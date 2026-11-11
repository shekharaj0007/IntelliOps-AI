from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.deps import get_current_user
from backend.app.insights import alert_dict
from backend.app.models import Alert, AlertRule, Service, utcnow

router = APIRouter(
    prefix="/api/alerts",
    tags=["alerts"],
    dependencies=[Depends(get_current_user)],
)


def _payload(db: Session, alert: Alert) -> dict:
    service = db.get(Service, alert.service_id)
    rule = db.get(AlertRule, alert.rule_id)
    if service is None or rule is None:
        raise HTTPException(status_code=404, detail="Alert is missing its service or rule")
    return alert_dict(alert, service, rule)


@router.get("")
def list_alerts(status: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Alert).order_by(Alert.opened_at.desc())
    if status:
        stmt = stmt.where(Alert.status == status)
    alerts = db.scalars(stmt).all()
    services = {service.id: service for service in db.scalars(select(Service)).all()}
    rules = {rule.id: rule for rule in db.scalars(select(AlertRule)).all()}
    payload = []
    for alert in alerts:
        service = services.get(alert.service_id)
        rule = rules.get(alert.rule_id)
        if service is None or rule is None:
            continue
        payload.append(alert_dict(alert, service, rule))
    return {"data_origin": "synthetic", "alerts": payload}


@router.post("/{alert_id}/ack")
def ack_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.status == "open":
        alert.status = "acked"
        alert.acked_at = utcnow()
        db.commit()
        db.refresh(alert)
    return _payload(db, alert)
