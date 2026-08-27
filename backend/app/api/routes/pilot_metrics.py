from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.schemas.pilot_metrics import PilotOperationalMetrics
from app.services.pilot_metrics import get_pilot_operational_metrics

router = APIRouter()


@router.get(
    "",
    response_model=PilotOperationalMetrics,
)
def pilot_operational_metrics(
    db: Session = Depends(get_db),
) -> PilotOperationalMetrics:
    """Return aggregate operational metrics for the pilot dashboard."""
    return get_pilot_operational_metrics(db)
