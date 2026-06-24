from __future__ import annotations

from fastapi import APIRouter

from ..schemas import AlertAcknowledge
from ..services.alert_service import acknowledge_alert, list_alerts

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/machines/{machine_id}/alerts")
def alerts(machine_id: int, active_only: bool = True, limit: int = 200) -> list[dict]:
    return list_alerts(machine_id, active_only=active_only, limit=limit)


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge(alert_id: int, payload: AlertAcknowledge) -> dict:
    return acknowledge_alert(alert_id, payload.acknowledged_by, payload.acknowledge_note)
