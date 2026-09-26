"""
Integration tests for /api/spools endpoints.
Covers CRUD, material filter, brand-weight auto-resolution,
and the materials/subtypes list endpoints.
"""
import pytest
from tests.conftest import make_spool_payload
from app.models import BrandSpoolWeight, FilamentMaterial, FilamentSubtype, Spool


# ---------------------------------------------------------------------------
# GET /api/spools
# ---------------------------------------------------------------------------

class TestListSpools:
    def test_empty_returns_list(self, client):
        r = client.get("/api/spools")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_created_spools(self, client):
        client.post("/api/spools", json=make_spool_payload())
        client.post("/api/spools", json=make_spool_payload(color_name="Blue"))
        r = client.get("/api/spools")
        assert len(r.json()) == 2

    def test_filter_by_material(self, client):
        client.post("/api/spools", json=make_spool_payload(material="PLA"))
        client.post("/api/spools", json=make_spool_payload(material="PETG"))
        r = client.get("/api/spools?material=PLA")
        assert r.status_code == 200
        results = r.json()
        assert len(results) == 1
        assert results[0]["material"] == "PLA"

    def test_filter_by_material_no_match(self, client):
        client.post("/api/spools", json=make_spool_payload(material="PLA"))
        r = client.get("/api/spools?material=ABS")
        assert r.json() == []

    def test_ordered_by_brand_then_material(self, client):
        client.post("/api/spools", json=make_spool_payload(brand="Zylon", material="PLA"))
        client.post("/api/spools", json=make_spool_payload(brand="Bambu Lab", material="PETG"))
        results = client.get("/api/spools").json()
        assert results[0]["brand"] == "Bambu Lab"
        assert results[1]["brand"] == "Zylon"


# ---------------------------------------------------------------------------
# POST /api/spools
# ---------------------------------------------------------------------------

class TestCreateSpool:
    def test_create_returns_201(self, client):
        r = client.post("/api/spools", json=make_spool_payload())
        assert r.status_code == 201

    def test_create_returns_id(self, client):
        r = client.post("/api/spools", json=make_spool_payload())
        assert "id" in r.json()
        assert r.json()["id"] > 0

    def test_create_stores_fields(self, client):
        payload = make_spool_payload(
            brand="SUNLU",
            material="PETG",
            color_name="Green",
            color_hex="#00FF00",
            initial_weight_g=800.0,
            current_weight_g=800.0,
        )
        data = client.post("/api/spools", json=payload).json()
        assert data["brand"] == "SUNLU"
        assert data["material"] == "PETG"
        assert data["color_name"] == "Green"
        assert data["initial_weight_g"] == 800.0

    def test_create_includes_remaining_pct(self, client):
        data = client.post("/api/spools", json=make_spool_payload(
            initial_weight_g=1000, current_weight_g=500
        )).json()
        assert data["remaining_pct"] == 50.0

    def test_create_defaults_is_refill_pack_false(self, client):
        data = client.post("/api/spools", json=make_spool_payload()).json()
        assert data["is_refill_pack"] is False

    def test_create_is_refill_pack_true(self, client):
        data = client.post("/api/spools", json=make_spool_payload(is_refill_pack=True)).json()
        assert data["is_refill_pack"] is True

    def test_create_resolves_spool_weight_from_brand(self, client, session):
        # Seed a brand weight
        session.add(BrandSpoolWeight(brand="Bambu Lab", spool_weight_g=250.0))
        session.commit()

        data = client.post("/api/spools", json=make_spool_payload(brand="Bambu Lab")).json()
        assert data["spool_weight_g"] == 250.0

    def test_create_spool_weight_zero_when_brand_unknown(self, client):
        data = client.post("/api/spools", json=make_spool_payload(brand="NoSuchBrand")).json()
        assert data["spool_weight_g"] == 0.0

    def test_create_brand_weight_case_insensitive(self, client, session):
        session.add(BrandSpoolWeight(brand="bambu lab", spool_weight_g=250.0))
        session.commit()

        data = client.post("/api/spools", json=make_spool_payload(brand="BAMBU LAB")).json()
        assert data["spool_weight_g"] == 250.0

    def test_create_missing_required_field_returns_422(self, client):
        payload = make_spool_payload()
        del payload["brand"]
        r = client.post("/api/spools", json=payload)
        assert r.status_code == 422

    def test_create_with_purchase_price(self, client):
        data = client.post("/api/spools", json=make_spool_payload(
            purchase_price=19.99
        )).json()
        assert data["purchase_price"] == 19.99
        assert data["price_per_kg"] == pytest.approx(19.99, abs=0.01)

    def test_create_with_optional_fields(self, client):
        data = client.post("/api/spools", json=make_spool_payload(
            notes="Test notes",
            purchase_location="Amazon",
            subtype="Matte",
        )).json()
        assert data["notes"] == "Test notes"
        assert data["purchase_location"] == "Amazon"
        assert data["subtype"] == "Matte"


# ---------------------------------------------------------------------------
# GET /api/spools/{id}
# ---------------------------------------------------------------------------

class TestGetSpool:
    def test_get_existing_spool(self, client):
        spool_id = client.post("/api/spools", json=make_spool_payload()).json()["id"]
        r = client.get(f"/api/spools/{spool_id}")
        assert r.status_code == 200
        assert r.json()["id"] == spool_id

    def test_get_nonexistent_returns_404(self, client):
        r = client.get("/api/spools/9999")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/spools/{id}
# ---------------------------------------------------------------------------

class TestUpdateSpool:
    def test_update_color(self, client):
        spool_id = client.post("/api/spools", json=make_spool_payload()).json()["id"]
        r = client.patch(f"/api/spools/{spool_id}", json={"color_name": "Blue"})
        assert r.status_code == 200
        assert r.json()["color_name"] == "Blue"

    def test_update_is_refill_pack(self, client):
        spool_id = client.post("/api/spools", json=make_spool_payload()).json()["id"]
        r = client.patch(f"/api/spools/{spool_id}", json={"is_refill_pack": True})
        assert r.status_code == 200
        assert r.json()["is_refill_pack"] is True

    def test_update_partial(self, client):
        spool_id = client.post("/api/spools", json=make_spool_payload()).json()["id"]
        r = client.patch(f"/api/spools/{spool_id}", json={"notes": "Updated notes"})
        assert r.status_code == 200
        data = r.json()
        assert data["notes"] == "Updated notes"
        assert data["brand"] == "Bambu Lab"  # unchanged

    def test_update_rerenders_remaining_pct(self, client):
        spool_id = client.post("/api/spools", json=make_spool_payload(
            initial_weight_g=1000, current_weight_g=1000
        )).json()["id"]
        r = client.patch(f"/api/spools/{spool_id}", json={"current_weight_g": 750.0})
        assert r.json()["remaining_pct"] == 75.0

    def test_update_rerenders_spool_weight_from_brand(self, client, session):
        session.add(BrandSpoolWeight(brand="SUNLU", spool_weight_g=225.0))
        session.commit()
        spool_id = client.post("/api/spools", json=make_spool_payload(brand="Bambu Lab")).json()["id"]
        r = client.patch(f"/api/spools/{spool_id}", json={"brand": "SUNLU"})
        assert r.json()["spool_weight_g"] == 225.0

    def test_update_unrelated_field_preserves_spool_weight_g(self, client, session):
        """Issue #71: an unrelated PATCH must not silently reset spool_weight_g
        back to the current brand-config tare."""
        session.add(BrandSpoolWeight(brand="SUNLU", spool_weight_g=225.0))
        session.commit()
        spool_id = client.post("/api/spools", json=make_spool_payload(brand="SUNLU")).json()["id"]
        # Simulate a pre-existing/legacy stored value that differs from the
        # current brand config (e.g. the brand tare was changed after creation).
        spool = session.get(Spool, spool_id)
        spool.spool_weight_g = 300.0
        session.commit()

        r = client.patch(f"/api/spools/{spool_id}", json={"color_name": "Matt White"})
        assert r.status_code == 200
        assert r.json()["color_name"] == "Matt White"
        assert r.json()["spool_weight_g"] == 300.0

    def test_update_same_brand_preserves_spool_weight_g(self, client, session):
        """Issue #71: PATCHing brand to its current value (not actually
        changing it) must not re-resolve and overwrite a custom spool_weight_g."""
        session.add(BrandSpoolWeight(brand="SUNLU", spool_weight_g=225.0))
        session.commit()
        spool_id = client.post("/api/spools", json=make_spool_payload(brand="SUNLU")).json()["id"]
        spool = session.get(Spool, spool_id)
        spool.spool_weight_g = 300.0
        session.commit()

        r = client.patch(f"/api/spools/{spool_id}", json={"brand": "SUNLU"})
        assert r.json()["spool_weight_g"] == 300.0

    def test_update_cannot_set_spool_weight_g_directly(self, client, session):
        """spool_weight_g stays derived-only — a client-supplied value in a
        PATCH with no brand change must be ignored, not applied."""
        session.add(BrandSpoolWeight(brand="SUNLU", spool_weight_g=225.0))
        session.commit()
        spool_id = client.post("/api/spools", json=make_spool_payload(brand="SUNLU")).json()["id"]
        r = client.patch(f"/api/spools/{spool_id}", json={"spool_weight_g": 999.0})
        assert r.json()["spool_weight_g"] == 225.0

    def test_update_nonexistent_returns_404(self, client):
        r = client.patch("/api/spools/9999", json={"color_name": "Blue"})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/spools/{id}
# ---------------------------------------------------------------------------

class TestDeleteSpool:
    def test_delete_returns_204(self, client):
        spool_id = client.post("/api/spools", json=make_spool_payload()).json()["id"]
        r = client.delete(f"/api/spools/{spool_id}")
        assert r.status_code == 204

    def test_delete_removes_spool(self, client):
        spool_id = client.post("/api/spools", json=make_spool_payload()).json()["id"]
        client.delete(f"/api/spools/{spool_id}")
        r = client.get(f"/api/spools/{spool_id}")
        assert r.status_code == 404

    def test_delete_nonexistent_returns_404(self, client):
        r = client.delete("/api/spools/9999")
        assert r.status_code == 404

    def test_delete_only_removes_target(self, client):
        id1 = client.post("/api/spools", json=make_spool_payload()).json()["id"]
        id2 = client.post("/api/spools", json=make_spool_payload(color_name="Blue")).json()["id"]
        client.delete(f"/api/spools/{id1}")
        assert client.get(f"/api/spools/{id2}").status_code == 200


# ---------------------------------------------------------------------------
# GET /api/spools/materials/list
# GET /api/spools/subtypes/list
# ---------------------------------------------------------------------------

class TestListEndpoints:
    def test_materials_list_empty(self, client):
        r = client.get("/api/spools/materials/list")
        assert r.status_code == 200
        assert r.json() == []

    def test_materials_list_returns_names(self, client, session):
        session.add(FilamentMaterial(name="PLA"))
        session.add(FilamentMaterial(name="PETG"))
        session.commit()
        r = client.get("/api/spools/materials/list")
        assert sorted(r.json()) == ["PETG", "PLA"]

    def test_subtypes_list_empty(self, client):
        r = client.get("/api/spools/subtypes/list")
        assert r.status_code == 200
        assert r.json() == []

    def test_subtypes_list_returns_names(self, client, session):
        session.add(FilamentSubtype(name="Matte"))
        session.add(FilamentSubtype(name="Silk"))
        session.commit()
        r = client.get("/api/spools/subtypes/list")
        assert sorted(r.json()) == ["Matte", "Silk"]


class TestSpoolValidation:
    """Input validation added on SpoolCreate/SpoolUpdate (422 on garbage)."""

    def test_create_negative_initial_weight_rejected(self, client):
        r = client.post("/api/spools", json=make_spool_payload(initial_weight_g=-100))
        assert r.status_code == 422

    def test_create_zero_initial_weight_rejected(self, client):
        r = client.post("/api/spools", json=make_spool_payload(initial_weight_g=0))
        assert r.status_code == 422

    def test_create_negative_current_weight_rejected(self, client):
        r = client.post("/api/spools", json=make_spool_payload(current_weight_g=-1))
        assert r.status_code == 422

    def test_create_custom_id_out_of_range_rejected(self, client):
        assert client.post("/api/spools", json=make_spool_payload(custom_id=0)).status_code == 422
        assert client.post("/api/spools", json=make_spool_payload(custom_id=10000)).status_code == 422

    def test_create_malformed_hex_rejected(self, client):
        assert client.post("/api/spools", json=make_spool_payload(color_hex="16161")).status_code == 422
        assert client.post("/api/spools", json=make_spool_payload(color_hex="FF0000")).status_code == 422  # missing '#'

    def test_update_negative_weight_rejected(self, client):
        spool = client.post("/api/spools", json=make_spool_payload()).json()
        r = client.patch(f"/api/spools/{spool['id']}", json={"current_weight_g": -5})
        assert r.status_code == 422

    def test_create_valid_payload_still_works(self, client):
        r = client.post("/api/spools", json=make_spool_payload(custom_id=42, color_hex="#A1B2C3"))
        assert r.status_code == 201


class TestSpoolDeleteCascade:
    """foreign_keys=ON: deleting a spool must cascade its audit rows."""

    def test_delete_spool_removes_audit_rows(self, client, session):
        from app.models import SpoolAudit
        spool = client.post("/api/spools", json=make_spool_payload()).json()
        # Weight edit creates an audit row
        client.patch(f"/api/spools/{spool['id']}", json={"current_weight_g": 900})
        assert session.query(SpoolAudit).filter_by(spool_id=spool["id"]).count() == 1

        r = client.delete(f"/api/spools/{spool['id']}")
        assert r.status_code == 204
        session.expire_all()
        assert session.query(SpoolAudit).filter_by(spool_id=spool["id"]).count() == 0
