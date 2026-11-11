"""SLO window and alert-rule evaluation on a tiny in-memory fleet."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.alerts import evaluate_alert_rules
from backend.app.models import Alert, AlertRule, Base, MetricSample, Service
from backend.app.slo import assess_slo, derive_status


def test_slo_breach_uses_only_the_last_two_hours():
    latest = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
    samples = [
        {
            "ts": latest - timedelta(hours=3),
            "latency_ms": 5000.0,
            "error_rate": 0.9,
        }
    ]
    for offset in range(6):
        samples.append(
            {
                "ts": latest - timedelta(minutes=5 * (5 - offset)),
                "latency_ms": 90.0,
                "error_rate": 0.01,
            }
        )
    calm = assess_slo(samples, latency_target=250.0, error_target=0.05)
    assert calm["breaching"] is False
    assert calm["samples"] == 6
    assert calm["latency_ms_observed"] == 90.0

    hot = []
    for offset in range(4):
        hot.append(
            {
                "ts": latest - timedelta(minutes=5 * (3 - offset)),
                "latency_ms": 120.0,
                "error_rate": 0.4,
            }
        )
    breached = assess_slo(hot, latency_target=250.0, error_target=0.02)
    assert breached["latency_breach"] is False
    assert breached["error_breach"] is True
    assert breached["breaching"] is True
    assert breached["breach_on"] == ["error rate"]


def test_status_combines_open_anomalies_and_slo_breach():
    assert derive_status(0, False) == "up"
    assert derive_status(2, False) == "degraded"
    assert derive_status(0, True) == "degraded"
    assert derive_status(1, True) == "down"


def _memory_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def _sample(service_id: int, ts: datetime, error_rate: float) -> MetricSample:
    return MetricSample(
        service_id=service_id,
        ts=ts,
        cpu=30.0,
        memory=40.0,
        error_rate=error_rate,
        latency_ms=100.0,
        disk=20.0,
    )


def test_alert_rule_opens_once_for_a_consecutive_tail():
    db = _memory_session()
    start = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)
    hot = Service(name="notification-worker", environment="prod", region="ap-south-1", owner="messaging")
    calm = Service(name="auth-service", environment="prod", region="eu-west-1", owner="identity")
    db.add_all([hot, calm])
    db.flush()
    for index, error_rate in enumerate([0.01, 0.01, 0.41, 0.38, 0.44]):
        db.add(_sample(hot.id, start + timedelta(minutes=5 * index), error_rate))
    for index, error_rate in enumerate([0.4, 0.42, 0.01]):
        db.add(_sample(calm.id, start + timedelta(minutes=5 * index), error_rate))
    db.add(
        AlertRule(
            name="Error rate above 5%",
            metric="error_rate",
            comparator="gt",
            threshold=0.05,
            consecutive=3,
        )
    )
    db.commit()

    opened = evaluate_alert_rules(db)
    assert len(opened) == 1
    assert opened[0].service_id == hot.id
    assert opened[0].status == "open"
    assert "Synthetic alert" in opened[0].summary

    assert evaluate_alert_rules(db) == []
    open_count = db.scalar(select(func.count()).select_from(Alert).where(Alert.status == "open"))
    assert open_count == 1

    opened[0].status = "acked"
    db.commit()
    reopened = evaluate_alert_rules(db)
    assert len(reopened) == 1
    assert reopened[0].id != opened[0].id
    assert reopened[0].service_id == hot.id
