"""
Tests for the bambu_cloud router helpers and the 2FA verification flow.
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import HTTPException

from app.routers.bambu_cloud import _parse_task_time
from app.models import PrintJob


class TestParseTaskTime:
    def test_unix_seconds(self):
        assert _parse_task_time(1750000000) == datetime.fromtimestamp(1750000000, tz=timezone.utc).replace(tzinfo=None)

    def test_unix_milliseconds(self):
        # ms and s forms of the same instant must parse identically
        assert _parse_task_time(1750000000000) == _parse_task_time(1750000000)

    def test_unix_milliseconds_string(self):
        assert _parse_task_time("1750000000000") == _parse_task_time(1750000000)

    def test_iso_string_with_z(self):
        assert _parse_task_time("2026-04-16T05:45:54Z") == datetime(2026, 4, 16, 5, 45, 54)

    def test_garbage_returns_none(self):
        assert _parse_task_time("not-a-date") is None
        assert _parse_task_time(None) is None


class TestVerify2FARetry:
    """A wrong 2FA code must keep the flow in pending_2fa so the user can retry."""

    @pytest.fixture(autouse=True)
    def pending_login(self):
        from app import bambu_cloud_client as bcc
        saved_status = dict(bcc._status)
        bcc._pending.clear()
        bcc._pending.update({
            "email": "user@example.com", "password": "pw",
            "region": "us", "mode": "verifyCode",
        })
        bcc._status["status"] = "pending_2fa"
        bcc._status["error"] = None
        yield
        bcc._pending.clear()
        bcc._status.update(saved_status)

    @pytest.mark.asyncio
    async def test_wrong_code_keeps_pending_status(self):
        from app import bambu_cloud_client as bcc
        # Bambu returns 200 with a message but no accessToken on a wrong code
        with patch("app.bambu_cloud_client._http_login",
                   return_value={"message": "verification code error"}):
            with pytest.raises(HTTPException):
                await bcc.verify_2fa("000000")

        assert bcc._status["status"] == "pending_2fa"

    @pytest.mark.asyncio
    async def test_retry_after_wrong_code_reaches_login(self):
        from app import bambu_cloud_client as bcc
        with patch("app.bambu_cloud_client._http_login",
                   return_value={"message": "verification code error"}):
            with pytest.raises(HTTPException):
                await bcc.verify_2fa("000000")

        # Second attempt must NOT be rejected by the "No pending login" guard
        with patch("app.bambu_cloud_client._http_login",
                   return_value={"message": "verification code error"}) as mock_login:
            with pytest.raises(HTTPException) as exc_info:
                await bcc.verify_2fa("111111")
            mock_login.assert_called_once()
            assert "No pending login" not in str(exc_info.value.detail)


class TestImportCloudPrints:
    def _patch_cloud(self, tasks):
        async def fake_get_all_tasks():
            return tasks
        return (
            patch("app.bambu_cloud_client.get_all_tasks", fake_get_all_tasks),
            patch("app.bambu_cloud_client._load_credentials", return_value={"token": "t"}),
        )

    def test_import_maps_ams_ht_and_skips_external(self, client, session):
        task = {
            "id": 100,
            "startTime": 1750000000,
            "endTime": 1750003600,
            "deviceId": "SN1",
            "designTitle": "Benchy",
            "status": 4,
            "weight": 25.0,
            "amsDetailMapping": [
                {"ams": 1, "weight": 10.0, "filamentType": "PLA"},     # standard AMS → ams1_tray2
                {"ams": 128, "weight": 10.0, "filamentType": "PLA"},   # AMS HT (N3S) → ams129_tray1
                {"ams": 254, "weight": 5.0, "filamentType": "PLA"},    # external spool → skipped
            ],
        }
        p_tasks, p_creds = self._patch_cloud([task])
        with p_tasks, p_creds:
            resp = client.post("/api/bambu-cloud/import-prints")

        assert resp.status_code == 200
        assert resp.json()["imported"] == 1

        job = session.query(PrintJob).filter(PrintJob.task_id == "100").one()
        slots = {s["ams_slot"] for s in job.suggested_usages}
        # Old idx//4 formula produced the nonsense key "ams33_tray1" for index 128
        assert slots == {"ams1_tray2", "ams129_tray1"}
        assert len(job.usages) == 2

    def test_import_millisecond_start_time(self, client, session):
        task = {
            "id": 101,
            "startTime": 1750000000000,   # milliseconds
            "deviceId": "SN1",
            "title": "MS print",
            "status": 4,
        }
        p_tasks, p_creds = self._patch_cloud([task])
        with p_tasks, p_creds:
            resp = client.post("/api/bambu-cloud/import-prints")

        assert resp.status_code == 200
        job = session.query(PrintJob).filter(PrintJob.task_id == "101").one()
        assert job.started_at == datetime.fromtimestamp(1750000000, tz=timezone.utc).replace(tzinfo=None)
