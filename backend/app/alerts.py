"""Evaluate stored alert rules against the latest synthetic samples.

A rule opens one alert per service when the latest `consecutive` samples all
match. An alert that is already open for that service and rule is left as-is.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Alert, AlertRule, MetricSample, Service
from backend.app.slo import as_utc

METRICS = {"cpu", "memory", "error_rate", "latency_ms", "disk"}
COMPARATORS = {
    "gt": lambda value, threshold: value > threshold,
    "gte": lambda value, threshold: value >= threshold,
    "lt": lambda value, threshold: value < threshold,
    "lte": lambda value, threshold: value <= threshold,
}
COMPARATOR_WORDS = {
    "gt": "above",
    "gte": "at or above",
    "lt": "below",
    "lte": "at or below",
}


def _format_value(metric: str, value: float) -> str:
    if metric == "error_rate":
        return f"{value * 100:.2f}%"
    if metric == "latency_ms":
        return f"{value:.0f} ms"
    return f"{value:.1f}"


def _summary(rule: AlertRule, values: list[float]) -> str:
    word = COMPARATOR_WORDS.get(rule.comparator, rule.comparator)
    shown = ", ".join(_format_value(rule.metric, value) for value in values)
    target = _format_value(rule.metric, rule.threshold)
    return (
        f"Synthetic alert. Latest {rule.consecutive} samples of {rule.metric} "
        f"are {word} {target} ({shown})."
    )


def _tail_matches(samples: list[MetricSample], rule: AlertRule) -> list[float] | None:
    if rule.consecutive < 1 or rule.metric not in METRICS:
        return None
    compare = COMPARATORS.get(rule.comparator)
    if compare is None or len(samples) < rule.consecutive:
        return None
    tail = samples[-rule.consecutive :]
    values = [float(getattr(sample, rule.metric)) for sample in tail]
    if not all(compare(value, rule.threshold) for value in values):
        return None
    return values


def evaluate_alert_rules(db: Session) -> list[Alert]:
    """Open alerts for rules whose latest samples match and are not already open."""
    rules = list(db.scalars(select(AlertRule)).all())
    if not rules:
        return []
    services = list(db.scalars(select(Service).order_by(Service.id)).all())
    limit = max(1, max(rule.consecutive for rule in rules))
    limit = min(limit, 288)
    opened: list[Alert] = []
    for service in services:
        samples = list(
            db.scalars(
                select(MetricSample)
                .where(MetricSample.service_id == service.id)
                .order_by(MetricSample.ts.desc())
                .limit(limit)
            ).all()
        )
        samples.reverse()
        for rule in rules:
            values = _tail_matches(samples, rule)
            if values is None:
                continue
            existing = db.scalar(
                select(Alert.id).where(
                    Alert.service_id == service.id,
                    Alert.rule_id == rule.id,
                    Alert.status == "open",
                )
            )
            if existing is not None:
                continue
            alert = Alert(
                service_id=service.id,
                rule_id=rule.id,
                status="open",
                opened_at=as_utc(samples[-1].ts),
                summary=_summary(rule, values),
            )
            db.add(alert)
            opened.append(alert)
    db.commit()
    return opened
