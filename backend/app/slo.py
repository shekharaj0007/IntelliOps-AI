"""SLO checks against the trailing window of synthetic samples.

Targets are seeded. A breach is a mean above the target. Nothing here is a
measured production SLO.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.insights import load_recent_metrics
from backend.app.models import Service, ServiceSlo

WINDOW_HOURS = 2.0


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _field(sample: object, name: str):
    if isinstance(sample, dict):
        return sample[name]
    return getattr(sample, name)


def samples_in_window(samples: list, hours: float = WINDOW_HOURS) -> list:
    """Keep samples within `hours` of the newest timestamp in the list."""
    if not samples:
        return []
    latest = max(as_utc(_field(sample, "ts")) for sample in samples)
    cutoff = latest - timedelta(hours=hours)
    return [sample for sample in samples if as_utc(_field(sample, "ts")) >= cutoff]


def assess_slo(
    samples: list,
    latency_target: float,
    error_target: float,
    hours: float = WINDOW_HOURS,
) -> dict:
    window = samples_in_window(samples, hours)
    if not window:
        return {
            "samples": 0,
            "latency_ms_observed": None,
            "error_rate_observed": None,
            "latency_breach": False,
            "error_breach": False,
            "breaching": False,
            "breach_on": [],
        }
    latency = sum(float(_field(sample, "latency_ms")) for sample in window) / len(window)
    error_rate = sum(float(_field(sample, "error_rate")) for sample in window) / len(window)
    latency_breach = latency > latency_target
    error_breach = error_rate > error_target
    breach_on = []
    if latency_breach:
        breach_on.append("latency")
    if error_breach:
        breach_on.append("error rate")
    return {
        "samples": len(window),
        "latency_ms_observed": round(latency, 2),
        "error_rate_observed": round(error_rate, 6),
        "latency_breach": latency_breach,
        "error_breach": error_breach,
        "breaching": latency_breach or error_breach,
        "breach_on": breach_on,
    }


def derive_status(open_anomalies: int, slo_breach: bool) -> str:
    """up / degraded / down from open anomalies and an SLO breach."""
    if open_anomalies > 0 and slo_breach:
        return "down"
    if open_anomalies > 0 or slo_breach:
        return "degraded"
    return "up"


def report_for_services(db: Session, services: list[Service]) -> list[dict]:
    slos = {slo.service_id: slo for slo in db.scalars(select(ServiceSlo)).all()}
    rows = []
    for service in services:
        slo = slos.get(service.id)
        samples = load_recent_metrics(db, service.id, 48)
        if slo is None:
            assessed = assess_slo([], 0.0, 0.0)
            target_latency = None
            target_error = None
        else:
            assessed = assess_slo(samples, slo.latency_ms, slo.error_rate)
            target_latency = slo.latency_ms
            target_error = slo.error_rate
        rows.append(
            {
                "service_id": service.id,
                "name": service.name,
                "region": service.region,
                "latency_ms_target": target_latency,
                "error_rate_target": target_error,
                **assessed,
            }
        )
    return rows
