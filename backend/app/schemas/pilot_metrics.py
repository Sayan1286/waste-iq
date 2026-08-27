from pydantic import BaseModel


class PilotOperationalMetrics(BaseModel):
    collection_requests: int
    successful_collections: int
    failed_collections: int

    average_assignment_time_minutes: float
    average_completion_time_minutes: float

    weight_disputes: int
    disputed_weight_percentage: float

    notification_failures: int

    active_collectors: int
    active_citizens: int

    system_errors: int
    api_failures: int
    background_job_failures: int

    uptime_percentage: float
