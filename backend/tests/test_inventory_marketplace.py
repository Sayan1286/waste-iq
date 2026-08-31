from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _make_lot(
    db_session,
    *,
    lot_number: str,
    material_category,
    active_pricing_rule,
    admin_user,
    citizen_user,
    collector_user,
    weight_kg: float = 10.0,
    unit_price: float = 12.5,
    source_city: str = "Kolkata",
    status: str = "available",
    material_description: str = "Mixed recyclables",
):
    from app.models.collector_assignment import CollectorAssignment
    from app.models.inventory_lot import (
        InventoryLot,
        InventoryLotStatus,
        InventoryLotVisibility,
    )
    from app.models.pickup_request import PickupRequest, PickupStatus

    pickup = PickupRequest(
        user_id=citizen_user.id,
        waste_type=material_description,
        address=f"10 Test Road, {source_city}, 700001",
        latitude=22.5,
        longitude=88.3,
        status=PickupStatus.completed,
    )
    db_session.add(pickup)
    db_session.flush()

    assignment = CollectorAssignment(
        request_id=pickup.id,
        collector_id=collector_user.id,
        accepted_at=datetime.now(timezone.utc) - timedelta(hours=2),
        completed_at=datetime.now(timezone.utc),
        weight_kg=weight_kg,
    )
    db_session.add(assignment)
    db_session.flush()

    lot = InventoryLot(
        lot_number=lot_number,
        pickup_request_id=pickup.id,
        citizen_id=citizen_user.id,
        collector_id=collector_user.id,
        material_category_id=material_category.id,
        material_description=material_description,
        weight_kg=weight_kg,
        unit_price_per_kg_snapshot=unit_price,
        total_listed_amount=Decimal(str(round(weight_kg * unit_price, 2))),
        pricing_rule_id=active_pricing_rule.id,
        source_city=source_city,
        source_address_snapshot=pickup.address,
        status=InventoryLotStatus(status),
        visibility=InventoryLotVisibility.visible,
        created_by=admin_user.id,
        updated_by=admin_user.id,
    )

    db_session.add(lot)
    db_session.commit()
    db_session.refresh(lot)

    return lot


# ─── Permission gates ────────────────────────────────────────────────────────


def test_dealer_without_profile_cannot_list_marketplace_inventory(
    client: TestClient, dealer_headers: dict
):
    response = client.get("/marketplace/inventory", headers=dealer_headers)
    assert response.status_code == 403


def test_draft_dealer_cannot_list_marketplace_inventory(
    client: TestClient, dealer_headers: dict, draft_dealer_profile
):
    response = client.get("/marketplace/inventory", headers=dealer_headers)
    assert response.status_code == 403


def test_rejected_dealer_cannot_reserve_marketplace_inventory(
    client: TestClient,
    db_session: Session,
    dealer_user,
    dealer_headers: dict,
    inventory_lot,
):
    from app.models.dealer_profile import DealerApprovalStatus, DealerProfile

    profile = db_session.get(DealerProfile, dealer_user.id)
    if profile is None:
        profile = DealerProfile(
            user_id=dealer_user.id,
            business_name="Rejected Recyclers",
            owner_name="Rejected Owner",
            phone="9000000003",
            email="dealer@test.com",
            address="321 Rejected Lane, Kolkata",
            city="Kolkata",
            state="West Bengal",
            postal_code="700005",
            materials_accepted=["Paper"],
        )
        db_session.add(profile)

    profile.approval_status = DealerApprovalStatus.rejected
    db_session.commit()

    response = client.post(
        f"/marketplace/inventory/{inventory_lot.id}/reserve",
        headers=dealer_headers,
    )

    assert response.status_code == 403


def test_citizen_cannot_access_marketplace(
    client: TestClient, citizen_headers: dict, inventory_lot
):
    response = client.get("/marketplace/inventory", headers=citizen_headers)
    assert response.status_code == 403

    response = client.post(
        f"/marketplace/inventory/{inventory_lot.id}/purchase",
        headers=citizen_headers,
    )
    assert response.status_code == 403


def test_unauthenticated_request_rejected(client: TestClient):
    response = client.get("/marketplace/inventory")
    assert response.status_code == 401


def test_list_marketplace_inventory_shows_available_lots(
    client: TestClient,
    dealer_headers: dict,
    approved_dealer_profile,
    inventory_lot,
):
    response = client.get(
        "/marketplace/inventory",
        headers=dealer_headers,
    )

    assert response.status_code == 200

    body = response.json()

    assert body["total_items"] == 1

    item = body["items"][0]

    assert item["id"] == inventory_lot.id
    assert item["status"] == "available"
    assert item["material_category_name"] == "PET Plastic"
    assert item["weight_kg"] == 15.5
    assert item["unit_price_per_kg_snapshot"] == 12.5
    assert item["total_listed_amount"] == 193.75
    assert item["currency_code"] == "INR"
    assert item["seller_name"] == "Test User"
    assert item["is_reserved_by_me"] is False


def test_list_marketplace_inventory_hides_sold_lots(
    client: TestClient,
    db_session: Session,
    dealer_headers: dict,
    approved_dealer_profile,
    inventory_lot,
):
    from app.models.inventory_lot import InventoryLotStatus

    inventory_lot.status = InventoryLotStatus.sold
    db_session.commit()

    response = client.get(
        "/marketplace/inventory",
        headers=dealer_headers,
    )

    assert response.status_code == 200
    assert response.json()["total_items"] == 0


def test_list_marketplace_inventory_hides_hidden_lots(
    client: TestClient,
    db_session: Session,
    dealer_headers: dict,
    approved_dealer_profile,
    inventory_lot,
):
    from app.models.inventory_lot import InventoryLotVisibility

    inventory_lot.visibility = InventoryLotVisibility.hidden
    db_session.commit()

    response = client.get(
        "/marketplace/inventory",
        headers=dealer_headers,
    )

    assert response.status_code == 200
    assert response.json()["total_items"] == 0


def test_list_marketplace_inventory_filter_by_category(
    client: TestClient,
    db_session: Session,
    dealer_headers: dict,
    approved_dealer_profile,
    material_category,
    active_pricing_rule,
    admin_user,
    citizen_user,
    collector_user,
    inventory_lot,
):
    from app.models.material_category import MaterialCategory

    other_category = MaterialCategory(
        code="CARDBOARD",
        name="Cardboard",
        description="Boxes and cartons",
        is_active=True,
        display_order=2,
    )

    db_session.add(other_category)
    db_session.commit()
    db_session.refresh(other_category)

    _make_lot(
        db_session,
        lot_number="LOT-2026-000100",
        material_category=other_category,
        active_pricing_rule=active_pricing_rule,
        admin_user=admin_user,
        citizen_user=citizen_user,
        collector_user=collector_user,
        material_description="Cardboard boxes",
    )

    response = client.get(
        f"/marketplace/inventory?material_category_id={material_category.id}",
        headers=dealer_headers,
    )

    assert response.status_code == 200

    body = response.json()

    assert body["total_items"] == 1
    assert body["items"][0]["id"] == inventory_lot.id


def test_list_marketplace_inventory_filter_by_city(
    client: TestClient,
    db_session: Session,
    dealer_headers: dict,
    approved_dealer_profile,
    material_category,
    active_pricing_rule,
    admin_user,
    citizen_user,
    collector_user,
    inventory_lot,
):
    _make_lot(
        db_session,
        lot_number="LOT-2026-000101",
        material_category=material_category,
        active_pricing_rule=active_pricing_rule,
        admin_user=admin_user,
        citizen_user=citizen_user,
        collector_user=collector_user,
        source_city="Howrah",
    )

    response = client.get(
        "/marketplace/inventory?city=Howrah",
        headers=dealer_headers,
    )

    assert response.status_code == 200

    body = response.json()

    assert body["total_items"] == 1
    assert body["items"][0]["source_city"] == "Howrah"


def test_list_marketplace_inventory_search(
    client: TestClient,
    db_session: Session,
    dealer_headers: dict,
    approved_dealer_profile,
    material_category,
    active_pricing_rule,
    admin_user,
    citizen_user,
    collector_user,
    inventory_lot,
):
    _make_lot(
        db_session,
        lot_number="LOT-2026-000102",
        material_category=material_category,
        active_pricing_rule=active_pricing_rule,
        admin_user=admin_user,
        citizen_user=citizen_user,
        collector_user=collector_user,
        material_description="Aluminum cans",
    )

    response = client.get(
        "/marketplace/inventory?search=Aluminum",
        headers=dealer_headers,
    )

    assert response.status_code == 200

    body = response.json()

    assert body["total_items"] == 1
    assert body["items"][0]["material_description"] == "Aluminum cans"
