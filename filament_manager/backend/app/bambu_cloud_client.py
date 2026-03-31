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

# serial → printer_id (DB)
_serial_to_printer_id: dict[str, int] = {}

# Running asyncio event loop (stored at startup for thread-safe task scheduling)
_loop: asyncio.AbstractEventLoop | None = None


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


def _mqtt_username(email: str, token: str) -> str:
    uid = _jwt_uid(token)
    return f"u_{uid}" if uid else email


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


# ── MQTT helpers ──────────────────────────────────────────────────────────────

def _process_device_message(serial: str, data: dict) -> None:
    """Parse MQTT payload, update caches, schedule print_monitor calls."""
    print_data = data.get("print", {})
    gcode_state = print_data.get("gcode_state", "")
    subtask_name = print_data.get("subtask_name", "")

    # Update AMS cache from top-level or nested ams object
    for ams_source in (data.get("ams", {}), print_data.get("ams", {})):
        if ams_source:
            _parse_ams_into_cache(serial, ams_source)

    # Update general status cache
    _printer_status_cache[serial] = {
        "gcode_state": gcode_state,
        "mc_percent": print_data.get("mc_percent"),
        "mc_remaining_time": print_data.get("mc_remaining_time"),
        "nozzle_temper": print_data.get("nozzle_temper"),
        "bed_temper": print_data.get("bed_temper"),
        "subtask_name": subtask_name,
    }

    if not gcode_state or _loop is None:
        return

    printer_id = _serial_to_printer_id.get(serial)
    if printer_id is None:
        return

    # Import here to avoid circular import at module level
    from . import print_monitor

    state_upper = gcode_state.upper()
    if state_upper == "RUNNING":
        asyncio.run_coroutine_threadsafe(
            print_monitor.on_cloud_print_start(printer_id, subtask_name, serial),
            _loop,
        )
    elif state_upper in ("FINISH", "FAILED", "IDLE"):
        asyncio.run_coroutine_threadsafe(
            print_monitor.on_cloud_print_end(printer_id, state_upper != "FAILED", state_upper),
            _loop,
        )


def _parse_ams_into_cache(serial: str, ams_raw: dict) -> None:
    snapshot: dict[str, dict] = {}
    for unit in ams_raw.get("ams", []):
        ams_id = int(unit.get("id", 0)) + 1   # 1-based
        for tray in unit.get("tray", []):
            tray_id = int(tray.get("id", 0)) + 1  # 1-based
            remain = tray.get("remain")
            try:
                remain_f = float(remain)
            except (TypeError, ValueError):
                continue
            # Bambu sends color as RRGGBBAA hex — take only the RGB part
            color_raw = str(tray.get("tray_color") or tray.get("color") or "").strip()
            color_hex = f"#{color_raw[:6]}" if len(color_raw) >= 6 else None
            material = tray.get("tray_type") or tray.get("type") or None
            snapshot[f"ams{ams_id}_tray{tray_id}"] = {
                "remain":   remain_f,
                "material": material,
                "color":    color_hex,
            }
    if snapshot:
        _ams_cache[serial] = snapshot


def _start_mqtt_for_serial(serial: str, email: str, token: str) -> None:
    """Create and start a non-blocking paho MQTT client for a device serial."""
    if serial in _mqtt_clients:
        try:
            _mqtt_clients[serial].loop_stop()
            _mqtt_clients[serial].disconnect()
        except Exception:
            pass

    try:
        username = _mqtt_username(email, token)
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
            if rc == 0:
                topic = f"device/{serial}/report"
                c.subscribe(topic, qos=0)
                log.info("Bambu Cloud MQTT connected for %s", serial)
                # Request a full status push immediately
                c.publish(
                    f"device/{serial}/request",
                    json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}),
                    qos=0,
                )
            else:
                log.error("Bambu Cloud MQTT connect failed for %s, rc=%d", serial, rc)

        def on_message(c, userdata, msg):
            try:
                data = json.loads(msg.payload)
            except Exception:
                return
            _process_device_message(serial, data)

        def on_disconnect(c, userdata, rc):
            log.warning("Bambu Cloud MQTT disconnected for %s, rc=%d", serial, rc)

        client.on_connect = on_connect
        client.on_message = on_message
        client.on_disconnect = on_disconnect

        client.connect_async(MQTT_HOST, MQTT_PORT)
        client.loop_start()  # background thread — non-blocking

        _mqtt_clients[serial] = client
        log.info("Bambu Cloud MQTT client started for serial %s", serial)
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

    await _connect_mqtt_for_cloud_printers(email, token)


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

    _save_credentials(email, password, token)
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

    _save_credentials(email, password, token)
    _status["status"] = "connected"
    _status["email"] = email
    _status["error"] = None
    _pending.clear()

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
    _pending.clear()
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
            .filter(PrinterConfig.is_active == True)    # noqa: E712
            .all()
        )
        for p in printers:
            _serial_to_printer_id[p.bambu_serial] = p.id
            serial = p.bambu_serial
            asyncio.get_event_loop().run_in_executor(
                None,
                lambda s=serial: _start_mqtt_for_serial(s, email, token),
            )
    finally:
        db.close()
