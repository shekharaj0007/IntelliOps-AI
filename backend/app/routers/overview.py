from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.deps import get_current_user
from backend.app.insights import (
    alert_dict,
    anomaly_dict,
    current_risk_threshold,
    load_recent_metrics,
    open_counts,
    risk_from_samples,
)
from backend.app.models import Alert, AlertRule, Anomaly, Incident, Service
from backend.app.slo import WINDOW_HOURS, report_for_services

router = APIRouter(
    prefix="/api",
    tags=["overview"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    services = list(db.scalars(select(Service).order_by(Service.name)).all())
    counts_map = open_counts(db)
    open_anomalies = list(
        db.scalars(select(Anomaly).where(Anomaly.status == "open").order_by(Anomaly.ts.desc())).all()
    )
    service_by_id = {service.id: service for service in services}
    acked = db.scalar(select(func.count()).select_from(Anomaly).where(Anomaly.status == "acked")) or 0
    open_incidents = (
        db.scalar(
            select(func.count())
            .select_from(Incident)
            .where(Incident.status.in_(("open", "investigating")))
        )
        or 0
    )
    threshold = current_risk_threshold()
    slo_rows = report_for_services(db, services)
    slo_breaches = [row for row in slo_rows if row["breaching"]]
    open_alert_rows = list(
        db.scalars(select(Alert).where(Alert.status == "open").order_by(Alert.opened_at.desc())).all()
    )
    rules = {rule.id: rule for rule in db.scalars(select(AlertRule)).all()}
    open_alerts = [
        alert_dict(alert, service_by_id[alert.service_id], rules[alert.rule_id])
        for alert in open_alert_rows
        if alert.service_id in service_by_id and alert.rule_id in rules
    ]

    fleet = []
    regions: dict[str, dict] = {}
    at_risk = []
    for service in services:
        samples = load_recent_metrics(db, service.id, 48)
        risk = risk_from_samples(samples)
        open_n = counts_map.get(service.id, 0)
        fleet.append(
            {
                "id": service.id,
                "name": service.name,
                "environment": service.environment,
                "region": service.region,
                "owner": service.owner,
                "open_anomalies": open_n,
                "risk_score": risk,
            }
        )
        bucket = regions.setdefault(
            service.region,
            {"region": service.region, "services": 0, "open_anomalies": 0, "highest_risk": 0.0},
        )
        bucket["services"] += 1
        bucket["open_anomalies"] += open_n
        bucket["highest_risk"] = round(max(bucket["highest_risk"], risk), 4)
        if risk >= threshold or open_n > 0:
            reasons = []
            if risk >= threshold:
                reasons.append(f"failure-risk {risk:.2f}")
            if open_n:
                label = "open anomaly" if open_n == 1 else "open anomalies"
                reasons.append(f"{open_n} {label}")
            at_risk.append(
                {
                    "service_id": service.id,
                    "name": service.name,
                    "region": service.region,
                    "environment": service.environment,
                    "risk_score": risk,
                    "open_anomalies": open_n,
                    "reason": "; ".join(reasons),
                }
            )

    at_risk.sort(key=lambda item: (item["risk_score"], item["open_anomalies"]), reverse=True)
    anomaly_payload = [
        anomaly_dict(item, service_by_id[item.service_id])
        for item in open_anomalies
        if item.service_id in service_by_id
    ]
    return {
        "data_origin": "synthetic",
        "risk_threshold": round(threshold, 4),
        "slo_window_hours": WINDOW_HOURS,
        "counts": {
            "services": len(services),
            "open_anomalies": len(anomaly_payload),
            "acked_anomalies": int(acked),
            "open_incidents": int(open_incidents),
            "slo_breaches": len(slo_breaches),
            "open_alerts": len(open_alerts),
        },
        "slos": slo_rows,
        "open_alerts": open_alerts,
        "regions": sorted(regions.values(), key=lambda item: item["region"]),
        "fleet": fleet,
        "open_anomalies": anomaly_payload,
        "services_at_risk": at_risk,
    }
