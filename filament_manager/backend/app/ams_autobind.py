"""
Smart auto-bind of tracked spools to AMS trays via RFID ``tag_uid``.

When a genuine Bambu spool is physically loaded into an AMS tray, the printer
reads its RFID ``tag_uid`` — a 16-hex string that is unique per physical spool.
This module uses that tag to deterministically bind the tracked :class:`Spool`
to the tray by setting the spool's ``ams_slot`` column, so the *existing*
auto-deduct logic (see ``print_monitor``) fires against the correct physical
spool even when the user owns many spools of the same material + colour.

``ams_slot`` is stored in the ``"{printer_name}:{slot_key}"`` form (see
``routers/printers.py``) — this module writes that same full-key form.

SAFETY — EXACT RFID identity only, never guess
-----------------------------------------------
The only auto-action taken here is a deterministic bind by physical RFID: a
tray's real ``tag_uid`` is matched against ``Spool.tag_uid`` and, on an EXACT
hit, that spool's ``ams_slot`` is moved to the current tray. A spool's
``tag_uid`` is populated from the authoritative Bambu Cloud filament record
during sync (see ``routers/filament_sync``) or via the manual "Assign spool"
action in the UI.

We NEVER bind by material / colour / bambu_spool_id — those identify a
*product*, not a *physical spool*, so guessing by them can (and did) stamp a
tray's RFID onto the wrong record and deduct from the wrong spool. An unknown
tag (no spool carries it) is left untouched for a one-time manual "Assign
spool" confirm, which stores the tag_uid and upgrades all future loads to the
exact-match path.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import PrinterConfig, Spool

log = logging.getLogger(__name__)


def _is_real_tag_uid(tag_uid) -> bool:
    """True only for a usable RFID tag.

    Genuine Bambu spools report a 16-hex, non-zero value (e.g.
    ``"4767E20300000100"``). Third-party/generic spools report empty or
    all-zeros (``"0000000000000000"``) — those have no usable RFID and are
    skipped entirely (manual assignment only).
    """
    if not tag_uid:
        return False
    s = str(tag_uid).strip()
    if not s:
        return False
    # All-zeros (any length) = no tag present.
    if set(s) <= {"0"}:
        return False
    return True


def _clear_slot_from_others(db: Session, full_key: str, slot_key: str, keep_spool_id: int | None) -> None:
    """Ensure no OTHER spool claims this AMS slot (a tray holds one spool).

    Clears ``ams_slot`` from every spool currently pointing at this slot
    (either full ``"{printer}:{slot}"`` or bare ``slot`` form) except the one we
    are binding. Guards against duplicate binds / races.
    """
    q = db.query(Spool).filter(
        (Spool.ams_slot == full_key) | (Spool.ams_slot == slot_key)
    )
    if keep_spool_id is not None:
        q = q.filter(Spool.id != keep_spool_id)
    q.update({"ams_slot": None}, synchronize_session=False)


def _autobind_for_printer(db: Session, printer: PrinterConfig, detail: dict[str, dict]) -> int:
    """Run the auto-bind pass for one printer's current AMS tray detail.

    ``detail`` is ``{slot_key: {material, color, remain, tag_uid, ...}}`` from
    ``bambu_cloud_client.get_ams_detail_for_serial``. Returns the number of
    spools whose ams_slot was set/updated.
    """
    changed = 0
    for slot_key, slot_info in detail.items():
        tag_uid = slot_info.get("tag_uid")
        if not _is_real_tag_uid(tag_uid):
            continue  # empty / all-zeros / third-party → manual only
        tag_uid = str(tag_uid).strip()
        full_key = f"{printer.name}:{slot_key}"

        # Exact RFID identity match ONLY. The spool's tag_uid is populated from
        # the authoritative Bambu Cloud filament record during sync (see
        # routers/filament_sync) or via the manual "Assign spool" action — never
        # guessed from material/colour, which is a product, not a physical spool.
        bound = db.query(Spool).filter(Spool.tag_uid == tag_uid).first()
        if bound is None:
            continue  # unknown physical spool → leave for manual "Assign spool"
        if bound.ams_slot != full_key:
            _clear_slot_from_others(db, full_key, slot_key, keep_spool_id=bound.id)
            log.info(
                "AMS auto-bind: tag_uid %s → spool #%d re-bound %s → %s",
                tag_uid, bound.id, bound.ams_slot, full_key,
            )
            bound.ams_slot = full_key
            changed += 1

    return changed


def autobind_from_ams_cache(serial: str) -> int:
    """Entry point: reconcile spool↔tray binding from the live AMS cache.

    Called from the MQTT message path whenever AMS tray data is refreshed. Opens
    its own DB session (this runs on the paho MQTT thread, not the async loop).
    Returns the number of spools re-bound/bound (0 if nothing to do).
    Never raises — logs and returns 0 on any error.
    """
    try:
        from . import bambu_cloud_client
    except Exception:  # pragma: no cover — import guard
        return 0

    detail = bambu_cloud_client.get_ams_detail_for_serial(serial)
    if not detail:
        return 0
    # Cheap pre-check: skip the DB session entirely if no tray has a real tag.
    if not any(_is_real_tag_uid(s.get("tag_uid")) for s in detail.values()):
        return 0

    db = SessionLocal()
    try:
        printers = (
            db.query(PrinterConfig)
            .filter(PrinterConfig.bambu_serial == serial)
            .filter(PrinterConfig.is_active == True)  # noqa: E712
            .all()
        )
        total = 0
        for printer in printers:
            total += _autobind_for_printer(db, printer, detail)
        if total:
            db.commit()
            try:
                from . import ha_publisher
                ha_publisher.trigger()
            except Exception as exc:  # pragma: no cover
                log.debug("AMS auto-bind: ha_publisher.trigger failed: %s", exc)
        return total
    except Exception as exc:
        log.warning("AMS auto-bind failed for serial %s: %s", serial, exc, exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass
        return 0
    finally:
        db.close()
