"""IsolationForest detection and a small failure-risk model.

Holdout numbers written to metrics.json are computed from the series passed
in. This module does not invent scores.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler

from backend.app.config import MODELS_DIR, ROOT

METRIC_NAMES = ["cpu", "memory", "error_rate", "latency_ms", "disk"]
SIGNAL_LABELS = {
    "cpu": "CPU spike",
    "memory": "Memory pressure",
    "error_rate": "Error burst",
    "latency_ms": "Latency cliff",
    "disk": "Disk saturation",
}
WINDOW = 12
CONTAMINATION = 0.04
BUNDLE_PATH = MODELS_DIR / "anomaly_bundle.joblib"
METRICS_PATH = ROOT / "metrics.json"

_bundle: dict | None = None


def feature_matrix(rows: list[dict], window: int = WINDOW) -> np.ndarray:
    """Level, delta, and trailing z-score for each metric.

    The z-score uses only samples before the current point, so a spike is
    compared with the recent baseline rather than with itself.
    """
    n = len(rows)
    width = len(METRIC_NAMES) * 3
    if n == 0:
        return np.zeros((0, width), dtype=np.float64)
    series = {
        name: np.asarray([float(row[name]) for row in rows], dtype=np.float64)
        for name in METRIC_NAMES
    }
    feats = np.zeros((n, width), dtype=np.float64)
    for metric_index, name in enumerate(METRIC_NAMES):
        values = series[name]
        for i in range(n):
            level = values[i]
            delta = 0.0 if i == 0 else float(values[i] - values[i - 1])
            if i < window:
                z_score = 0.0
            else:
                history = values[i - window : i]
                sigma = float(history.std())
                if sigma < 1e-6:
                    sigma = 1e-6
                z_score = float((level - float(history.mean())) / sigma)
            base = metric_index * 3
            feats[i, base] = level
            feats[i, base + 1] = delta
            feats[i, base + 2] = z_score
    return feats


def risk_feature_matrix(feature_rows: np.ndarray) -> np.ndarray:
    # error z, latency z, cpu z, error level
    return np.column_stack(
        [
            feature_rows[:, 8],
            feature_rows[:, 11],
            feature_rows[:, 2],
            feature_rows[:, 6],
        ]
    )


def fit_isolation_forest(
    features: np.ndarray,
    contamination: float = CONTAMINATION,
    n_estimators: int = 200,
    random_state: int = 42,
) -> tuple[StandardScaler, IsolationForest]:
    scaler = StandardScaler()
    scaled = scaler.fit_transform(features)
    model = IsolationForest(
        n_estimators=n_estimators,
        contamination=contamination,
        random_state=random_state,
        n_jobs=1,
        bootstrap=False,
    )
    model.fit(scaled)
    return scaler, model


def isolation_scores(
    scaler: StandardScaler, model: IsolationForest, features: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    scaled = scaler.transform(features)
    flags = model.predict(scaled) == -1
    # decision_function is lower for outliers; flip it so larger means worse.
    scores = -model.decision_function(scaled)
    return flags, scores


def rule_failure_risk(rows: list[dict], window: int = WINDOW) -> float:
    """Heuristic used only when a fitted logistic model is not available."""
    if len(rows) <= window:
        return 0.0
    last = feature_matrix(rows, window)[-1]
    err_z = max(0.0, float(last[8]))
    lat_z = max(0.0, float(last[11]))
    cpu_z = max(0.0, float(last[2]))
    err = max(0.0, float(last[6]))
    linear = 0.55 * err_z + 0.45 * lat_z + 0.25 * cpu_z + 6.0 * err - 1.2
    return float(1.0 / (1.0 + np.exp(-linear)))


def _positive_proba(model: LogisticRegression, scaled: np.ndarray) -> np.ndarray:
    proba = model.predict_proba(scaled)
    classes = list(model.classes_)
    if 1 not in classes:
        return np.zeros(len(scaled), dtype=np.float64)
    return proba[:, classes.index(1)]


def _threshold_from_train(scores: np.ndarray, labels: np.ndarray) -> tuple[float, float, float]:
    normal = scores[labels == 0]
    anomalous = scores[labels == 1]
    normal_mean = float(normal.mean()) if len(normal) else 0.5
    anomalous_mean = float(anomalous.mean()) if len(anomalous) else 0.5
    return float((normal_mean + anomalous_mean) / 2.0), normal_mean, anomalous_mean


def _binary_report(y_true: np.ndarray, y_pred: np.ndarray, y_score: np.ndarray) -> dict:
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        average="binary",
        zero_division=0,
        pos_label=1,
    )
    report = {
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "tp": int(np.sum((y_true == 1) & (y_pred == 1))),
        "fp": int(np.sum((y_true == 0) & (y_pred == 1))),
        "fn": int(np.sum((y_true == 1) & (y_pred == 0))),
        "tn": int(np.sum((y_true == 0) & (y_pred == 0))),
        "n": int(len(y_true)),
        "n_positive": int(np.sum(y_true == 1)),
        "average_precision": None,
        "roc_auc": None,
    }
    if len(np.unique(y_true)) == 2 and len(y_true) > 1:
        report["average_precision"] = float(average_precision_score(y_true, y_score))
        report["roc_auc"] = float(roc_auc_score(y_true, y_score))
    return report


def evaluate_holdout(
    series_by_service: dict[str, list[dict]],
    labels_by_service: dict[str, np.ndarray],
    holdout_fraction: float = 0.25,
    contamination: float = CONTAMINATION,
    window: int = WINDOW,
    random_state: int = 42,
) -> dict:
    if_true: list[int] = []
    if_pred: list[int] = []
    if_score: list[float] = []
    risk_train_x: list[np.ndarray] = []
    risk_train_y: list[np.ndarray] = []
    risk_hold_x: list[np.ndarray] = []
    risk_hold_y: list[np.ndarray] = []

    for name, rows in series_by_service.items():
        labels = np.asarray(labels_by_service[name], dtype=np.int8)
        features = feature_matrix(rows, window)
        n = len(rows)
        split = int(n * (1.0 - holdout_fraction))
        split = max(split, window + 10)
        if split >= n or len(features[window:split]) < 20:
            continue
        scaler, model = fit_isolation_forest(
            features[window:split],
            contamination=contamination,
            random_state=random_state,
        )
        flags, scores = isolation_scores(scaler, model, features[split:])
        if_true.extend(int(value) for value in labels[split:])
        if_pred.extend(int(bool(value)) for value in flags)
        if_score.extend(float(value) for value in scores)

        risk_x = risk_feature_matrix(features)
        risk_train_x.append(risk_x[window:split])
        risk_train_y.append(labels[window:split])
        risk_hold_x.append(risk_x[split:])
        risk_hold_y.append(labels[split:])

    if if_true:
        forest_report = _binary_report(
            np.asarray(if_true, dtype=np.int8),
            np.asarray(if_pred, dtype=np.int8),
            np.asarray(if_score, dtype=np.float64),
        )
    else:
        forest_report = {"skipped": "no holdout rows"}

    if not risk_train_x:
        risk_report: dict = {"skipped": "no training rows"}
    else:
        x_train = np.vstack(risk_train_x)
        y_train = np.concatenate(risk_train_y).astype(np.int8)
        x_hold = np.vstack(risk_hold_x)
        y_hold = np.concatenate(risk_hold_y).astype(np.int8)
        if len(np.unique(y_train)) < 2:
            risk_report = {"skipped": "single class in train"}
        else:
            scaler = StandardScaler()
            x_train_s = scaler.fit_transform(x_train)
            x_hold_s = scaler.transform(x_hold)
            clf = LogisticRegression(
                class_weight="balanced",
                max_iter=800,
                random_state=random_state,
            )
            clf.fit(x_train_s, y_train)
            train_scores = _positive_proba(clf, x_train_s)
            threshold, normal_mean, anomalous_mean = _threshold_from_train(train_scores, y_train)
            hold_scores = _positive_proba(clf, x_hold_s)
            preds = (hold_scores >= threshold).astype(np.int8)
            risk_report = _binary_report(y_hold, preds, hold_scores)
            risk_report["accuracy"] = float(np.mean(preds == y_hold))
            risk_report["threshold"] = threshold
            risk_report["train_normal_mean_proba"] = normal_mean
            risk_report["train_anomalous_mean_proba"] = anomalous_mean
            risk_report["threshold_note"] = (
                "Threshold is the midpoint of the training-split mean probabilities "
                "for normal and anomalous points. It was not fit on the holdout."
            )

    return {
        "holdout_fraction": holdout_fraction,
        "split": "last fraction of each service timeline",
        "isolation_forest": forest_report,
        "failure_risk_logreg": risk_report,
    }


def fit_bundle(
    series_by_service: dict[str, list[dict]],
    labels_by_service: dict[str, np.ndarray],
    contamination: float = CONTAMINATION,
    window: int = WINDOW,
    random_state: int = 42,
) -> dict:
    models: dict[str, dict] = {}
    risk_x_parts: list[np.ndarray] = []
    risk_y_parts: list[np.ndarray] = []
    for name, rows in series_by_service.items():
        features = feature_matrix(rows, window)
        labels = np.asarray(labels_by_service[name], dtype=np.int8)
        scaler, model = fit_isolation_forest(
            features[window:],
            contamination=contamination,
            random_state=random_state,
        )
        models[name] = {"scaler": scaler, "iforest": model}
        risk_x_parts.append(risk_feature_matrix(features)[window:])
        risk_y_parts.append(labels[window:])

    risk_scaler = StandardScaler()
    x_all = np.vstack(risk_x_parts)
    y_all = np.concatenate(risk_y_parts).astype(np.int8)
    x_scaled = risk_scaler.fit_transform(x_all)
    logreg = LogisticRegression(
        class_weight="balanced",
        max_iter=800,
        random_state=random_state,
    )
    logreg.fit(x_scaled, y_all)
    full_scores = _positive_proba(logreg, x_scaled)
    threshold, normal_mean, anomalous_mean = _threshold_from_train(full_scores, y_all)
    return {
        "window": window,
        "contamination": contamination,
        "models": models,
        "risk_scaler": risk_scaler,
        "risk_model": logreg,
        "risk_kind": "logistic_regression",
        "risk_threshold": threshold,
        "risk_normal_mean_proba": normal_mean,
        "risk_anomalous_mean_proba": anomalous_mean,
        "feature_names": [
            f"{metric}_{stat}" for metric in METRIC_NAMES for stat in ("level", "delta", "zscore")
        ],
    }


def save_bundle(bundle: dict) -> None:
    global _bundle
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, BUNDLE_PATH)
    _bundle = bundle


def load_bundle() -> dict | None:
    global _bundle
    if not BUNDLE_PATH.exists():
        _bundle = None
        return None
    _bundle = joblib.load(BUNDLE_PATH)
    return _bundle


def get_bundle() -> dict | None:
    return _bundle


def model_loaded() -> bool:
    return _bundle is not None


def write_metrics_json(holdout: dict, extra: dict | None = None) -> None:
    payload = {
        "data_origin": "synthetic",
        "note": (
            "Holdout scores were computed by backend.app.anomaly on a time-based "
            "split of the synthetic seed. They are not production measurements."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sklearn_version": sklearn.__version__,
        "holdout": holdout,
    }
    if extra:
        payload.update(extra)
    METRICS_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def summarize_window(features: np.ndarray, start: int, end: int) -> str:
    ranked: list[tuple[float, str]] = []
    baseline_start = max(0, start - max(WINDOW, end - start))
    for index, name in enumerate(METRIC_NAMES):
        z_peak = float(np.max(features[start:end, index * 3 + 2]))
        level_now = float(np.median(features[start:end, index * 3]))
        if baseline_start < start:
            level_base = float(np.median(features[baseline_start:start, index * 3]))
        else:
            level_base = level_now
        shift = level_now - level_base
        signal = 0.0
        if z_peak >= 2.5:
            signal = z_peak
        elif name in {"cpu", "memory", "disk"} and shift >= 20:
            signal = shift
        elif name == "error_rate" and shift >= 0.08:
            signal = shift * 50
        elif name == "latency_ms" and shift >= 250:
            signal = shift / 50
        if signal > 0:
            ranked.append((signal, SIGNAL_LABELS[name]))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if ranked:
        strongest = ranked[0][0]
        kept = [text for value, text in ranked if value >= strongest * 0.4][:3]
        label = " and ".join(kept)
    else:
        label = "Multivariate outlier"
    return f"{label} across {end - start} samples (synthetic detection)"


def collapse_flags(
    flags: np.ndarray,
    scores: np.ndarray,
    features: np.ndarray,
    min_run: int = 4,
    max_gap: int = 2,
) -> list[dict]:
    filled = np.asarray(flags, dtype=bool).copy()
    hits = np.flatnonzero(filled)
    for left, right in zip(hits, hits[1:]):
        gap = int(right - left - 1)
        if 0 < gap <= max_gap:
            filled[left:right] = True

    groups: list[tuple[int, int]] = []
    start: int | None = None
    for index, flagged in enumerate(filled):
        if flagged and start is None:
            start = index
        elif not flagged and start is not None:
            if index - start >= min_run:
                groups.append((start, index))
            start = None
    if start is not None and len(filled) - start >= min_run:
        groups.append((start, len(filled)))

    events: list[dict] = []
    for group_start, group_end in groups:
        segment = scores[group_start:group_end]
        peak = group_start + int(np.argmax(segment))
        events.append(
            {
                "index": peak,
                "start_index": group_start,
                "end_index": group_end,
                "score": float(scores[peak]),
                "summary": summarize_window(features, group_start, group_end),
            }
        )
    return events


def detect_series(rows: list[dict], bundle: dict, service_name: str) -> list[dict]:
    model_entry = bundle["models"].get(service_name)
    window = int(bundle["window"])
    if model_entry is None or len(rows) <= window:
        return []
    features = feature_matrix(rows, window)
    flags, scores = isolation_scores(model_entry["scaler"], model_entry["iforest"], features)
    flags = np.asarray(flags, dtype=bool).copy()
    flags[:window] = False
    return collapse_flags(flags, scores, features)


def score_failure_risk(rows: list[dict], bundle: dict | None = None) -> float:
    active = _bundle if bundle is None else bundle
    if active is None or active.get("risk_kind") != "logistic_regression":
        return rule_failure_risk(rows)
    window = int(active["window"])
    if len(rows) <= window:
        return rule_failure_risk(rows)
    features = feature_matrix(rows, window)
    scaled = active["risk_scaler"].transform(risk_feature_matrix(features[-1:]))
    return float(_positive_proba(active["risk_model"], scaled)[0])


def failure_risk_threshold(bundle: dict | None = None) -> float:
    active = _bundle if bundle is None else bundle
    if active is None:
        return 0.5
    return float(active.get("risk_threshold", 0.5))


def refit_unlabeled(series_by_service: dict[str, list[dict]]) -> dict:
    """Refit IsolationForest when joblib is gone but metric rows remain.

    Injection labels are not stored on the rows, so failure risk falls back
    to the heuristic and metrics.json is left as the last labeled run wrote it.
    """
    models: dict[str, dict] = {}
    for name, rows in series_by_service.items():
        if len(rows) <= WINDOW + 20:
            continue
        scaler, model = fit_isolation_forest(feature_matrix(rows)[WINDOW:])
        models[name] = {"scaler": scaler, "iforest": model}
    bundle = {
        "window": WINDOW,
        "contamination": CONTAMINATION,
        "models": models,
        "risk_scaler": None,
        "risk_model": None,
        "risk_kind": "rule",
        "risk_threshold": 0.5,
        "feature_names": [
            f"{metric}_{stat}" for metric in METRIC_NAMES for stat in ("level", "delta", "zscore")
        ],
    }
    save_bundle(bundle)
    return bundle
