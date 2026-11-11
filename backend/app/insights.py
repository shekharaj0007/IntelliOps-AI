from __future__ import annotations

import math
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.anomaly import failure_risk_threshold, get_bundle, score_failure_risk
from backend.app.models import Anomaly, Incident, MetricSample, Service


def iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def band_for(summary: str) -> str:
    text = summary.lower()
    if "error" in text or "latency" in text:
        return "critical"
    return "warning"


def metric_dicts(samples: list[MetricSample]) -> list[dict]:
    return [
        {
            "ts": iso(sample.ts),
            "cpu": sample.cpu,
            "memory": sample.memory,
            "error_rate": sample.error_rate,
            "latency_ms": sample.latency_ms,
            "disk": sample.disk,
        }
        for sample in samples
    ]


def load_recent_metrics(db: Session, service_id: int, limit: int) -> list[MetricSample]:
    rows = db.scalars(
        select(MetricSample)
        .where(MetricSample.service_id == service_id)
        .order_by(MetricSample.ts.desc())
        .limit(limit)
    ).all()
    return list(reversed(rows))


def _rows(samples: list[MetricSample]) -> list[dict]:
    return [
        {
            "cpu": sample.cpu,
            "memory": sample.memory,
            "error_rate": sample.error_rate,
            "latency_ms": sample.latency_ms,
            "disk": sample.disk,
        }
        for sample in samples
    ]


def risk_from_samples(samples: list[MetricSample]) -> float:
    if not samples:
        return 0.0
    value = float(score_failure_risk(_rows(samples), get_bundle()))
    if not math.isfinite(value):
        return 0.0
    return round(value, 4)


def current_risk_threshold() -> float:
    value = float(failure_risk_threshold(get_bundle()))
    if not math.isfinite(value):
        return 0.5
    return value


def anomaly_dict(anomaly: Anomaly, service: Service) -> dict:
    return {
        "id": anomaly.id,
        "service_id": anomaly.service_id,
        "service_name": service.name,
        "region": service.region,
        "ts": iso(anomaly.ts),
        "score": anomaly.score,
        "summary": anomaly.summary,
        "status": anomaly.status,
        "band": band_for(anomaly.summary),
    }


def incident_dict(
    incident: Incident,
    service: Service | None,
    similarity: float | None = None,
) -> dict:
    payload = {
        "id": incident.id,
        "title": incident.title,
        "severity": incident.severity,
        "status": incident.status,
        "service_id": incident.service_id,
        "service_name": service.name if service else "unknown",
        "summary": incident.summary,
        "rca_text": incident.rca_text,
        "created_at": iso(incident.created_at),
    }
    if similarity is not None:
        payload["similarity"] = round(float(similarity), 4)
    return payload


def open_counts(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(Anomaly.service_id, func.count())
        .where(Anomaly.status == "open")
        .group_by(Anomaly.service_id)
    ).all()
    return {int(service_id): int(count) for service_id, count in rows}
