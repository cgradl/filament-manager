"""
Tests for the Filament Sync router — _subtype_from_cloud_name(),
_color_name_from_cloud_note(), and the apply_sync import-from-cloud path.

Issue #67: pulling a cloud filament whose display name carries variant info
beyond the base material (e.g. a custom BambuStudio "Serial" field producing
filamentName="PLA Recycled" for filamentType="PLA") lost that variant on
import — it was dumped into notes instead of subtype — and lost it a second
time when the spool was later pushed back (the automatic weight sync
recomposes filamentName from material+subtype+subtype2, so a blank subtype
silently drops "Recycled" from the cloud record on every subsequent sync).

Issue #70: Bambu Cloud has no dedicated color-name field, so a cloud import
always left color_name="" even for spools this app had itself pushed (which
embed color_name in the cloud note field as a workaround). The import path
never parsed that back out.
"""
from unittest.mock import AsyncMock, patch

from app.routers.filament_sync import (
    _subtype_from_cloud_name, _cloud_filament_name,
    _color_name_from_cloud_note, _local_to_cloud_body,
)
from app.models import Spool


# ---------------------------------------------------------------------------
# _subtype_from_cloud_name — unit tests
# ---------------------------------------------------------------------------

class TestSubtypeFromCloudName:
    def test_variant_beyond_material_extracted(self):
        assert _subtype_from_cloud_name("PLA Recycled", "PLA") == "Recycled"

    def test_multi_word_variant_kept_whole(self):
        assert _subtype_from_cloud_name("PETG High Speed Matte", "PETG") == "High Speed Matte"

    def test_exact_material_match_has_no_variant(self):
        assert _subtype_from_cloud_name("PLA", "PLA") == ""

    def test_multi_word_material_stripped_correctly(self):
        # material itself contains a space (e.g. local material list has "PLA Silk")
        assert _subtype_from_cloud_name("PLA Silk Basic", "PLA Silk") == "Basic"

    def test_false_prefix_not_corrupted(self):
        # "PLAX" is not "PLA " followed by a word boundary — must not become "X Something"
        assert _subtype_from_cloud_name("PLAX Something", "PLA") == "PLAX Something"

    def test_hyphenated_material_not_confused_with_prefix(self):
        # filamentType="PLA-CF" is a distinct material from "PLA" — no false partial match
        assert _subtype_from_cloud_name("PLA-CF Basic", "PLA-CF") == "Basic"

    def test_empty_filament_name(self):
        assert _subtype_from_cloud_name("", "PLA") == ""

    def test_empty_material_keeps_whole_name(self):
        assert _subtype_from_cloud_name("PLA Recycled", "") == "PLA Recycled"

    def test_case_insensitive_material_match(self):
        assert _subtype_from_cloud_name("pla Recycled", "PLA") == "Recycled"


# ---------------------------------------------------------------------------
# _color_name_from_cloud_note — unit tests
# ---------------------------------------------------------------------------

class TestColorNameFromCloudNote:
    def test_separator_present_splits_name_and_notes(self):
        assert _color_name_from_cloud_note("Black — Bought at the hardware store") == \
            ("Black", "Bought at the hardware store")

    def test_separator_with_empty_notes_tail(self):
        # what _local_to_cloud_body() writes when the spool has no local notes
        assert _color_name_from_cloud_note("Red — ") == ("Red", "")

    def test_no_separator_is_left_completely_untouched(self):
        # a genuine free-text Bambu note this app never wrote — must not be
        # mis-parsed as a color name
        note = "Bought at the hardware store"
        assert _color_name_from_cloud_note(note) == ("", note)

    def test_empty_note(self):
        assert _color_name_from_cloud_note("") == ("", "")


class TestRoundTrip:
    """The core regression for issue #67: pull then push must recover the
    original cloud filamentName instead of dropping the variant."""

    def test_pulled_subtype_recomposes_original_cloud_name(self):
        subtype = _subtype_from_cloud_name("PLA Recycled", "PLA")
        spool = Spool(
            brand="Generic", material="PLA", subtype=subtype or None,
            color_name="Black", color_hex="#000000",
            initial_weight_g=1000.0, current_weight_g=1000.0,
        )
        assert _cloud_filament_name(spool) == "PLA Recycled"

    def test_pushed_color_name_recovers_with_local_notes(self):
        """Issue #70: push a spool that has both a color and local notes,
        then confirm the cloud note this produces can be parsed back into
        the original color_name + notes."""
        spool = Spool(
            brand="Generic", material="PLA", color_name="Black", color_hex="#000000",
            notes="Bought at the hardware store",
            initial_weight_g=1000.0, current_weight_g=1000.0,
        )
        cloud_body = _local_to_cloud_body(spool)
        name, notes = _color_name_from_cloud_note(cloud_body["note"])
        assert name == "Black"
        assert notes == "Bought at the hardware store"

    def test_pushed_color_name_recovers_with_no_local_notes(self):
        """Same as above but with no local notes at all — the common case.
        Without the always-include-separator fix in _local_to_cloud_body(),
        this bare string would be indistinguishable from a foreign Bambu note
        and could never be safely recovered."""
        spool = Spool(
            brand="Generic", material="PLA", color_name="Red", color_hex="#FF0000",
            initial_weight_g=1000.0, current_weight_g=1000.0,
        )
        cloud_body = _local_to_cloud_body(spool)
        name, notes = _color_name_from_cloud_note(cloud_body["note"])
        assert name == "Red"
        assert notes == ""


# ---------------------------------------------------------------------------
# apply_sync — import_from_cloud integration
# ---------------------------------------------------------------------------

def _apply(client, **overrides):
    body = {
        "confirmed_matches": [],
        "import_from_cloud": [],
        "push_to_cloud": [],
        "deleted_actions": [],
    }
    body.update(overrides)
    return client.post("/api/filament-sync/apply", json=body)


class TestImportFromCloud:
    def _patch_cloud(self, cloud_spools):
        return (
            patch("app.bambu_cloud_client.get_status", return_value={"status": "connected"}),
            patch("app.bambu_cloud_client.list_all_filaments", new_callable=AsyncMock, return_value=cloud_spools),
        )

    def test_variant_stored_in_subtype_not_notes(self, client, session):
        cloud = [{
            "id": 42,
            "filamentVendor": "Generic",
            "filamentType": "PLA",
            "filamentName": "PLA Recycled",
            "note": "Bought at the hardware store",
            "color": "000000",
            "totalNetWeight": 1000,
            "netWeight": 1000,
        }]
        p_status, p_list = self._patch_cloud(cloud)
        with p_status, p_list:
            r = _apply(client, import_from_cloud=["42"])

        assert r.status_code == 200
        assert r.json()["imported"] == 1

        spool = session.query(Spool).filter(Spool.bambu_spool_id == "42").one()
        assert spool.material == "PLA"
        assert spool.subtype == "Recycled"
        assert spool.notes == "Bought at the hardware store"

    def test_color_name_recovered_from_round_tripped_note(self, client, session):
        """Issue #70: a note in this app's own "{color_name} — {notes}" format
        (i.e. a spool it previously pushed) must have color_name recovered on
        import, with the remainder preserved in notes."""
        cloud = [{
            "id": 55,
            "filamentVendor": "Generic",
            "filamentType": "PLA",
            "filamentName": "PLA",
            "note": "Black — Bought at the hardware store",
            "color": "000000",
            "totalNetWeight": 1000,
            "netWeight": 1000,
        }]
        p_status, p_list = self._patch_cloud(cloud)
        with p_status, p_list:
            r = _apply(client, import_from_cloud=["55"])

        assert r.status_code == 200
        spool = session.query(Spool).filter(Spool.bambu_spool_id == "55").one()
        assert spool.color_name == "Black"
        assert spool.notes == "Bought at the hardware store"

    def test_foreign_note_without_separator_leaves_color_name_blank(self, client, session):
        """A note this app never wrote (no " — " separator) has no reliable
        color name to extract — must stay untouched, exactly as before."""
        cloud = [{
            "id": 56,
            "filamentVendor": "Bambu Lab",
            "filamentType": "PLA",
            "filamentName": "PLA Basic",
            "note": "Bought at the hardware store",
            "color": "FFFFFF",
            "totalNetWeight": 1000,
            "netWeight": 1000,
        }]
        p_status, p_list = self._patch_cloud(cloud)
        with p_status, p_list:
            r = _apply(client, import_from_cloud=["56"])

        assert r.status_code == 200
        spool = session.query(Spool).filter(Spool.bambu_spool_id == "56").one()
        assert spool.color_name == ""
        assert spool.notes == "Bought at the hardware store"

    def test_no_variant_leaves_subtype_blank(self, client, session):
        cloud = [{
            "id": 7,
            "filamentVendor": "Bambu Lab",
            "filamentType": "PETG",
            "filamentName": "PETG",
            "color": "FF0000",
            "totalNetWeight": 1000,
            "netWeight": 1000,
        }]
        p_status, p_list = self._patch_cloud(cloud)
        with p_status, p_list:
            r = _apply(client, import_from_cloud=["7"])

        assert r.status_code == 200
        spool = session.query(Spool).filter(Spool.bambu_spool_id == "7").one()
        assert spool.subtype is None
        assert spool.notes == ""

    def test_missing_cloud_note_leaves_notes_empty(self, client, session):
        # No "note" key in the cloud payload at all — must not fall back to filamentName
        cloud = [{
            "id": 9,
            "filamentVendor": "Bambu Lab",
            "filamentType": "PLA",
            "filamentName": "PLA Basic",
            "color": "FFFFFF",
            "totalNetWeight": 1000,
            "netWeight": 1000,
        }]
        p_status, p_list = self._patch_cloud(cloud)
        with p_status, p_list:
            r = _apply(client, import_from_cloud=["9"])

        assert r.status_code == 200
        spool = session.query(Spool).filter(Spool.bambu_spool_id == "9").one()
        assert spool.subtype == "Basic"
        assert spool.notes == ""
