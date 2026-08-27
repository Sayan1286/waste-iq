from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.collector_assignment import CollectorAssignment
from app.models.pickup_request import PickupRequest, PickupStatus

from app.schemas.pilot_metrics import PilotOperationalMetrics


def _minutes_between(start: datetime, end: datetime) -> float:
    """Return the elapsed time between two timestamps in minutes."""
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)

    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    return max((end - start).total_seconds() / 60.0, 0.0)


def get_pilot_operational_metrics(
    db: Session,
) -> PilotOperationalMetrics:
    """Return aggregate operational metrics for the pilot dashboard."""

    total_requests = db.scalar(select(func.count(PickupRequest.id))) or 0

    successful_collections = (
        db.scalar(
            select(func.count(PickupRequest.id)).where(
                PickupRequest.status == PickupStatus.completed
            )
        )
        or 0
    )

    failed_collections = (
        db.scalar(
            select(func.count(PickupRequest.id)).where(
                PickupRequest.status == PickupStatus.cancelled
            )
        )
        or 0
    )

    assignments = db.scalars(select(CollectorAssignment)).all()

    assignment_times: list[float] = []
    completion_times: list[float] = []

    for assignment in assignments:
        if assignment.accepted_at is not None:
            assignment_times.append(
                _minutes_between(
                    assignment.created_at,
                    assignment.accepted_at,
                )
            )

        if assignment.completed_at is not None:
            completion_times.append(
                _minutes_between(
                    assignment.created_at,
                    assignment.completed_at,
                )
            )

    average_assignment_time = (
        sum(assignment_times) / len(assignment_times) if assignment_times else 0.0
    )

    average_completion_time = (
        sum(completion_times) / len(completion_times) if completion_times else 0.0
    )

    active_collectors = (
        db.scalar(select(func.count(func.distinct(CollectorAssignment.collector_id)))) or 0
    )

    active_citizens = db.scalar(select(func.count(func.distinct(PickupRequest.user_id)))) or 0

    # Weight-dispute tracking is not currently represented in the data model.
    weight_disputes = 0
    disputed_weight_percentage = 0.0

    # Notification delivery failures are not currently represented by a
    # failure status in the notification model.
    notification_failures = 0

    # Error/uptime metrics require the monitoring infrastructure from
    # WIQ-V1-023. Keep these explicitly zero until that integration is added.
    system_errors = 0
    api_failures = 0
    background_job_failures = 0
    uptime_percentage = 100.0

    return PilotOperationalMetrics(
        collection_requests=total_requests,
        successful_collections=successful_collections,
        failed_collections=failed_collections,
        average_assignment_time_minutes=round(
            average_assignment_time,
            2,
        ),
        average_completion_time_minutes=round(
            average_completion_time,
            2,
        ),
        weight_disputes=weight_disputes,
        disputed_weight_percentage=disputed_weight_percentage,
        notification_failures=notification_failures,
        active_collectors=active_collectors,
        active_citizens=active_citizens,
        system_errors=system_errors,
        api_failures=api_failures,
        background_job_failures=background_job_failures,
        uptime_percentage=uptime_percentage,
    )
