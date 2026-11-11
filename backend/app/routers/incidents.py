from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.deps import get_current_user
from backend.app.insights import comment_dict, incident_dict
from backend.app.models import Anomaly, Incident, IncidentComment, Service, User, utcnow
from backend.app.rca import playbook_rca, rank_similar

router = APIRouter(
    prefix="/api/incidents",
    tags=["incidents"],
    dependencies=[Depends(get_current_user)],
)

SEVERITIES = {"low", "medium", "high", "critical"}


class IncidentIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    severity: str
    service_id: int
    summary: str = Field(min_length=3)


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


def _services(db: Session) -> dict[int, Service]:
    return {service.id: service for service in db.scalars(select(Service)).all()}


@router.get("")
def list_incidents(db: Session = Depends(get_db)):
    incidents = db.scalars(select(Incident).order_by(Incident.created_at.desc())).all()
    services = _services(db)
    return {
        "data_origin": "synthetic",
        "incidents": [
            incident_dict(item, services.get(item.service_id)) for item in incidents
        ],
    }


@router.post("")
def create_incident(body: IncidentIn, db: Session = Depends(get_db)):
    severity = body.severity.strip().lower()
    if severity not in SEVERITIES:
        raise HTTPException(status_code=400, detail="Severity must be low, medium, high, or critical")
    service = db.get(Service, body.service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    incident = Incident(
        title=body.title.strip(),
        severity=severity,
        status="open",
        service_id=service.id,
        summary=body.summary.strip(),
        rca_text=None,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident_dict(incident, service)


@router.get("/similar")
def similar_incidents(q: str, db: Session = Depends(get_db)):
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query is empty")
    incidents = list(db.scalars(select(Incident)).all())
    services = _services(db)
    ranked = rank_similar(incidents, query, limit=5)
    return {
        "data_origin": "synthetic",
        "query": query,
        "results": [
            incident_dict(item, services.get(item.service_id), similarity=score)
            for item, score in ranked
        ],
    }


@router.post("/{incident_id}/comments")
def add_comment(
    incident_id: int,
    body: CommentIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    text = body.body.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Comment is empty")
    comment = IncidentComment(
        incident_id=incident.id,
        author=user.email,
        body=text,
        ts=utcnow(),
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment_dict(comment)


@router.post("/{incident_id}/rca")
def generate_rca(incident_id: int, db: Session = Depends(get_db)):
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    service = db.get(Service, incident.service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    anomalies = list(
        db.scalars(
            select(Anomaly)
            .where(Anomaly.service_id == incident.service_id)
            .order_by(Anomaly.ts.desc())
            .limit(8)
        ).all()
    )
    others = list(db.scalars(select(Incident)).all())
    query = " ".join([incident.title, incident.summary, *[item.summary for item in anomalies]])
    similar = rank_similar(others, query, limit=4, exclude_id=incident.id)
    incident.rca_text = playbook_rca(service.name, incident.title, anomalies, similar)
    db.commit()
    db.refresh(incident)
    services = _services(db)
    return {
        "data_origin": "synthetic",
        "incident": incident_dict(incident, service),
        "similar": [
            incident_dict(item, services.get(item.service_id), similarity=score)
            for item, score in similar
        ],
    }
