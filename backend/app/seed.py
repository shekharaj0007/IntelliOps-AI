"""Synthetic fleet seed. Every injected spike is labeled in memory for holdout scoring."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from backend.app.anomaly import (
    detect_series,
    evaluate_holdout,
    failure_risk_threshold,
    fit_bundle,
    load_bundle,
    refit_unlabeled,
    save_bundle,
    score_failure_risk,
    write_metrics_json,
)
from backend.app.config import DEMO_EMAIL, DEMO_NAME, DEMO_PASSWORD
from backend.app.models import Anomaly, Incident, MetricSample, Service, User
from backend.app.security import hash_password

log = logging.getLogger("intelliops.seed")

STEP = timedelta(minutes=5)
DAYS = 3
SAMPLES_PER_HOUR = 12
SAMPLES = DAYS * 24 * SAMPLES_PER_HOUR

SERVICE_SPECS = [
    {
        "name": "api-gateway",
        "environment": "prod",
        "region": "us-east-1",
        "owner": "platform",
        "cpu": 32.0,
        "memory": 58.0,
        "error_rate": 0.006,
        "latency_ms": 85.0,
        "disk": 41.0,
    },
    {
        "name": "checkout-api",
        "environment": "prod",
        "region": "us-east-1",
        "owner": "payments",
        "cpu": 41.0,
        "memory": 63.0,
        "error_rate": 0.009,
        "latency_ms": 120.0,
        "disk": 47.0,
    },
    {
        "name": "auth-service",
        "environment": "prod",
        "region": "eu-west-1",
        "owner": "identity",
        "cpu": 22.0,
        "memory": 48.0,
        "error_rate": 0.004,
        "latency_ms": 55.0,
        "disk": 36.0,
    },
    {
        "name": "inventory-db",
        "environment": "prod",
        "region": "eu-west-1",
        "owner": "data",
        "cpu": 48.0,
        "memory": 71.0,
        "error_rate": 0.002,
        "latency_ms": 15.0,
        "disk": 66.0,
    },
    {
        "name": "search-indexer",
        "environment": "staging",
        "region": "ap-south-1",
        "owner": "search",
        "cpu": 36.0,
        "memory": 60.0,
        "error_rate": 0.011,
        "latency_ms": 210.0,
        "disk": 52.0,
    },
    {
        "name": "notification-worker",
        "environment": "prod",
        "region": "ap-south-1",
        "owner": "messaging",
        "cpu": 27.0,
        "memory": 44.0,
        "error_rate": 0.007,
        "latency_ms": 140.0,
        "disk": 33.0,
    },
]

# (start_hour, kind, duration_hours). The last 25% of the timeline is the holdout.
EVENTS = {
    "api-gateway": [(16, "cpu", 1.0), (58, "latency", 3.0)],
    "checkout-api": [(28, "error", 1.0), (66, "cpu", 6.0)],
    "auth-service": [(20, "latency", 1.0), (56, "error", 1.25)],
    "inventory-db": [(36, "cpu", 1.25), (62, "latency", 1.0)],
    "search-indexer": [(24, "error", 1.0), (60, "latency", 1.5)],
    "notification-worker": [(40, "cpu", 1.0), (69, "error", 4.0)],
}

HISTORICAL_INCIDENTS = [
    {
        "service": "checkout-api",
        "title": "Checkout error burst after tax-rule deploy",
        "severity": "high",
        "status": "resolved",
        "summary": "Synthetic seed. Checkout error burst above the baseline for about an hour after a tax-rule deploy. Customers retried payments.",
        "rca_text": (
            "Playbook: error burst on checkout-api with stable CPU. The tax-rule pack was rolled back "
            "and the error rate returned to baseline. Latency was only mildly elevated."
        ),
        "hours_ago": 50,
    },
    {
        "service": "api-gateway",
        "title": "Gateway latency cliff from a stalled auth dependency",
        "severity": "critical",
        "status": "resolved",
        "summary": "Synthetic seed. A latency cliff on api-gateway tracked timeouts against auth-service. CPU stayed near baseline.",
        "rca_text": (
            "Playbook: latency cliff caused by auth-service timeouts. Connection pool was exhausted. "
            "Raising the pool and restarting the auth task cleared the cliff within 15 minutes."
        ),
        "hours_ago": 34,
    },
    {
        "service": "inventory-db",
        "title": "Inventory CPU spike during compaction",
        "severity": "medium",
        "status": "resolved",
        "summary": "Synthetic seed. CPU spike on inventory-db lined up with a manual compaction. Reads queued until it finished.",
        "rca_text": (
            "Playbook: CPU spike from compaction on inventory-db. The job was throttled. "
            "No error burst. Latency recovered when compaction ended."
        ),
        "hours_ago": 22,
    },
    {
        "service": "search-indexer",
        "title": "Search latency cliff during full reindex",
        "severity": "high",
        "status": "resolved",
        "summary": "Synthetic seed. search-indexer hit a latency cliff while a full reindex shared the staging cluster.",
        "rca_text": (
            "Playbook: latency cliff on search-indexer. The reindex was paused and resumed off-peak. "
            "Query latency returned to the staging baseline."
        ),
        "hours_ago": 14,
    },
    {
        "service": "notification-worker",
        "title": "Notification worker error burst",
        "severity": "critical",
        "status": "open",
        "summary": "Synthetic seed. Error burst on notification-worker in the latest samples. Delivery retries are climbing.",
        "rca_text": None,
        "hours_ago": 1,
    },
]


def _windows(events: list[tuple[float, str, float]], n_samples: int) -> list[dict]:
    windows = []
    for hour, kind, duration_h in events:
        start = int(hour * SAMPLES_PER_HOUR)
        length = max(1, int(duration_h * SAMPLES_PER_HOUR))
        end = min(n_samples, start + length)
        if start < end:
            windows.append({"start": start, "end": end, "kind": kind})
    return windows


def build_service_series(
    spec: dict,
    events: list[tuple[float, str, float]],
    rng: np.random.Generator,
    n_samples: int,
    start: datetime,
) -> tuple[list[dict], np.ndarray, list[dict]]:
    windows = _windows(events, n_samples)
    labels = np.zeros(n_samples, dtype=np.int8)
    rows: list[dict] = []
    for index in range(n_samples):
        phase = 2 * np.pi * (index / (SAMPLES_PER_HOUR * 24))
        cpu = spec["cpu"] + 4.0 * np.sin(phase) + float(rng.normal(0, 1.6))
        memory = spec["memory"] + 2.0 * np.sin(phase / 2) + float(rng.normal(0, 0.8))
        error_rate = spec["error_rate"] + float(abs(rng.normal(0, 0.0015)))
        latency = spec["latency_ms"] + 6.0 * np.sin(phase) + float(rng.normal(0, 3.0))
        disk = spec["disk"] + 0.4 * np.sin(phase / 3) + float(rng.normal(0, 0.4))
        row = {
            "cpu": float(np.clip(cpu, 2, 78)),
            "memory": float(np.clip(memory, 10, 88)),
            "error_rate": float(np.clip(error_rate, 0.0005, 0.03)),
            "latency_ms": float(np.clip(latency, 4, spec["latency_ms"] * 2.2)),
            "disk": float(np.clip(disk, 5, 90)),
            "ts": start + index * STEP,
        }
        kind = next((item["kind"] for item in windows if item["start"] <= index < item["end"]), None)
        if kind is not None:
            labels[index] = 1
        if kind == "cpu":
            row["cpu"] = float(np.clip(97 + rng.normal(0, 0.5), 94, 99.5))
            row["latency_ms"] = float(row["latency_ms"] + 50)
        elif kind == "error":
            row["error_rate"] = float(np.clip(0.38 + abs(float(rng.normal(0, 0.04))), 0.25, 0.7))
            row["latency_ms"] = float(row["latency_ms"] * 1.8 + 80)
        elif kind == "latency":
            row["latency_ms"] = float(np.clip(1550 + rng.normal(0, 40), 1200, 2200))
            row["cpu"] = float(min(96, row["cpu"] + 28))
        rows.append(row)
    return rows, labels, windows


def _count(db: Session, model: type) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def seed_if_empty(db: Session) -> None:
    if _count(db, User) == 0:
        db.add(
            User(
                email=DEMO_EMAIL,
                password_hash=hash_password(DEMO_PASSWORD),
                name=DEMO_NAME,
            )
        )
        db.commit()

    if _count(db, Service) > 0:
        if load_bundle() is None:
            _refit_from_db(db)
        return

    rng = np.random.default_rng(42)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = now - STEP * (SAMPLES - 1)
    series: dict[str, list[dict]] = {}
    labels: dict[str, np.ndarray] = {}
    windows_by_service: dict[str, list[dict]] = {}

    for spec in SERVICE_SPECS:
        db.add(
            Service(
                name=spec["name"],
                environment=spec["environment"],
                region=spec["region"],
                owner=spec["owner"],
            )
        )
    db.flush()
    services = list(db.scalars(select(Service).order_by(Service.id)).all())
    id_by_name = {service.name: service.id for service in services}

    for spec in SERVICE_SPECS:
        rows, y, windows = build_service_series(spec, EVENTS[spec["name"]], rng, SAMPLES, start)
        series[spec["name"]] = rows
        labels[spec["name"]] = y
        windows_by_service[spec["name"]] = windows

    holdout = evaluate_holdout(series, labels)
    bundle = fit_bundle(series, labels)
    save_bundle(bundle)

    detected: dict[str, list[dict]] = {}
    grouped = 0
    for spec in SERVICE_SPECS:
        events = detect_series(series[spec["name"]], bundle, spec["name"])
        detected[spec["name"]] = events
        grouped += len(events)
        log.info("Detected %s grouped anomalies on %s", len(events), spec["name"])

    forest = holdout.get("isolation_forest", {})
    risk = holdout.get("failure_risk_logreg", {})
    if "f1" in forest:
        log.info(
            "Holdout isolation forest precision=%.3f recall=%.3f f1=%.3f",
            forest["precision"],
            forest["recall"],
            forest["f1"],
        )
    if "roc_auc" in risk and risk["roc_auc"] is not None:
        log.info("Holdout failure-risk ROC AUC=%.3f", risk["roc_auc"])

    # Latest-point risks are full-fit scores, not holdout metrics.
    latest_risk = {
        name: round(float(score_failure_risk(rows, bundle)), 4) for name, rows in series.items()
    }
    write_metrics_json(
        holdout,
        extra={
            "samples_per_service": SAMPLES,
            "step_minutes": 5,
            "services": [spec["name"] for spec in SERVICE_SPECS],
            "injected_windows": windows_by_service,
            "grouped_anomalies_on_full_history": grouped,
            "grouped_anomalies_note": (
                "Count of grouped anomalies from the model refit on the full synthetic "
                "history. This is not a holdout score."
            ),
            "production_risk_threshold": {
                "note": (
                    "Midpoint of mean predicted probabilities on the full synthetic fit. "
                    "Used by the API to mark services at risk. Not a holdout metric."
                ),
                "value": round(float(failure_risk_threshold(bundle)), 6),
                "full_fit_normal_mean_proba": round(float(bundle["risk_normal_mean_proba"]), 6),
                "full_fit_anomalous_mean_proba": round(float(bundle["risk_anomalous_mean_proba"]), 6),
            },
            "latest_failure_risk": latest_risk,
        },
    )

    metric_rows = []
    for spec in SERVICE_SPECS:
        service_id = id_by_name[spec["name"]]
        for row in series[spec["name"]]:
            metric_rows.append(
                {
                    "service_id": service_id,
                    "ts": row["ts"],
                    "cpu": row["cpu"],
                    "memory": row["memory"],
                    "error_rate": row["error_rate"],
                    "latency_ms": row["latency_ms"],
                    "disk": row["disk"],
                }
            )
    for offset in range(0, len(metric_rows), 50):
        db.execute(insert(MetricSample), metric_rows[offset : offset + 50])

    for spec in SERVICE_SPECS:
        service_id = id_by_name[spec["name"]]
        for event in detected[spec["name"]]:
            if not math.isfinite(event["score"]):
                continue
            db.add(
                Anomaly(
                    service_id=service_id,
                    ts=series[spec["name"]][event["index"]]["ts"],
                    score=round(float(event["score"]), 6),
                    summary=event["summary"],
                    status="open",
                )
            )

    for item in HISTORICAL_INCIDENTS:
        db.add(
            Incident(
                title=item["title"],
                severity=item["severity"],
                status=item["status"],
                service_id=id_by_name[item["service"]],
                summary=item["summary"],
                rca_text=item["rca_text"],
                created_at=now - timedelta(hours=item["hours_ago"]),
            )
        )
    db.commit()
    log.info(
        "Seeded synthetic fleet: %s services, %s samples each, %s grouped anomalies",
        len(SERVICE_SPECS),
        SAMPLES,
        grouped,
    )


def _refit_from_db(db: Session) -> None:
    services = list(db.scalars(select(Service).order_by(Service.id)).all())
    series: dict[str, list[dict]] = {}
    for service in services:
        samples = db.scalars(
            select(MetricSample)
            .where(MetricSample.service_id == service.id)
            .order_by(MetricSample.ts.asc())
        ).all()
        series[service.name] = [
            {
                "cpu": sample.cpu,
                "memory": sample.memory,
                "error_rate": sample.error_rate,
                "latency_ms": sample.latency_ms,
                "disk": sample.disk,
            }
            for sample in samples
        ]
    if series:
        refit_unlabeled(series)
        log.info("Refit IsolationForest from stored samples; failure risk is the rule fallback")
