"""
Bambu Lab Filament Sync router.

Two-phase flow:
  POST /api/filament-sync/preview  → compute FilamentSyncPlan (no side effects)
  POST /api/filament-sync/apply    → execute ApplySyncRequest confirmed by user

Settings:
  GET  /api/filament-sync/status
  PATCH /api/filament-sync/settings

Sync modes (stored in bambu_filament_sync_direction):
  'off'           — disabled
  'pull'          — bambuFM → FM (import cloud spools locally)
  'push'          — FM → bambuFM (push local spools to cloud)
  'bidirectional' — both directions
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Spool, UserPreferences
from .. import bambu_cloud_client

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/filament-sync", tags=["filament-sync"])

SYNC_MODES = ("off", "pull", "push", "bidirectional")

# Confidence thresholds
THRESHOLD_SHOW    = 40   # minimum score to include in suggestions list
THRESHOLD_CHECKED = 80   # minimum score to pre-check a suggestion


# ── DB helper ─────────────────────────────────────────────────────────────────

def _get_or_create_prefs(db: Session) -> UserPreferences:
    prefs = db.query(UserPreferences).filter(UserPreferences.id == 1).first()
    if not prefs:
        prefs = UserPreferences(id=1)
        db.add(prefs)
        db.commit()
        db.refresh(prefs)
    return prefs


# ── Color matching ─────────────────────────────────────────────────────────────

def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.lstrip("#")
    if len(h) != 6:
        return (128, 128, 128)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (128, 128, 128)


def _color_distance(hex1: str, hex2: str) -> float:
    r1, g1, b1 = _hex_to_rgb(hex1)
    r2, g2, b2 = _hex_to_rgb(hex2)
    return math.sqrt((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2)


# ── Field mapping helpers ──────────────────────────────────────────────────────

def _cloud_hex(cloud: dict) -> str:
    raw = str(cloud.get("color") or "888888").strip().lstrip("#")
    return f"#{raw[:6].upper()}" if len(raw) >= 6 else "#888888"


def _cloud_summary(cloud: dict) -> str:
    parts = [
        cloud.get("filamentVendor") or "",
        cloud.get("filamentType") or "",
        cloud.get("filamentName") or "",
    ]
    return " ".join(p for p in parts if p).strip() or f"Cloud spool {cloud.get('id', '?')}"


def _local_summary(spool: Spool) -> str:
    parts = [spool.brand or "", spool.material or "", spool.color_name or ""]
    return " ".join(p for p in parts if p).strip() or f"Spool #{spool.id}"


def _local_to_cloud_body(spool: Spool) -> dict:
    """Build a cloud create/update payload from a local spool."""
    color_hex = (spool.color_hex or "#888888").lstrip("#").upper()[:6]
    # filamentName is shown as "Material Type" in the Bambu app (it's the product
    # series name, e.g. "Bambu PLA Matte"); filamentType is the raw material code
    # (PLA/PETG/…) hidden in their UI. filamentVendor already carries the brand,
    # so filamentName = material + subtypes (e.g. "PETG High Speed Matte") avoids
    # doubling the brand in Bambu's "Parameter 1" display (vendor + filamentName).
    # Mapping color_name here is wrong — it shows the color as the material type.
    name_parts = [spool.material or "", spool.subtype or "", spool.subtype2 or ""]
    filament_name = " ".join(p for p in name_parts if p).strip() or "Unknown"
    # Preserve color name in note since Bambu has no dedicated color-name field
    note = spool.notes or ""
    if spool.color_name and spool.color_name not in note:
        note = spool.color_name + (f" — {note}" if note else "")
    return {
        # createType / colorType / filamentId / isSupport are required by the
        # Bambu Swagger schema (CreateFilamentV2Req). Manually-added spools have
        # no RFID and no Bambu product ID so createType="manual", filamentId="",
        # isSupport=False, colorType=2 (monochrome). Missing any of these → 400.
        "createType":     "manual",
        "filamentVendor": spool.brand or "",
        "filamentType":   spool.material or "",
        "filamentName":   filament_name,
        "filamentId":     "",
        "isSupport":      False,
        "color":          color_hex,
        "colorType":      2,
        "totalNetWeight": int(spool.initial_weight_g or 0),
        "netWeight":      int(spool.current_weight_g or 0),
        "note":           note,
    }


# ── Match scoring ──────────────────────────────────────────────────────────────

def _match_score(local: Spool, cloud: dict) -> tuple[int, str]:
    """Return (score 0-99, reason string) for a local↔cloud pair."""
    score = 0
    reasons: list[str] = []

    cloud_mat   = (cloud.get("filamentType") or "").strip().upper()
    local_mat   = (local.material or "").strip().upper()
    cloud_brand = (cloud.get("filamentVendor") or "").strip().upper()
    local_brand = (local.brand or "").strip().upper()

    if cloud_mat and local_mat and cloud_mat == local_mat:
        score += 35
        reasons.append("material")

    if cloud_brand and local_brand and cloud_brand == local_brand:
        score += 30
        reasons.append("brand")

    cloud_color = _cloud_hex(cloud)
    local_color = (local.color_hex or "#888888").upper()
    dist = _color_distance(cloud_color, local_color)
    if dist <= 30:
        score += 35
        reasons.append("color")
    elif dist <= 80:
        score += 20
        reasons.append("color~")

    cloud_w = float(cloud.get("totalNetWeight") or 0)
    local_w = float(local.initial_weight_g or 0)
    if cloud_w > 0 and local_w > 0:
        ratio = min(cloud_w, local_w) / max(cloud_w, local_w)
        if ratio >= 0.95:
            score += 10
            reasons.append("weight")

    return min(score, 99), "+".join(reasons) if reasons else "none"


# ── Plan builder ───────────────────────────────────────────────────────────────

def _build_plan(local_spools: list[Spool], cloud_spools: list[dict],
                sync_mode: str) -> "FilamentSyncPlan":
    cloud_by_id: dict[str, dict] = {str(c["id"]): c for c in cloud_spools if c.get("id")}
    cloud_ids_in_response: set[str] = set(cloud_by_id.keys())

    # Split local into already-linked and unlinked
    linked_locals: list[Spool] = []
    unlinked_locals: list[Spool] = []
    cloud_deleted: list[SyncCloudDeleted] = []

    for s in local_spools:
        if s.bambu_spool_id:
            if s.bambu_spool_id in cloud_ids_in_response:
                linked_locals.append(s)
            else:
                # Previously linked, cloud record is gone
                cloud_deleted.append(SyncCloudDeleted(
                    local_id=s.id,
                    local_summary=_local_summary(s),
                    was_cloud_id=s.bambu_spool_id,
                ))
        else:
            unlinked_locals.append(s)

    linked_cloud_ids: set[str] = {s.bambu_spool_id for s in linked_locals}
    unlinked_cloud: list[dict] = [c for cid, c in cloud_by_id.items()
                                  if cid not in linked_cloud_ids]

    # Score all (local, cloud) pairs for unlinked items
    candidates: list[tuple[int, str, int, dict]] = []  # (score, reason, local_id, cloud)
    for s in unlinked_locals:
        for c in unlinked_cloud:
            score, reason = _match_score(s, c)
            if score >= THRESHOLD_SHOW:
                candidates.append((score, reason, s.id, c))

    # Sort descending so highest-confidence pairs are assigned first
    candidates.sort(key=lambda x: x[0], reverse=True)

    assigned_local_ids: set[int] = set()
    assigned_cloud_ids: set[str] = set()
    suggestions: list[SyncMatchSuggestion] = []

    local_map = {s.id: s for s in unlinked_locals}

    for score, reason, local_id, cloud in candidates:
        cloud_id = str(cloud["id"])
        if local_id in assigned_local_ids or cloud_id in assigned_cloud_ids:
            continue
        assigned_local_ids.add(local_id)
        assigned_cloud_ids.add(cloud_id)
        s = local_map[local_id]
        suggestions.append(SyncMatchSuggestion(
            local_id=local_id,
            local_summary=_local_summary(s),
            cloud_id=cloud_id,
            cloud_summary=_cloud_summary(cloud),
            cloud_color_hex=_cloud_hex(cloud),
            local_color_hex=(s.color_hex or "#888888"),
            confidence=score,
            match_reason=reason,
            pre_checked=(score >= THRESHOLD_CHECKED),
        ))

    # Remaining unmatched items
    unmatched_locals = [s for s in unlinked_locals if s.id not in assigned_local_ids]
    unmatched_cloud  = [c for c in unlinked_cloud if str(c["id"]) not in assigned_cloud_ids]

    cloud_only: list[SyncCloudOnly] = []
    if sync_mode in ("pull", "bidirectional"):
        for c in unmatched_cloud:
            cloud_only.append(SyncCloudOnly(
                cloud_id=str(c["id"]),
                cloud_summary=_cloud_summary(c),
                filament_vendor=c.get("filamentVendor") or "",
                filament_type=c.get("filamentType") or "",
                filament_name=c.get("filamentName") or "",
                color_hex=_cloud_hex(c),
                initial_weight_g=float(c.get("totalNetWeight") or 0),
                current_weight_g=float(c.get("netWeight") or 0),
            ))

    local_only: list[SyncLocalOnly] = []
    if sync_mode in ("push", "bidirectional"):
        for s in unmatched_locals:
            local_only.append(SyncLocalOnly(
                local_id=s.id,
                local_summary=_local_summary(s),
                color_hex=(s.color_hex or "#888888"),
            ))

    return FilamentSyncPlan(
        already_linked_count=len(linked_locals),
        match_suggestions=suggestions,
        cloud_only=cloud_only,
        local_only=local_only,
        cloud_deleted=cloud_deleted if sync_mode in ("pull", "bidirectional") else [],
    )


# ── Schemas ────────────────────────────────────────────────────────────────────

class SyncMatchSuggestion(BaseModel):
    local_id: int
    local_summary: str
    cloud_id: str
    cloud_summary: str
    cloud_color_hex: str
    local_color_hex: str
    confidence: int
    match_reason: str
    pre_checked: bool


class SyncCloudOnly(BaseModel):
    cloud_id: str
    cloud_summary: str
    filament_vendor: str
    filament_type: str
    filament_name: str
    color_hex: str
    initial_weight_g: float
    current_weight_g: float


class SyncLocalOnly(BaseModel):
    local_id: int
    local_summary: str
    color_hex: str


class SyncCloudDeleted(BaseModel):
    local_id: int
    local_summary: str
    was_cloud_id: str


class FilamentSyncPlan(BaseModel):
    already_linked_count: int
    match_suggestions: list[SyncMatchSuggestion]
    cloud_only: list[SyncCloudOnly]
    local_only: list[SyncLocalOnly]
    cloud_deleted: list[SyncCloudDeleted]


class ConfirmedMatch(BaseModel):
    local_id: int
    cloud_id: str


class DeletedAction(BaseModel):
    local_id: int
    action: Literal["archive", "keep", "delete"]


class ApplySyncRequest(BaseModel):
    confirmed_matches: list[ConfirmedMatch]
    import_from_cloud: list[str]   # cloud_ids to create locally
    push_to_cloud: list[int]       # local_ids to push to cloud
    deleted_actions: list[DeletedAction]


class FilamentSyncResult(BaseModel):
    matched: int
    imported: int
    pushed: int
    archived: int
    deleted: int
    errors: int


class SyncSettings(BaseModel):
    sync_mode: Literal["off", "pull", "push", "bidirectional"]


class SyncStatus(BaseModel):
    sync_mode: str
    enabled: bool
    last_sync_at: str | None
    total_spools: int
    linked_spools: int


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/status", response_model=SyncStatus)
def get_sync_status(db: Session = Depends(get_db)):
    prefs = _get_or_create_prefs(db)
    mode = prefs.bambu_filament_sync_direction or "off"
    total  = db.query(Spool).filter(Spool.archived == False).count()   # noqa: E712
    linked = db.query(Spool).filter(
        Spool.bambu_spool_id != None,   # noqa: E711
        Spool.archived == False,         # noqa: E712
    ).count()
    return SyncStatus(
        sync_mode=mode,
        enabled=(mode != "off"),
        last_sync_at=prefs.bambu_filament_last_sync_at.isoformat()
            if prefs.bambu_filament_last_sync_at else None,
        total_spools=total,
        linked_spools=linked,
    )


@router.patch("/settings", response_model=SyncStatus)
def patch_sync_settings(body: SyncSettings, db: Session = Depends(get_db)):
    if body.sync_mode not in SYNC_MODES:
        raise HTTPException(400, f"sync_mode must be one of {SYNC_MODES}")
    prefs = _get_or_create_prefs(db)
    prefs.bambu_filament_sync_direction = body.sync_mode
    prefs.bambu_filament_sync_enabled   = (body.sync_mode != "off")
    db.commit()
    db.refresh(prefs)
    total  = db.query(Spool).filter(Spool.archived == False).count()   # noqa: E712
    linked = db.query(Spool).filter(
        Spool.bambu_spool_id != None,   # noqa: E711
        Spool.archived == False,         # noqa: E712
    ).count()
    return SyncStatus(
        sync_mode=body.sync_mode,
        enabled=(body.sync_mode != "off"),
        last_sync_at=prefs.bambu_filament_last_sync_at.isoformat()
            if prefs.bambu_filament_last_sync_at else None,
        total_spools=total,
        linked_spools=linked,
    )


@router.post("/preview", response_model=FilamentSyncPlan)
async def preview_sync(db: Session = Depends(get_db)):
    """Compute sync plan — no DB writes, no cloud writes."""
    cloud_status = bambu_cloud_client.get_status()
    if cloud_status["status"] != "connected":
        raise HTTPException(503, "Not connected to Bambu Cloud")

    prefs = _get_or_create_prefs(db)
    sync_mode = prefs.bambu_filament_sync_direction or "off"
    if sync_mode == "off":
        raise HTTPException(400, "Sync is disabled. Enable it in settings first.")

    cloud_spools = await bambu_cloud_client.list_all_filaments()
    log.info("Filament sync preview: %d cloud spools, mode=%s", len(cloud_spools), sync_mode)

    local_spools = db.query(Spool).filter(Spool.archived == False).all()  # noqa: E712

    return _build_plan(local_spools, cloud_spools, sync_mode)


@router.post("/apply", response_model=FilamentSyncResult)
async def apply_sync(body: ApplySyncRequest, db: Session = Depends(get_db)):
    """Execute a user-confirmed sync plan."""
    cloud_status = bambu_cloud_client.get_status()
    if cloud_status["status"] != "connected":
        raise HTTPException(503, "Not connected to Bambu Cloud")

    # Re-fetch cloud data to ensure we apply against fresh records
    cloud_spools = await bambu_cloud_client.list_all_filaments()
    cloud_by_id  = {str(c["id"]): c for c in cloud_spools if c.get("id")}

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    matched = imported = pushed = archived = deleted_count = errors = 0

    # 1. Apply confirmed matches: link local → cloud and sync cloud fields onto local
    match_cloud_ids = {m.cloud_id for m in body.confirmed_matches}
    for m in body.confirmed_matches:
        try:
            spool = db.query(Spool).filter(Spool.id == m.local_id).first()
            if not spool:
                log.warning("apply: local spool %d not found for match", m.local_id)
                errors += 1
                continue
            cloud = cloud_by_id.get(m.cloud_id)
            if not cloud:
                log.warning("apply: cloud spool %s not found for match", m.cloud_id)
                errors += 1
                continue
            spool.bambu_spool_id  = m.cloud_id
            spool.bambu_synced_at = now
            # Sync weight fields from cloud
            cloud_init = float(cloud.get("totalNetWeight") or 0)
            cloud_curr = float(cloud.get("netWeight") or 0)
            if cloud_init > 0:
                spool.initial_weight_g = cloud_init
            if cloud_curr >= 0:
                spool.current_weight_g = cloud_curr
            spool.updated_at = now
            matched += 1
        except Exception as exc:
            log.warning("apply: match error for local=%d cloud=%s: %s", m.local_id, m.cloud_id, exc)
            errors += 1

    # 2. Import from cloud → create local spools
    for cloud_id in body.import_from_cloud:
        if cloud_id in match_cloud_ids:
            continue  # already handled as a match
        try:
            cloud = cloud_by_id.get(cloud_id)
            if not cloud:
                errors += 1
                continue
            new_spool = Spool(
                bambu_spool_id=cloud_id,
                brand=cloud.get("filamentVendor") or "",
                material=cloud.get("filamentType") or "PLA",
                color_name="",
                color_hex=_cloud_hex(cloud),
                initial_weight_g=max(float(cloud.get("totalNetWeight") or 0), 1.0),
                current_weight_g=max(float(cloud.get("netWeight") or 0), 0.0),
                # Store the Bambu product name in notes; it's not a color name
                notes=cloud.get("filamentName") or "",
                bambu_synced_at=now,
                created_at=now,
                updated_at=now,
            )
            db.add(new_spool)
            imported += 1
        except Exception as exc:
            log.warning("apply: import error for cloud=%s: %s", cloud_id, exc)
            errors += 1

    # 3. Push local → cloud (create cloud records for local-only spools)
    for local_id in body.push_to_cloud:
        try:
            spool = db.query(Spool).filter(Spool.id == local_id).first()
            if not spool:
                errors += 1
                continue
            body_payload = _local_to_cloud_body(spool)
            result = await bambu_cloud_client.create_filament(body_payload)
            cloud_id = str(result.get("id") or (result.get("data") or {}).get("id") or "")
            if cloud_id:
                spool.bambu_spool_id  = cloud_id
                spool.bambu_synced_at = now
                spool.updated_at      = now
            pushed += 1
        except Exception as exc:
            log.warning("apply: push error for local=%d: %s", local_id, exc)
            errors += 1

    # 4. Handle cloud-deleted spools
    for da in body.deleted_actions:
        try:
            spool = db.query(Spool).filter(Spool.id == da.local_id).first()
            if not spool:
                errors += 1
                continue
            if da.action == "archive":
                spool.archived        = True
                spool.bambu_spool_id  = None
                spool.bambu_synced_at = None
                spool.updated_at      = now
                archived += 1
            elif da.action == "keep":
                spool.bambu_spool_id  = None
                spool.bambu_synced_at = None
                spool.updated_at      = now
            elif da.action == "delete":
                db.delete(spool)
                deleted_count += 1
        except Exception as exc:
            log.warning("apply: deleted action error for local=%d: %s", da.local_id, exc)
            errors += 1

    # Update last sync timestamp
    prefs = _get_or_create_prefs(db)
    prefs.bambu_filament_last_sync_at = now
    db.commit()

    log.info(
        "Filament sync apply done — matched=%d imported=%d pushed=%d "
        "archived=%d deleted=%d errors=%d",
        matched, imported, pushed, archived, deleted_count, errors,
    )
    return FilamentSyncResult(
        matched=matched,
        imported=imported,
        pushed=pushed,
        archived=archived,
        deleted=deleted_count,
        errors=errors,
    )
