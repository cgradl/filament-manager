"""
Bambu Lab Cloud integration.

Handles:
- Email/password + 2FA authentication via bambu-lab-cloud-api
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
import json
import logging
import os
import stat
import threading
from datetime import datetime, timezone
from typing import Callable

from cryptography.fernet import Fernet
from fastapi import HTTPException

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

CRED_FILE = "/data/.bambu_cloud.json"
_2FA_TIMEOUT_SECONDS = 600  # 10 minutes

# ── Module-level state ────────────────────────────────────────────────────────

_status: dict = {
    "status": "disconnected",   # disconnected | pending_2fa | connected | error
    "email": None,
    "error": None,
}

# Temporarily holds login context during 2FA flow
_pending: dict = {}   # {email, password, initiated_at}

# serial → MQTTClient
_mqtt_clients: dict[str, object] = {}

# serial → last parsed printer status dict
_printer_status_cache: dict[str, dict] = {}

# serial → ams snapshot {slot_key: remain_pct}
_ams_cache: dict[str, dict[str, float]] = {}

# serial → printer_id (DB)
_serial_to_printer_id: dict[str, int] = {}

# Running asyncio event loop (stored at startup for thread-safe task scheduling)
_loop: asyncio.AbstractEventLoop | None = None


# ── Credential helpers ────────────────────────────────────────────────────────

def _save_credentials(email: str, password: str, token: str) -> None:
    key = Fernet.generate_key()
    f = Fernet(key)
    data = {
        "email": email,
        "password_enc": f.encrypt(password.encode()).decode(),
        "fernet_key": key.decode(),
        "token": token,
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


# ── MQTT helpers ──────────────────────────────────────────────────────────────

def _on_mqtt_message(device_id: str, data: dict) -> None:
    """
    Called from paho-mqtt's background thread.
    Parses payload, updates caches, and schedules print_monitor calls
    on the asyncio event loop thread-safely.
    """
    print_data = data.get("print", {})
    gcode_state = print_data.get("gcode_state", "")
    subtask_name = print_data.get("subtask_name", "")

    # Update AMS cache
    ams_raw = data.get("ams", {})
    if ams_raw:
        _parse_ams_into_cache(device_id, ams_raw)
    # Also handle ams nested under print
    ams_in_print = print_data.get("ams", {})
    if ams_in_print:
        _parse_ams_into_cache(device_id, ams_in_print)

    # Update general status cache
    _printer_status_cache[device_id] = {
        "gcode_state": gcode_state,
        "mc_percent": print_data.get("mc_percent"),
        "mc_remaining_time": print_data.get("mc_remaining_time"),
        "nozzle_temper": print_data.get("nozzle_temper"),
        "bed_temper": print_data.get("bed_temper"),
        "subtask_name": subtask_name,
    }

    if not gcode_state:
        return

    printer_id = _serial_to_printer_id.get(device_id)
    if printer_id is None:
        return

    state_upper = gcode_state.upper()

    if _loop is None:
        return

    # Import here to avoid circular import at module level
    from . import print_monitor

    if state_upper == "RUNNING":
        asyncio.run_coroutine_threadsafe(
            print_monitor.on_cloud_print_start(printer_id, subtask_name, device_id),
            _loop,
        )
    elif state_upper in ("FINISH", "FAILED", "IDLE"):
        success = state_upper != "FAILED"
        asyncio.run_coroutine_threadsafe(
            print_monitor.on_cloud_print_end(printer_id, success, state_upper),
            _loop,
        )


def _parse_ams_into_cache(serial: str, ams_raw: dict) -> None:
    snapshot: dict[str, float] = {}
    for unit in ams_raw.get("ams", []):
        ams_id = int(unit.get("id", 0)) + 1  # HA uses 1-based
        for tray in unit.get("tray", []):
            tray_id = int(tray.get("id", 0)) + 1  # 1-based
            remain = tray.get("remain")
            try:
                snapshot[f"ams{ams_id}_tray{tray_id}"] = float(remain)
            except (TypeError, ValueError):
                pass
    if snapshot:
        _ams_cache[serial] = snapshot


def _start_mqtt_for_serial(serial: str, email: str, token: str) -> None:
    """Start a non-blocking MQTT client for a device serial. Called from sync context."""
    if serial in _mqtt_clients:
        try:
            _mqtt_clients[serial].disconnect()
        except Exception:
            pass

    try:
        from bambulab.mqtt import MQTTClient

        def _cb(device_id: str, data: dict) -> None:
            _on_mqtt_message(device_id, data)

        client = MQTTClient(
            username=email,
            access_token=token,
            device_id=serial,
            on_message=_cb,
        )
        # connect in background thread — non-blocking
        t = threading.Thread(target=client.connect, kwargs={"blocking": True}, daemon=True)
        t.start()
        _mqtt_clients[serial] = client
        log.info("Bambu Cloud MQTT started for serial %s", serial)
        # Request a full status dump immediately
        try:
            client.request_full_status()
        except Exception:
            pass
    except Exception as exc:
        log.error("Failed to start MQTT for %s: %s", serial, exc)


# ── Public API ────────────────────────────────────────────────────────────────

async def startup() -> None:
    """Called from main.py lifespan. Reconnects if saved credentials exist."""
    global _loop
    _loop = asyncio.get_event_loop()

    creds = _load_credentials()
    if not creds:
        log.info("Bambu Cloud: no saved credentials, skipping auto-connect")
        return

    email = creds.get("email", "")
    token = creds.get("token", "")
    if not email or not token:
        return

    log.info("Bambu Cloud: reconnecting as %s", email)
    _status["status"] = "connected"
    _status["email"] = email
    _status["error"] = None

    # Reconnect MQTT for all cloud-source printers
    await _connect_mqtt_for_cloud_printers(email, token)


async def shutdown() -> None:
    """Cleanly disconnect all MQTT clients."""
    for serial, client in list(_mqtt_clients.items()):
        try:
            client.disconnect()
            log.info("Bambu Cloud MQTT disconnected for %s", serial)
        except Exception:
            pass
    _mqtt_clients.clear()


async def begin_login(email: str, password: str) -> dict:
    """
    Start the login flow. Stores pending context and initiates 2FA by
    calling BambuAuthenticator.login() in a thread (it's synchronous).

    The library sends a 2FA email then invokes the code_callback we pass.
    We use a threading.Event to pause that callback until verify_2fa() is called.
    Returns {"requires_2fa": True} immediately so the frontend can show the code form.
    """
    global _pending

    _pending = {
        "email": email,
        "password": password,
        "initiated_at": datetime.now(timezone.utc),
        "code_event": threading.Event(),
        "code_value": None,
        "result_event": threading.Event(),
        "result_token": None,
        "result_error": None,
    }
    _status["status"] = "pending_2fa"
    _status["email"] = email
    _status["error"] = None

    # Run the blocking login in a thread
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _run_login_in_thread)

    return {"requires_2fa": True}


def _run_login_in_thread() -> None:
    """Blocking login call — runs in executor thread."""
    try:
        from bambulab.auth import BambuAuthenticator, BambuAuthError

        auth = BambuAuthenticator(region="global")

        def code_callback() -> str:
            log.info("Bambu Cloud: waiting for 2FA code from user")
            got_code = _pending["code_event"].wait(timeout=_2FA_TIMEOUT_SECONDS)
            if not got_code or not _pending.get("code_value"):
                raise RuntimeError("2FA timeout — code not received")
            return _pending["code_value"]

        token = auth.login(
            _pending["email"],
            _pending["password"],
            code_callback=code_callback,
        )
        _pending["result_token"] = token
    except Exception as exc:
        _pending["result_error"] = str(exc)
    finally:
        _pending["result_event"].set()


async def verify_2fa(code: str) -> None:
    """
    Submit the 2FA code. Unblocks the login thread, waits for result,
    then persists credentials and starts MQTT.
    """
    if not _pending or _status["status"] != "pending_2fa":
        raise HTTPException(400, "No pending login — start login first")

    initiated = _pending.get("initiated_at")
    if initiated:
        age = (datetime.now(timezone.utc) - initiated).total_seconds()
        if age > _2FA_TIMEOUT_SECONDS:
            _status["status"] = "disconnected"
            raise HTTPException(408, "2FA session expired — please log in again")

    _pending["code_value"] = code
    _pending["code_event"].set()

    # Wait for the login thread to finish (up to 30s)
    loop = asyncio.get_event_loop()
    done = await loop.run_in_executor(
        None,
        lambda: _pending["result_event"].wait(timeout=30),
    )

    if not done or _pending.get("result_error"):
        err = _pending.get("result_error", "Unknown error")
        _status["status"] = "error"
        _status["error"] = err
        raise HTTPException(400, f"Login failed: {err}")

    token = _pending["result_token"]
    email = _pending["email"]
    password = _pending["password"]

    _save_credentials(email, password, token)
    _status["status"] = "connected"
    _status["email"] = email
    _status["error"] = None

    await _connect_mqtt_for_cloud_printers(email, token)
    log.info("Bambu Cloud: login complete for %s", email)


async def logout() -> None:
    """Disconnect MQTT, delete credentials, reset state."""
    await shutdown()
    _delete_credentials()
    _status["status"] = "disconnected"
    _status["email"] = None
    _status["error"] = None
    _serial_to_printer_id.clear()
    _printer_status_cache.clear()
    _ams_cache.clear()
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
        from bambulab.client import BambuClient
        client = BambuClient(token=creds["token"])
        raw = client.get_devices()
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
    return dict(_ams_cache.get(serial, {}))


def register_printer(printer_id: int, serial: str) -> None:
    """Called when a printer config is saved with bambu_source='cloud'."""
    _serial_to_printer_id[serial] = printer_id


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _connect_mqtt_for_cloud_printers(email: str, token: str) -> None:
    """Query DB for all cloud-source printers and start MQTT for each."""
    from .database import SessionLocal
    from .models import PrinterConfig

    db = SessionLocal()
    try:
        printers = (
            db.query(PrinterConfig)
            .filter(PrinterConfig.bambu_source == "cloud")
            .filter(PrinterConfig.bambu_serial != None)  # noqa: E711
            .filter(PrinterConfig.is_active == True)  # noqa: E712
            .all()
        )
        for p in printers:
            _serial_to_printer_id[p.bambu_serial] = p.id
            loop = asyncio.get_event_loop()
            serial = p.bambu_serial
            loop.run_in_executor(
                None,
                lambda s=serial: _start_mqtt_for_serial(s, email, token),
            )
    finally:
        db.close()
