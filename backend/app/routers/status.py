from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.insights import iso, open_counts
from backend.app.models import Service
from backend.app.slo import WINDOW_HOURS, derive_status, report_for_services

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status")
def public_status(db: Session = Depends(get_db)):
    """Read-only fleet status. No JWT. Derived from synthetic anomalies and SLOs."""
    services = list(db.scalars(select(Service).order_by(Service.name)).all())
    counts = open_counts(db)
    reports = {row["service_id"]: row for row in report_for_services(db, services)}
    payload = []
    for service in services:
        report = reports.get(service.id, {})
        payload.append(
            {
                "name": service.name,
                "region": service.region,
                "status": derive_status(counts.get(service.id, 0), bool(report.get("breaching"))),
            }
        )
    return {
        "data_origin": "synthetic",
        "generated_at": iso(datetime.now(timezone.utc)),
        "window_hours": WINDOW_HOURS,
        "note": (
            "Status is derived from open anomalies and whether the last "
            f"{WINDOW_HOURS:.0f} hours of synthetic samples breach the seeded SLO. "
            "This is not a live production status page."
        ),
        "services": payload,
    }
