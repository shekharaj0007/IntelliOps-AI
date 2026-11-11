"""Tiny synthetic case: a calm series with one spiked window.

The forest is fit on that series, including the spike, which is how the
seed trains on history that already contains injected events.
"""

import numpy as np

from backend.app.anomaly import WINDOW, feature_matrix, fit_isolation_forest, isolation_scores


def seed_tiny_case(
    n: int = 220,
    spike_start: int = 170,
    spike_len: int = 14,
    seed: int = 7,
) -> tuple[list[dict], slice]:
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n):
        rows.append(
            {
                "cpu": float(rng.normal(30, 1.5)),
                "memory": float(rng.normal(50, 1.2)),
                "error_rate": float(abs(rng.normal(0.01, 0.002))),
                "latency_ms": float(rng.normal(80, 4)),
                "disk": float(rng.normal(40, 1.0)),
            }
        )
    spike = slice(spike_start, spike_start + spike_len)
    for index in range(spike.start, spike.stop):
        rows[index]["cpu"] = 99.0
        rows[index]["error_rate"] = 0.5
        rows[index]["latency_ms"] = 1800.0
    return rows, spike


def test_isolation_forest_flags_spiked_window():
    rows, spike = seed_tiny_case()
    features = feature_matrix(rows, WINDOW)
    scaler, model = fit_isolation_forest(
        features[WINDOW:],
        contamination=0.08,
        n_estimators=100,
        random_state=42,
    )
    flags, scores = isolation_scores(scaler, model, features)
    spike_rate = float(flags[spike].mean())
    calm_rate = float(flags[WINDOW : spike.start].mean())
    assert spike_rate >= 0.8, f"spike flag rate {spike_rate:.2f}"
    assert calm_rate <= 0.1, f"calm flag rate {calm_rate:.2f}"
    assert float(scores[spike].mean()) > float(scores[WINDOW : spike.start].mean())
