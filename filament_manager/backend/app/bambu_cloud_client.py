"""
Bambu Lab Cloud integration.

Handles:
- Email/password + 2FA authentication via Bambu Cloud REST API
- Encrypted credential storage in /data/.bambu_cloud.json (chmod 0600)
- Cloud MQTT connection per printer (us.mqtt.bambulab.com:8883)
- Bridging MQTT events → print_monitor state machine

Security model:
  The Fernet key is generated once and stored in the same file as the
  ciphertext. Protection relies entirely on file permissions (0600), which
  is appropriate for HA add-ons where /data/ is a single-tenant volume —
  the same security boundary as HA's own secrets.yaml and our SQLite DB.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import ssl
import stat
import threading
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import requests
from cryptography.fernet import Fernet
from fastapi import HTTPException

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

CRED_FILE = "/data/.bambu_cloud.json"
_2FA_TIMEOUT_SECONDS = 600  # 10 minutes

_AUTH_BASE = "https://api.bambulab.com/v1/user-service/user"
_IOT_BASE  = "https://api.bambulab.com/v1/iot-service/api"
MQTT_HOST  = "us.mqtt.bambulab.com"
MQTT_PORT  = 8883

# ── Module-level state ────────────────────────────────────────────────────────

_status: dict = {
    "status": "disconnected",   # disconnected | pending_2fa | connected | error
    "email": None,
    "error": None,
}

# Holds login context during 2FA flow
_pending: dict = {}   # {email, password}

# serial → paho MQTT client
_mqtt_clients: dict[str, mqtt.Client] = {}

# serial → last parsed printer status dict
_printer_status_cache: dict[str, dict] = {}

# serial → ams snapshot {slot_key: remain_pct}
_ams_cache: dict[str, dict[str, float]] = {}

# serial → set of 0-based tray indices seen during the current print (tray_now tracking)
_print_active_trays: dict[str, set[int]] = {}

# serial → {unit_id (1-based): max tray number seen for that unit}
# Derived from actual MQTT data — tells us how many slots each AMS unit really has.
_ams_unit_tray_counts: dict[str, dict[int, int]] = {}

# serial → printer_id (DB)
_serial_to_printer_id: dict[str, int] = {}

# Running asyncio event loop (stored at startup for thread-safe task scheduling)
_loop: asyncio.AbstractEventLoop | None = None

# Prevent concurrent re-auth attempts
_reauth_in_progress: bool = False


# ── JWT / auth helpers ────────────────────────────────────────────────────────

def _jwt_uid(token: str) -> str:
    """Decode UID from JWT payload without signature verification."""
    try:
        payload_b64 = token.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        return str(payload.get("uid") or payload.get("sub", ""))
    except Exception:
        return ""


def _jwt_payload(token: str) -> dict:
    """Decode full JWT payload without signature verification."""
    try:
        payload_b64 = token.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))
    except Exception:
        return {}


def _is_token_valid(token: str) -> bool:
    """Return True if the token is usable.

    If the JWT has an 'exp' claim and it is in the past → expired (False).
    If no 'exp' claim (Bambu tokens sometimes omit it) → assume valid (True).
    If the token is non-empty but not a decodable JWT (Bambu post-2FA tokens
    are opaque strings) → assume valid (True) and let the MQTT broker reject
    it with rc=5 if it has actually expired.
    If the token is empty → invalid (False).
    """
    import time
    if not token:
        return False
    payload = _jwt_payload(token)
    if not payload:
        # Token present but not a standard JWT (e.g. Bambu post-2FA opaque token)
        # — assume it is still valid.
        return True
    exp = payload.get("exp")
    if exp is None:
        # No expiry claim — assume valid.
        return True
    return float(exp) > time.time()


def _mqtt_username(email: str, token: str) -> str:
    # Prefer the uid saved in credentials (token may not be a standard JWT)
    creds = _load_credentials()
    if creds and creds.get("uid"):
        return f"u_{creds['uid']}"
    uid = _jwt_uid(token)
    return f"u_{uid}" if uid else email


# ── Credential helpers ────────────────────────────────────────────────────────

def _save_credentials(email: str, password: str, token: str, uid: str = "") -> None:
    key = Fernet.generate_key()
    f = Fernet(key)
    data = {
        "email": email,
        "password_enc": f.encrypt(password.encode()).decode(),
        "fernet_key": key.decode(),
        "token": token,
        "uid": uid,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(CRED_FILE, "w") as fp:
        json.dump(data, fp)
    os.chmod(CRED_FILE, stat.S_IRUSR | stat.S_IWUSR)
    log.info("Bambu Cloud credentials saved to %s", CRED_FILE)


def _load_credentials() -> dict | None:
    try:
        with open(CRED_FILE) as fp:
            return json.load(fp)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _decrypt_password(data: dict) -> str:
    f = Fernet(data["fernet_key"].encode())
    return f.decrypt(data["password_enc"].encode()).decode()


def _delete_credentials() -> None:
    try:
        os.remove(CRED_FILE)
        log.info("Bambu Cloud credentials removed")
    except FileNotFoundError:
        pass


# ── HTTP auth calls ───────────────────────────────────────────────────────────

def _http_login(email: str, password: str, code: str | None = None) -> dict:
    """POST to Bambu login endpoint. Returns response JSON."""
    payload: dict = {"account": email, "password": password}
    if code:
        payload["code"] = code
        payload["loginType"] = "verifyCode"
    resp = requests.post(f"{_AUTH_BASE}/login", json=payload, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _http_send_2fa_email(email: str) -> None:
    """Ask Bambu to send the verification code to the user's email."""
    try:
        requests.post(
            f"{_AUTH_BASE}/sendemail/code",
            json={"email": email, "type": "codeLogin"},
            timeout=20,
        )
    except Exception as exc:
        log.warning("Failed to request 2FA email: %s", exc)


def _http_get_devices(token: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{_IOT_BASE}/user/bind", headers=headers, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    return data.get("devices", [])


def _ams_index_to_slot_key(
    index: int,
    unit_tray_counts: dict[int, int] | None = None,
) -> str | None:
    """Convert 0-based global AMS tray index (tray_now / amsDetailMapping[].ams) to slot key.

    When unit_tray_counts is supplied ({1: 4, 2: 1} etc.) the actual per-unit tray counts
    are used to compute the unit/tray from the global offset.  Falls back to the legacy
    4-trays-per-unit assumption when no counts are available.

    Returns "ams{unit}_tray{slot}" (1-based), or None for external spool (254, 255) or
    an index that exceeds the known AMS capacity.
    """
    if index is None or index in (254, 255):
        return None

    if unit_tray_counts:
        offset = 0
        for unit_id in sorted(unit_tray_counts.keys()):
            count = unit_tray_counts[unit_id]
            if index < offset + count:
                tray = (index - offset) + 1  # 1-based
                return f"ams{unit_id}_tray{tray}"
            offset += count
        return None  # index exceeds known AMS capacity

    # Fallback: standard 4-trays-per-unit assumption (max 4 units = 16 slots)
    if index >= 16:
        return None
    unit = (index // 4) + 1
    slot = (index % 4) + 1
    return f"ams{unit}_tray{slot}"


def get_ams_unit_tray_counts(serial: str) -> dict[int, int]:
    """Return the observed tray count per AMS unit for a device serial.

    Derived from actual MQTT data; empty dict if no data has been received yet.
    """
    return dict(_ams_unit_tray_counts.get(serial, {}))


def _http_get_task_data(serial: str, token: str) -> dict:
    """Fetch the most recent completed task from the Bambu Cloud task API.

    Returns a dict with:
      weight (float | None)       — total filament weight in grams
      amsDetailMapping (list)     — per-tray breakdown [{ams, weight, filamentType, sourceColor, ...}]
    """
    result: dict = {"weight": None, "amsDetailMapping": []}
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(
            "https://api.bambulab.com/v1/user-service/my/tasks",
            params={"deviceId": serial, "limit": 1},
            headers=headers,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        hits = data.get("hits") or []
        if hits:
            task = hits[0]
            weight = task.get("weight")
            if weight is not None:
                result["weight"] = float(weight)
            ams_map = task.get("amsDetailMapping")
            if isinstance(ams_map, list):
                result["amsDetailMapping"] = ams_map
    except Exception as exc:
        log.warning("Bambu Cloud task data fetch failed for %s: %s", serial, exc)
    return result


async def get_task_data_for_serial(serial: str) -> dict:
    """Async wrapper: fetch the most recent task data (weight + amsDetailMapping) for a serial."""
    creds = _load_credentials()
    if not creds or not creds.get("token"):
        return {"weight": None, "amsDetailMapping": []}
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: _http_get_task_data(serial, creds["token"]))


def _http_get_uid(token: str) -> str:
    """Fetch the user's uid from the Bambu profile endpoint.

    The token returned after 2FA verification is not always a standard JWT,
    so uid cannot be reliably extracted from the token payload.  The profile
    endpoint is the authoritative source for the uid used as the MQTT username.
    """
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(
            "https://api.bambulab.com/v1/user-service/my/profile",
            headers=headers,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        uid = str(data.get("uid") or data.get("uidStr") or "")
        log.info("Bambu Cloud profile uid: %r (response keys: %s)", uid, list(data.keys()))
        return uid
    except Exception as exc:
        log.warning("Bambu Cloud: failed to fetch profile uid: %s", exc)
        return ""


# ── MQTT helpers ──────────────────────────────────────────────────────────────

def _process_device_message(serial: str, data: dict) -> None:
    """Parse MQTT payload, update caches, schedule print_monitor calls."""
    print_data = data.get("print", {})

    # Update AMS cache from top-level or nested ams object
    # tray_now (currently active tray slot) lives inside the ams dict, not in print
    current = _printer_status_cache.get(serial, {})
    for ams_source in (data.get("ams", {}), print_data.get("ams", {})):
        if ams_source:
            _parse_ams_into_cache(serial, ams_source)
            if "tray_now" in ams_source:
                tray_now_val = ams_source["tray_now"]
                current["tray_now"] = tray_now_val
                # Track active trays during print for suggested_usages fallback
                try:
                    idx = int(tray_now_val)
                    if _ams_index_to_slot_key(idx, get_ams_unit_tray_counts(serial)) is not None:
                        if serial not in _print_active_trays:
                            _print_active_trays[serial] = set()
                        _print_active_trays[serial].add(idx)
                except (TypeError, ValueError):
                    pass
    _printer_status_cache[serial] = current

    # Merge ALL scalar fields from the print object — Bambu sends incremental
    # updates so we only overwrite keys that are present in this message.
    # Storing every field ensures the raw cache in the Experiments tab shows
    # the full picture of what the printer actually sends.
    current = _printer_status_cache.get(serial, {})
    for field, val in print_data.items():
        # Skip nested objects (ams dict handled above); store everything else
        if not isinstance(val, (dict, list)):
            current[field] = val
    _printer_status_cache[serial] = current

    # Only dispatch print-state callbacks when gcode_state is actually present in
    # this message.  Using the cached value would re-fire the callback on every
    # incremental AMS/temperature update, causing duplicate coroutines that race
    # to close the same job and hit SQLite write conflicts.
    gcode_state_in_msg = print_data.get("gcode_state")
    if not gcode_state_in_msg or _loop is None:
        return

    printer_id = _serial_to_printer_id.get(serial)
    if printer_id is None:
        return

    # Import here to avoid circular import at module level
    from . import print_monitor

    state_upper = gcode_state_in_msg.upper()
    if state_upper == "RUNNING":
        asyncio.run_coroutine_threadsafe(
            print_monitor.on_cloud_print_start(printer_id, current.get("subtask_name", ""), serial),
            _loop,
        )
    elif state_upper in ("FINISH", "FAILED", "IDLE"):
        # PAUSE is intentionally excluded — a paused job stays open until FINISH/FAILED/IDLE.
        asyncio.run_coroutine_threadsafe(
            print_monitor.on_cloud_print_end(printer_id, state_upper != "FAILED", state_upper),
            _loop,
        )


def _parse_ams_into_cache(serial: str, ams_raw: dict) -> None:
    # Merge into the existing cache — do NOT replace wholesale.  Bambu sends
    # incremental MQTT updates that may only carry `remain` without the full
    # tray profile (tray_sub_brands / tray_type / color).  Overwriting the
    # entire cache on every incremental update would wipe the material name
    # that was captured from the last pushall.
    existing = dict(_ams_cache.get(serial, {}))
    unit_counts = dict(_ams_unit_tray_counts.get(serial, {}))
    changed = False
    for unit in ams_raw.get("ams", []):
        ams_id = int(unit.get("id", 0)) + 1   # 1-based
        trays_in_msg = unit.get("tray", [])

        # Track the highest tray id seen for this unit.  Use max() so incremental
        # updates (which may only report a single tray) don't shrink the count.
        tray_ids_in_msg = {int(t.get("id", 0)) + 1 for t in trays_in_msg if "id" in t}
        if tray_ids_in_msg:
            unit_counts[ams_id] = max(unit_counts.get(ams_id, 0), max(tray_ids_in_msg))

        for tray in trays_in_msg:
            tray_id = int(tray.get("id", 0)) + 1  # 1-based
            slot_key = f"ams{ams_id}_tray{tray_id}"
            slot = dict(existing.get(slot_key, {}))

            # remain — always update when the key is present in the message
            if "remain" in tray:
                try:
                    slot["remain"] = float(tray["remain"])
                except (TypeError, ValueError):
                    slot["remain"] = None

            # remain_flag — update when present
            if "remain_flag" in tray:
                slot["remain_flag"] = tray["remain_flag"]

            # color — update only when a non-empty value is sent
            color_raw = str(tray.get("tray_color") or tray.get("color") or "").strip()
            if len(color_raw) >= 6:
                slot["color"] = f"#{color_raw[:6]}"

            # material — update only when the message carries actual profile data;
            # preserve the existing name if this update has no material fields at all
            sub_brand = tray.get("tray_sub_brands") or ""
            base_type = tray.get("tray_type") or tray.get("type") or ""
            if sub_brand or base_type:
                slot["material"] = sub_brand or base_type

            existing[slot_key] = slot
            changed = True

    if changed:
        _ams_cache[serial] = existing
    if unit_counts:
        _ams_unit_tray_counts[serial] = unit_counts


async def _reauthenticate() -> None:
    """Re-login using saved encrypted password and restart all MQTT connections."""
    global _reauth_in_progress, _pending
    creds = _load_credentials()
    if not creds:
        log.error("Bambu Cloud token refresh: no saved credentials")
        _status["status"] = "error"
        _status["error"] = "Session expired — please log in again"
        _reauth_in_progress = False
        return
    email = creds.get("email", "")
    try:
        password = _decrypt_password(creds)
    except Exception as exc:
        log.error("Bambu Cloud token refresh: failed to decrypt password: %s", exc)
        _status["status"] = "error"
        _status["error"] = "Session expired — please log in again"
        _reauth_in_progress = False
        return
    try:
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, lambda: _http_login(email, password))
    except Exception as exc:
        log.error("Bambu Cloud token refresh: re-login failed: %s", exc)
        _status["status"] = "error"
        _status["error"] = f"Session expired — re-login failed: {exc}"
        _reauth_in_progress = False
        return

    login_type = resp.get("loginType", "")
    if login_type == "verifyCode":
        # 2FA required during automatic re-auth — do NOT auto-send the email or
        # enter the 2FA flow.  Automatically spamming the user's inbox on every
        # container restart (when the token has expired) is not acceptable.
        # Instead, surface a clear error and let the user log in manually from
        # the Experiments tab.
        log.warning(
            "Bambu Cloud token refresh: 2FA required for %s — "
            "manual re-login needed (Experiments tab)",
            email,
        )
        _status["status"] = "error"
        _status["email"] = email
        _status["error"] = "Session expired — please log in again in the Experiments tab"
        _reauth_in_progress = False
        return

    new_token = resp.get("accessToken", "")
    if not new_token:
        log.error("Bambu Cloud token refresh: no token in response")
        _status["status"] = "error"
        _status["error"] = "Session expired — please log in again"
        _reauth_in_progress = False
        return

    uid = await loop.run_in_executor(None, lambda: _http_get_uid(new_token))
    _save_credentials(email, password, new_token, uid)
    _status["status"] = "connected"
    _status["email"] = email
    _status["error"] = None
    log.info("Bambu Cloud token refreshed for %s — restarting MQTT", email)
    await _connect_mqtt_for_cloud_printers(email, new_token)
    # Clear flag AFTER new clients are registered so the rc=5 handler on any
    # lingering old client cannot restart re-auth before the new client is in place.
    _reauth_in_progress = False


def _start_mqtt_for_serial(serial: str, email: str, token: str) -> None:
    """Create and start a non-blocking paho MQTT client for a device serial."""
    if serial in _mqtt_clients:
        try:
            _mqtt_clients[serial].loop_stop()
            _mqtt_clients[serial].disconnect()
        except Exception:
            pass

    try:
        creds = _load_credentials()
        saved_uid = (creds or {}).get("uid", "")
        jwt_uid = _jwt_uid(token)
        username = f"u_{saved_uid}" if saved_uid else (f"u_{jwt_uid}" if jwt_uid else email)
        log.info(
            "Bambu Cloud MQTT starting for %s — username=%r saved_uid=%r jwt_uid=%r",
            serial, username, saved_uid, jwt_uid,
        )
        # paho-mqtt 2.x requires callback_api_version; 1.x doesn't have it
        try:
            client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
                client_id=f"bambu-filament-manager-{serial}",
                protocol=mqtt.MQTTv311,
            )
        except AttributeError:
            client = mqtt.Client(
                client_id=f"bambu-filament-manager-{serial}",
                protocol=mqtt.MQTTv311,
            )
        client.username_pw_set(username, token)

        tls_ctx = ssl.create_default_context()
        client.tls_set_context(tls_ctx)

        def on_connect(c, userdata, flags, rc):
            global _reauth_in_progress
            log.info("Bambu Cloud MQTT on_connect for %s: rc=%s flags=%s", serial, rc, flags)
            if rc == 0:
                topic = f"device/{serial}/report"
                c.subscribe(topic, qos=0)
                log.info("Bambu Cloud MQTT subscribed to %s", topic)
                payload = json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}})
                c.publish(f"device/{serial}/request", payload, qos=0)
                log.info("Bambu Cloud MQTT pushall sent for %s", serial)
            elif int(str(rc)) == 5:
                # Ignore callbacks from stale clients that were replaced by a newer connection
                if _mqtt_clients.get(serial) is not c:
                    log.debug("Ignoring rc=5 from stale client for %s", serial)
                    threading.Thread(target=lambda: (c.disconnect(), c.loop_stop()), daemon=True).start()
                    return
                # rc=5 = Not Authorised — disconnect (suppresses auto-reconnect) then stop loop
                log.warning("Bambu Cloud MQTT auth rejected for %s (rc=5) — stopping client", serial)
                threading.Thread(target=lambda: (c.disconnect(), c.loop_stop()), daemon=True).start()
                # Only trigger re-auth once; skip if already pending 2FA or in error state
                already_handled = _reauth_in_progress or _status["status"] in ("pending_2fa", "error")
                if _loop is not None and not already_handled:
                    _reauth_in_progress = True
                    asyncio.run_coroutine_threadsafe(_reauthenticate(), _loop)
            else:
                log.error("Bambu Cloud MQTT connect failed for %s, rc=%s", serial, rc)

        def on_message(c, userdata, msg):
            log.debug("Bambu Cloud MQTT message on %s: %d bytes", msg.topic, len(msg.payload))
            try:
                data = json.loads(msg.payload)
            except Exception as exc:
                log.warning("Bambu Cloud MQTT bad JSON for %s: %s", serial, exc)
                return
            _process_device_message(serial, data)

        def on_disconnect(c, userdata, rc):
            if _mqtt_clients.get(serial) is not c:
                return  # stale client disconnecting — ignore
            log.warning("Bambu Cloud MQTT disconnected for %s, rc=%s", serial, rc)

        def on_log(c, userdata, level, buf):
            log.debug("paho [%s]: %s", serial, buf)

        client.on_connect = on_connect
        client.on_message = on_message
        client.on_disconnect = on_disconnect
        client.on_log = on_log

        client.connect_async(MQTT_HOST, MQTT_PORT)
        client.loop_start()  # background thread — non-blocking

        _mqtt_clients[serial] = client
        log.info("Bambu Cloud MQTT client started for serial %s", serial)
    except Exception as exc:
        log.error("Failed to start MQTT for %s: %s", serial, exc)


# ── Public API ────────────────────────────────────────────────────────────────

async def startup() -> None:
    """Called from main.py lifespan. Reconnects if saved credentials exist."""
    global _loop, _reauth_in_progress
    _loop = asyncio.get_event_loop()

    creds = _load_credentials()
    if not creds:
        log.info("Bambu Cloud: no saved credentials, skipping auto-connect")
        return

    email = creds.get("email", "")
    token = creds.get("token", "")
    if not email or not token:
        return

    if _is_token_valid(token):
        log.info("Bambu Cloud: token still valid, reconnecting as %s", email)
        _status["status"] = "connected"
        _status["email"] = email
        _status["error"] = None
        await _connect_mqtt_for_cloud_printers(email, token)
        # If MQTT got rc=5 during connect the on_connect handler already called
        # _reauthenticate() which may have changed _status — leave it as-is.
    else:
        # Token expired — attempt silent re-auth using saved password before starting MQTT.
        # This avoids the rc=5 → 2FA loop on every container restart with a stale token.
        log.info("Bambu Cloud: saved token expired for %s — attempting re-auth", email)
        _reauth_in_progress = True
        await _reauthenticate()


async def shutdown() -> None:
    """Cleanly stop all MQTT clients."""
    for serial, client in list(_mqtt_clients.items()):
        try:
            client.loop_stop()
            client.disconnect()
            log.info("Bambu Cloud MQTT disconnected for %s", serial)
        except Exception:
            pass
    _mqtt_clients.clear()


async def begin_login(email: str, password: str) -> dict:
    """
    Start the login flow.
    - If Bambu requires 2FA: sends the verification email and returns
      {"requires_2fa": True} so the frontend can show the code form.
    - If no 2FA needed: completes login immediately.
    """
    global _pending

    try:
        resp = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _http_login(email, password)
        )
    except Exception as exc:
        _status["status"] = "error"
        _status["error"] = str(exc)
        raise HTTPException(400, f"Login failed: {exc}")

    login_type = resp.get("loginType", "")

    if login_type == "verifyCode":
        _pending = {"email": email, "password": password}
        _status["status"] = "pending_2fa"
        _status["email"] = email
        _status["error"] = None
        # Ask Bambu to send the 2FA email
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: _http_send_2fa_email(email)
        )
        return {"requires_2fa": True}

    # No 2FA required — token is in the first response
    token = resp.get("accessToken", "")
    if not token:
        raise HTTPException(400, "Login failed: no access token returned")

    loop = asyncio.get_event_loop()
    uid = await loop.run_in_executor(None, lambda: _http_get_uid(token))
    _save_credentials(email, password, token, uid)
    _status["status"] = "connected"
    _status["email"] = email
    _status["error"] = None
    await _connect_mqtt_for_cloud_printers(email, token)
    return {"requires_2fa": False}


async def verify_2fa(code: str) -> None:
    """Submit the 2FA code, complete login, persist credentials, start MQTT."""
    if not _pending or _status["status"] != "pending_2fa":
        raise HTTPException(400, "No pending login — start login first")

    email = _pending["email"]
    password = _pending["password"]

    try:
        resp = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _http_login(email, password, code=code)
        )
    except Exception as exc:
        _status["status"] = "error"
        _status["error"] = str(exc)
        raise HTTPException(400, f"Verification failed: {exc}")

    token = resp.get("accessToken", "")
    if not token:
        err = resp.get("message", "No access token returned")
        _status["status"] = "error"
        _status["error"] = err
        raise HTTPException(400, f"Login failed: {err}")

    global _reauth_in_progress
    loop = asyncio.get_event_loop()
    uid = await loop.run_in_executor(None, lambda: _http_get_uid(token))
    _save_credentials(email, password, token, uid)
    _status["status"] = "connected"
    _status["email"] = email
    _status["error"] = None
    _pending.clear()

    await _connect_mqtt_for_cloud_printers(email, token)
    # Clear flag AFTER new clients are registered (same ordering as _reauthenticate)
    _reauth_in_progress = False
    log.info("Bambu Cloud: login complete for %s", email)


async def logout() -> None:
    """Disconnect MQTT, delete credentials, reset state."""
    global _reauth_in_progress
    await shutdown()
    _delete_credentials()
    _status["status"] = "disconnected"
    _status["email"] = None
    _status["error"] = None
    _serial_to_printer_id.clear()
    _printer_status_cache.clear()
    _ams_cache.clear()
    _print_active_trays.clear()
    _ams_unit_tray_counts.clear()
    _pending.clear()
    _reauth_in_progress = False
    log.info("Bambu Cloud: logged out")


def get_status() -> dict:
    return {
        "status": _status["status"],
        "email": _status["email"],
        "error": _status["error"],
    }


def get_devices() -> list[dict]:
    """Fetch bound devices from Bambu Cloud (requires connected state)."""
    if _status["status"] != "connected":
        raise HTTPException(503, "Not connected to Bambu Cloud")
    creds = _load_credentials()
    if not creds:
        raise HTTPException(503, "No credentials found")
    try:
        raw = _http_get_devices(creds["token"])
        return [
            {
                "serial": d.get("dev_id", ""),
                "name": d.get("name", d.get("dev_id", "")),
                "model": d.get("dev_model_name") or d.get("dev_product_name", ""),
                "online": d.get("online", False),
            }
            for d in raw
        ]
    except Exception as exc:
        log.error("Bambu Cloud get_devices failed: %s", exc)
        raise HTTPException(502, f"Failed to fetch devices: {exc}")


def get_printer_cloud_status(serial: str | None) -> dict:
    """Return last known MQTT status for a printer (or empty if none yet)."""
    if not serial:
        return {}
    return _printer_status_cache.get(serial, {})


def get_ams_snapshot_for_serial(serial: str) -> dict[str, float]:
    """Return the last AMS remain% snapshot for a device serial."""
    return {k: v["remain"] for k, v in _ams_cache.get(serial, {}).items()}


def get_ams_detail_for_serial(serial: str) -> dict[str, dict]:
    """Return full AMS tray detail (remain, material, color) for display."""
    return dict(_ams_cache.get(serial, {}))


def reset_print_trays(serial: str) -> None:
    """Clear the active tray set for a serial — call at print start."""
    _print_active_trays[serial] = set()


def get_print_trays(serial: str) -> set[int]:
    """Return the set of 0-based tray indices seen during the current/last print."""
    return set(_print_active_trays.get(serial, set()))


def register_printer(printer_id: int, serial: str) -> None:
    """Called when a printer config with a bambu_serial is saved."""
    _serial_to_printer_id[serial] = printer_id


def cancel_pending_2fa() -> None:
    """Cancel a pending 2FA flow; reset to disconnected without deleting credentials."""
    global _reauth_in_progress
    _pending.clear()
    _reauth_in_progress = False
    _status["status"] = "disconnected"
    _status["error"] = None
    log.info("Bambu Cloud: 2FA cancelled")


def get_debug_info() -> dict:
    """Return diagnostic snapshot of MQTT connection state and caches."""
    creds = _load_credentials()
    token_info: dict = {}
    if creds and creds.get("token"):
        payload = _jwt_payload(creds["token"])
        exp = payload.get("exp")
        token_info = {
            "uid": payload.get("uid") or payload.get("sub"),
            "exp": exp,
            "expired": (exp is not None and exp < __import__("time").time()),
            "saved_at": creds.get("saved_at"),
        }

    clients_info = {}
    for serial, client in _mqtt_clients.items():
        try:
            connected = client.is_connected()
        except AttributeError:
            # paho < 1.5 doesn't have is_connected()
            connected = getattr(client, "_state", None) == 2  # CONNECTED = 2
        clients_info[serial] = {
            "connected": connected,
            "printer_id": _serial_to_printer_id.get(serial),
        }

    return {
        "status": _status,
        "token": token_info,
        "mqtt_clients": clients_info,
        "printer_status_cache": dict(_printer_status_cache),
        "ams_cache": dict(_ams_cache),
        "serial_to_printer_id": dict(_serial_to_printer_id),
    }


async def reconnect() -> None:
    """Force re-read credentials and restart all MQTT connections."""
    global _reauth_in_progress
    creds = _load_credentials()
    if not creds:
        raise Exception("No saved credentials")
    email = creds.get("email", "")
    token = creds.get("token", "")
    if not email or not token:
        raise Exception("Credentials incomplete")
    if _is_token_valid(token):
        await _connect_mqtt_for_cloud_printers(email, token)
    else:
        log.info("Bambu Cloud reconnect: token expired, re-authenticating")
        _reauth_in_progress = True
        await _reauthenticate()


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _connect_mqtt_for_cloud_printers(email: str, token: str) -> None:
    """Query DB for all printers with a Bambu serial and start MQTT for each.

    MQTT is started for every active printer that has a bambu_serial set,
    regardless of bambu_source.  The bambu_source flag controls which data
    is used for print tracking; the MQTT connection is needed for the
    Experiments tab to show live cloud data even when the printer is still
    configured to use HA entities for tracking.

    Awaits all executor tasks so that every _start_mqtt_for_serial call
    completes (client created + stored in _mqtt_clients) before returning.
    This ensures _reauth_in_progress is only cleared after the new clients
    are registered, closing the race window where a stale rc=5 callback
    could restart the re-auth cycle.
    """
    from .database import SessionLocal
    from .models import PrinterConfig

    db = SessionLocal()
    try:
        printers = (
            db.query(PrinterConfig)
            .filter(PrinterConfig.bambu_serial != None)  # noqa: E711
            .filter(PrinterConfig.is_active == True)    # noqa: E712
            .all()
        )
        loop = asyncio.get_event_loop()
        tasks = []
        for p in printers:
            _serial_to_printer_id[p.bambu_serial] = p.id
            serial = p.bambu_serial
            tasks.append(loop.run_in_executor(
                None,
                lambda s=serial: _start_mqtt_for_serial(s, email, token),
            ))
        if tasks:
            await asyncio.gather(*tasks)
    finally:
        db.close()
