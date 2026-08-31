from datetime import datetime, timedelta, timezone

from app.models.inventory_lot import InventoryLotStatus
from app.models.inventory_lot_event import (
    InventoryLotEvent,
    InventoryLotEventType,
)
from app.models.notification import Notification, NotificationType
from app.models.pickup_request import PickupRequest, PickupStatus
from app.services import jobs


# ============================================================
# Reservation Sweep
# ============================================================


def test_reservation_sweep_releases_expired_lot(
    db_session,
    inventory_lot,
    dealer_user,
    jobs_session_factory,
    monkeypatch,
):
    inventory_lot.status = InventoryLotStatus.reserved
    inventory_lot.reserved_by_dealer_id = dealer_user.id
    inventory_lot.reserved_at = datetime.now(timezone.utc) - timedelta(hours=25)
    inventory_lot.reservation_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()

    monkeypatch.setattr(jobs, "SessionLocal", jobs_session_factory)

    jobs.reservation_sweep_job()

    db_session.expire_all()

    lot = (
        db_session.query(type(inventory_lot))
        .filter(type(inventory_lot).id == inventory_lot.id)
        .one()
    )

    assert lot.status == InventoryLotStatus.available
    assert lot.reserved_by_dealer_id is None
    assert lot.reserved_at is None
    assert lot.reservation_expires_at is None

    event = (
        db_session.query(InventoryLotEvent)
        .filter(
            InventoryLotEvent.inventory_lot_id == inventory_lot.id,
            InventoryLotEvent.event_type == InventoryLotEventType.reservation_expired,
        )
        .one()
    )

    assert event.new_status == InventoryLotStatus.available


def test_reservation_sweep_ignores_unexpired_lot(
    db_session,
    inventory_lot,
    dealer_user,
    jobs_session_factory,
    monkeypatch,
):
    inventory_lot.status = InventoryLotStatus.reserved
    inventory_lot.reserved_by_dealer_id = dealer_user.id
    inventory_lot.reserved_at = datetime.now(timezone.utc)
    inventory_lot.reservation_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    db_session.commit()

    monkeypatch.setattr(jobs, "SessionLocal", jobs_session_factory)

    jobs.reservation_sweep_job()

    db_session.expire_all()

    lot = (
        db_session.query(type(inventory_lot))
        .filter(type(inventory_lot).id == inventory_lot.id)
        .one()
    )

    assert lot.status == InventoryLotStatus.reserved
    assert lot.reserved_by_dealer_id == dealer_user.id


def test_reservation_sweep_releases_expired_lot_without_dealer(
    db_session,
    inventory_lot,
    jobs_session_factory,
    monkeypatch,
):
    inventory_lot.status = InventoryLotStatus.reserved
    inventory_lot.reserved_by_dealer_id = None
    inventory_lot.reserved_at = datetime.now(timezone.utc) - timedelta(hours=25)
    inventory_lot.reservation_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()

    monkeypatch.setattr(jobs, "SessionLocal", jobs_session_factory)

    jobs.reservation_sweep_job()

    db_session.expire_all()

    lot = (
        db_session.query(type(inventory_lot))
        .filter(type(inventory_lot).id == inventory_lot.id)
        .one()
    )

    assert lot.status == InventoryLotStatus.available
    assert lot.reserved_by_dealer_id is None
    assert lot.reserved_at is None
    assert lot.reservation_expires_at is None


def test_reservation_sweep_creates_expiration_event(
    db_session,
    inventory_lot,
    jobs_session_factory,
    monkeypatch,
):
    inventory_lot.status = InventoryLotStatus.reserved
    inventory_lot.reservation_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()

    monkeypatch.setattr(jobs, "SessionLocal", jobs_session_factory)

    jobs.reservation_sweep_job()

    db_session.expire_all()

    event = (
        db_session.query(InventoryLotEvent)
        .filter(
            InventoryLotEvent.inventory_lot_id == inventory_lot.id,
            InventoryLotEvent.event_type == InventoryLotEventType.reservation_expired,
        )
        .one()
    )

    assert event.previous_status == InventoryLotStatus.reserved
    assert event.new_status == InventoryLotStatus.available
    assert event.actor_user_id is None
    assert event.event_notes == "Reservation expired automatically by scheduler."
    assert event.metadata_json == {}


def test_reservation_sweep_notifies_dealer(
    db_session,
    inventory_lot,
    dealer_user,
    jobs_session_factory,
    monkeypatch,
):
    inventory_lot.status = InventoryLotStatus.reserved
    inventory_lot.reserved_by_dealer_id = dealer_user.id
    inventory_lot.reservation_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()

    monkeypatch.setattr(jobs, "SessionLocal", jobs_session_factory)

    calls = []

    def fake_notify(self, db, lot, dealer_id):
        calls.append((db, lot.id, dealer_id))

    monkeypatch.setattr(
        jobs.NotificationDispatcher,
        "notify_reservation_expired",
        fake_notify,
    )

    jobs.reservation_sweep_job()

    assert len(calls) == 1
    assert calls[0][1] == inventory_lot.id
    assert calls[0][2] == dealer_user.id


def test_reservation_sweep_does_not_notify_without_dealer(
    db_session,
    inventory_lot,
    jobs_session_factory,
    monkeypatch,
):
    inventory_lot.status = InventoryLotStatus.reserved
    inventory_lot.reserved_by_dealer_id = None
    inventory_lot.reservation_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()

    monkeypatch.setattr(jobs, "SessionLocal", jobs_session_factory)

    calls = []

    def fake_notify(self, *args, **kwargs):
        calls.append(True)

    monkeypatch.setattr(
        jobs.NotificationDispatcher,
        "notify_reservation_expired",
        fake_notify,
    )

    jobs.reservation_sweep_job()

    assert calls == []


def test_reservation_sweep_continues_when_notification_fails(
    db_session,
    inventory_lot,
    dealer_user,
    jobs_session_factory,
    monkeypatch,
):
    inventory_lot.status = InventoryLotStatus.reserved
    inventory_lot.reserved_by_dealer_id = dealer_user.id
    inventory_lot.reservation_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()

    monkeypatch.setattr(jobs, "SessionLocal", jobs_session_factory)

    def failing_notification(self, *args, **kwargs):
        raise RuntimeError("notification service unavailable")

    monkeypatch.setattr(
        jobs.NotificationDispatcher,
        "notify_reservation_expired",
        failing_notification,
    )

    jobs.reservation_sweep_job()

    db_session.expire_all()

    lot = (
        db_session.query(type(inventory_lot))
        .filter(type(inventory_lot).id == inventory_lot.id)
        .one()
    )

    assert lot.status == InventoryLotStatus.available


def test_reservation_sweep_updates_last_run(
    db_session,
    jobs_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(jobs, "SessionLocal", jobs_session_factory)

    jobs.last_runs["reservation_sweep"] = None

    jobs.reservation_sweep_job()

    assert jobs.last_runs["reservation_sweep"] is not None
    assert jobs.last_runs["reservation_sweep"].tzinfo is not None


# ============================================================
# Aging Pickup Alerts
# ============================================================


def test_aging_pickup_alert_notifies_admin(
    db_session,
    citizen_user,
    admin_user,
    jobs_session_factory,
    monkeypatch,
):
    pickup = PickupRequest(
        user_id=citizen_user.id,
        waste_type="Plastic bottles",
        address="12 Lake Road, Kolkata, 700029",
        latitude=22.5726,
        longitude=88.3639,
        status=PickupStatus.pending,
        created_at=datetime.now(timezone.utc) - timedelta(days=3),
    )

    db_session.add(pickup)
    db_session.commit()
    db_session.refresh(pickup)

    monkeypatch.setattr(jobs, "SessionLocal", jobs_session_factory)

    jobs.aging_pickup_alert_job()

    db_session.expire_all()

    notifications = (
        db_session.query(Notification)
        .filter(
            Notification.user_id == admin_user.id,
            Notification.type == NotificationType.system,
        )
        .all()
    )

    assert len(notifications) == 1
    assert notifications[0].title == "Aging Pickup Alert"
    assert notifications[0].metadata_json["event"] == "aging_pickup_alert"
    assert notifications[0].metadata_json["pickup_id"] == str(pickup.id)


def test_aging_pickup_alert_is_idempotent(
    db_session,
    citizen_user,
    admin_user,
    jobs_session_factory,
    monkeypatch,
):
    pickup = PickupRequest(
        user_id=citizen_user.id,
        waste_type="Plastic bottles",
        address="12 Lake Road, Kolkata, 700029",
        latitude=22.5726,
        longitude=88.3639,
        status=PickupStatus.pending,
        created_at=datetime.now(timezone.utc) - timedelta(days=3),
    )

    db_session.add(pickup)
    db_session.commit()
    db_session.refresh(pickup)

    monkeypatch.setattr(jobs, "SessionLocal", jobs_session_factory)

    jobs.aging_pickup_alert_job()
    jobs.aging_pickup_alert_job()

    notifications = (
        db_session.query(Notification)
        .filter(
            Notification.user_id == admin_user.id,
            Notification.type == NotificationType.system,
        )
        .all()
    )

    assert len(notifications) == 1


def test_aging_pickup_alert_handles_accepted_pickup(
    db_session,
    citizen_user,
    admin_user,
    jobs_session_factory,
    monkeypatch,
):
    pickup = PickupRequest(
        user_id=citizen_user.id,
        waste_type="Plastic bottles",
        address="12 Lake Road, Kolkata, 700029",
        latitude=22.5726,
        longitude=88.3639,
        status=PickupStatus.accepted,
        created_at=datetime.now(timezone.utc) - timedelta(days=3),
    )

    db_session.add(pickup)
    db_session.commit()

    monkeypatch.setattr(jobs, "SessionLocal", jobs_session_factory)

    jobs.aging_pickup_alert_job()

    db_session.expire_all()

    notification = (
        db_session.query(Notification)
        .filter(
            Notification.user_id == admin_user.id,
            Notification.type == NotificationType.system,
        )
        .one()
    )

    assert notification.title == "Aging Pickup Alert"


def test_aging_pickup_alert_ignores_recent_pending_pickup(
    db_session,
    citizen_user,
    admin_user,
    jobs_session_factory,
    monkeypatch,
):
    pickup = PickupRequest(
        user_id=citizen_user.id,
        waste_type="Plastic",
        address="12 Lake Road, Kolkata, 700029",
        latitude=22.5726,
        longitude=88.3639,
        status=PickupStatus.pending,
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )

    db_session.add(pickup)
    db_session.commit()

    monkeypatch.setattr(jobs, "SessionLocal", jobs_session_factory)

    jobs.aging_pickup_alert_job()

    db_session.expire_all()

    notifications = (
        db_session.query(Notification)
        .filter(
            Notification.user_id == admin_user.id,
            Notification.type == NotificationType.system,
        )
        .all()
    )

    assert notifications == []


def test_aging_pickup_alert_ignores_completed_pickup(
    db_session,
    citizen_user,
    admin_user,
    jobs_session_factory,
    monkeypatch,
):
    pickup = PickupRequest(
        user_id=citizen_user.id,
        waste_type="Plastic",
        address="12 Lake Road, Kolkata, 700029",
        latitude=22.5726,
        longitude=88.3639,
        status=PickupStatus.completed,
        created_at=datetime.now(timezone.utc) - timedelta(days=5),
    )

    db_session.add(pickup)
    db_session.commit()

    monkeypatch.setattr(jobs, "SessionLocal", jobs_session_factory)

    jobs.aging_pickup_alert_job()

    db_session.expire_all()

    notifications = (
        db_session.query(Notification)
        .filter(
            Notification.user_id == admin_user.id,
            Notification.type == NotificationType.system,
        )
        .all()
    )

    assert notifications == []


def test_aging_pickup_alert_processes_multiple_pickups(
    db_session,
    citizen_user,
    admin_user,
    jobs_session_factory,
    monkeypatch,
):
    pickup_one = PickupRequest(
        user_id=citizen_user.id,
        waste_type="Plastic",
        address="12 Lake Road, Kolkata, 700029",
        latitude=22.5726,
        longitude=88.3639,
        status=PickupStatus.pending,
        created_at=datetime.now(timezone.utc) - timedelta(days=3),
    )

    pickup_two = PickupRequest(
        user_id=citizen_user.id,
        waste_type="Paper",
        address="13 Lake Road, Kolkata, 700029",
        latitude=22.5726,
        longitude=88.3639,
        status=PickupStatus.accepted,
        created_at=datetime.now(timezone.utc) - timedelta(days=4),
    )

    db_session.add_all([pickup_one, pickup_two])
    db_session.commit()

    monkeypatch.setattr(jobs, "SessionLocal", jobs_session_factory)

    jobs.aging_pickup_alert_job()

    db_session.expire_all()

    notifications = (
        db_session.query(Notification)
        .filter(
            Notification.user_id == admin_user.id,
            Notification.type == NotificationType.system,
        )
        .all()
    )

    assert len(notifications) == 2


def test_aging_pickup_alert_updates_last_run(
    db_session,
    jobs_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(jobs, "SessionLocal", jobs_session_factory)

    jobs.last_runs["aging_pickups"] = None

    jobs.aging_pickup_alert_job()

    assert jobs.last_runs["aging_pickups"] is not None
    assert jobs.last_runs["aging_pickups"].tzinfo is not None


# ============================================================
# Scheduler
# ============================================================


def test_start_scheduler_does_nothing_in_test_environment(monkeypatch):
    monkeypatch.setattr(jobs.settings, "environment", "test")
    monkeypatch.setattr(jobs.settings, "enable_background_jobs", True)

    class FakeScheduler:
        running = False

        def add_job(self, *args, **kwargs):
            raise AssertionError("add_job should not be called")

        def start(self):
            raise AssertionError("scheduler.start should not be called")

    monkeypatch.setattr(jobs, "scheduler", FakeScheduler())

    jobs.start_scheduler()


def test_start_scheduler_does_nothing_when_background_jobs_disabled(
    monkeypatch,
):
    monkeypatch.setattr(jobs.settings, "environment", "production")
    monkeypatch.setattr(jobs.settings, "enable_background_jobs", False)

    class FakeScheduler:
        running = False

        def add_job(self, *args, **kwargs):
            raise AssertionError("add_job should not be called")

        def start(self):
            raise AssertionError("scheduler.start should not be called")

    monkeypatch.setattr(jobs, "scheduler", FakeScheduler())

    jobs.start_scheduler()


def test_start_scheduler_does_nothing_when_already_running(
    monkeypatch,
):
    monkeypatch.setattr(jobs.settings, "environment", "production")
    monkeypatch.setattr(jobs.settings, "enable_background_jobs", True)

    class FakeScheduler:
        running = True

        def add_job(self, *args, **kwargs):
            raise AssertionError("add_job should not be called")

        def start(self):
            raise AssertionError("scheduler.start should not be called")

    monkeypatch.setattr(jobs, "scheduler", FakeScheduler())

    jobs.start_scheduler()


def test_start_scheduler_registers_jobs(monkeypatch):
    monkeypatch.setattr(jobs.settings, "environment", "production")
    monkeypatch.setattr(jobs.settings, "enable_background_jobs", True)

    added_jobs = []
    started = False

    class FakeScheduler:
        running = False

        def get_job(self, job_id):
            return None

        def add_job(self, *args, **kwargs):
            added_jobs.append(kwargs)

        def start(self):
            nonlocal started
            started = True

    monkeypatch.setattr(jobs, "scheduler", FakeScheduler())

    jobs.start_scheduler()

    assert len(added_jobs) == 2
    assert started is True

    job_ids = {job["id"] for job in added_jobs}

    assert "reservation_sweep" in job_ids
    assert "aging_pickups" in job_ids


def test_start_scheduler_does_not_duplicate_existing_jobs(
    monkeypatch,
):
    monkeypatch.setattr(jobs.settings, "environment", "production")
    monkeypatch.setattr(jobs.settings, "enable_background_jobs", True)

    added_jobs = []
    started = False

    class FakeScheduler:
        running = False

        def get_job(self, job_id):
            return object()

        def add_job(self, *args, **kwargs):
            added_jobs.append(kwargs)

        def start(self):
            nonlocal started
            started = True

    monkeypatch.setattr(jobs, "scheduler", FakeScheduler())

    jobs.start_scheduler()

    assert added_jobs == []
    assert started is True


def test_stop_scheduler_shuts_down_running_scheduler(monkeypatch):
    shutdown_called = False

    class FakeScheduler:
        running = True

        def shutdown(self, wait=False):
            nonlocal shutdown_called
            shutdown_called = True
            assert wait is False

    monkeypatch.setattr(jobs, "scheduler", FakeScheduler())

    jobs.stop_scheduler()

    assert shutdown_called is True


def test_stop_scheduler_does_nothing_when_not_running(monkeypatch):
    shutdown_called = False

    class FakeScheduler:
        running = False

        def shutdown(self, wait=False):
            nonlocal shutdown_called
            shutdown_called = True

    monkeypatch.setattr(jobs, "scheduler", FakeScheduler())

    jobs.stop_scheduler()

    assert shutdown_called is False
