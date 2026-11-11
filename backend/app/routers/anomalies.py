from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.deps import get_current_user
from backend.app.insights import anomaly_dict
from backend.app.models import Anomaly, Service

router = APIRouter(
    prefix="/api/anomalies",
    tags=["anomalies"],
    dependencies=[Depends(get_current_user)],
)


@router.get("")
def list_anomalies(status: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Anomaly).order_by(Anomaly.ts.desc())
    if status:
        stmt = stmt.where(Anomaly.status == status)
    anomalies = db.scalars(stmt).all()
    services = {service.id: service for service in db.scalars(select(Service)).all()}
    payload = []
    for anomaly in anomalies:
        service = services.get(anomaly.service_id)
        if service is None:
            continue
        payload.append(anomaly_dict(anomaly, service))
    return {"data_origin": "synthetic", "anomalies": payload}


@router.post("/{anomaly_id}/ack")
def ack_anomaly(anomaly_id: int, db: Session = Depends(get_db)):
    anomaly = db.get(Anomaly, anomaly_id)
    if anomaly is None:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    if anomaly.status == "open":
        anomaly.status = "acked"
        db.commit()
        db.refresh(anomaly)
    service = db.get(Service, anomaly.service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    return anomaly_dict(anomaly, service)
