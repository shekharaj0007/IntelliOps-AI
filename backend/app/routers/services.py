from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.deps import get_current_user
from backend.app.insights import anomaly_dict, load_recent_metrics, metric_dicts, open_counts, risk_from_samples
from backend.app.models import Anomaly, Service

router = APIRouter(
    prefix="/api/services",
    tags=["services"],
    dependencies=[Depends(get_current_user)],
)


def _service_payload(db: Session, service: Service, counts: dict[int, int]) -> dict:
    samples = load_recent_metrics(db, service.id, 48)
    return {
        "id": service.id,
        "name": service.name,
        "environment": service.environment,
        "region": service.region,
        "owner": service.owner,
        "open_anomalies": counts.get(service.id, 0),
        "risk_score": risk_from_samples(samples),
    }


@router.get("")
def list_services(db: Session = Depends(get_db)):
    services = db.scalars(select(Service).order_by(Service.name)).all()
    counts = open_counts(db)
    return {
        "data_origin": "synthetic",
        "services": [_service_payload(db, service, counts) for service in services],
    }


@router.get("/{service_id}")
def service_detail(service_id: int, db: Session = Depends(get_db)):
    service = db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    samples = load_recent_metrics(db, service.id, 144)
    anomalies = db.scalars(
        select(Anomaly).where(Anomaly.service_id == service.id).order_by(Anomaly.ts.desc())
    ).all()
    return {
        "data_origin": "synthetic",
        "service": {
            "id": service.id,
            "name": service.name,
            "environment": service.environment,
            "region": service.region,
            "owner": service.owner,
        },
        "risk_score": risk_from_samples(samples),
        "metrics": metric_dicts(samples),
        "anomalies": [anomaly_dict(item, service) for item in anomalies],
    }
