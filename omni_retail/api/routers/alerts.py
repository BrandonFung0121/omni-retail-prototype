from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from omni_retail.api.dependencies import get_session
from omni_retail.api.schemas import AlertOut, AlertSummaryResponse
from omni_retail.automation import Severity, run_all_rules

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
def get_alerts(
    severity: Optional[Severity] = None,
    type: Optional[str] = None,
    session: Session = Depends(get_session),
) -> list[AlertOut]:
    """All currently-open alerts, most severe first. Optionally filter by severity or type."""
    alerts = run_all_rules(session)
    if severity is not None:
        alerts = [a for a in alerts if a.severity == severity]
    if type is not None:
        alerts = [a for a in alerts if a.type.value == type]
    return alerts


@router.get("/summary", response_model=AlertSummaryResponse)
def get_alert_summary(session: Session = Depends(get_session)) -> AlertSummaryResponse:
    """Counts by severity and by type, for the Action Center header."""
    alerts = run_all_rules(session)
    by_type: dict[str, int] = {}
    for alert in alerts:
        by_type[alert.type.value] = by_type.get(alert.type.value, 0) + 1

    return AlertSummaryResponse(
        total=len(alerts),
        critical=sum(1 for a in alerts if a.severity == Severity.CRITICAL),
        warning=sum(1 for a in alerts if a.severity == Severity.WARNING),
        info=sum(1 for a in alerts if a.severity == Severity.INFO),
        by_type=by_type,
    )
