from __future__ import annotations

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from backend.app.models import Anomaly, Incident


def incident_text(incident: Incident) -> str:
    return " ".join(
        part for part in (incident.title, incident.summary, incident.rca_text or "") if part
    )


def rank_similar(
    incidents: list[Incident],
    query: str,
    limit: int = 5,
    exclude_id: int | None = None,
) -> list[tuple[Incident, float]]:
    pool = [item for item in incidents if item.id != exclude_id]
    if not pool or not query.strip():
        return []
    corpus = [incident_text(item) for item in pool]
    try:
        matrix = TfidfVectorizer(stop_words="english").fit_transform(corpus + [query])
    except ValueError:
        return []
    sims = cosine_similarity(matrix[-1], matrix[:-1]).ravel()
    order = np_argsort_desc(sims)
    ranked: list[tuple[Incident, float]] = []
    for index in order:
        score = float(sims[index])
        if score <= 0:
            continue
        ranked.append((pool[index], score))
        if len(ranked) >= limit:
            break
    return ranked


def np_argsort_desc(values) -> list[int]:
    return sorted(range(len(values)), key=lambda index: float(values[index]), reverse=True)


def playbook_rca(
    service_name: str,
    title: str,
    anomalies: list[Anomaly],
    similar: list[tuple[Incident, float]],
) -> str:
    lines = [
        f"Playbook RCA for '{title}' on {service_name}.",
        (
            "Source: synthetic operations data. This note is assembled from recent anomaly "
            "signals and similar past incidents. No external language model was called."
        ),
    ]
    if not anomalies:
        lines.append(
            "No anomalies are on file for this service. Compare the latest error rate and "
            "latency with the service baseline before declaring customer impact."
        )
    else:
        lines.append("Recent anomaly signals:")
        for anomaly in anomalies[:6]:
            lines.append(
                f"- {anomaly.summary} (score {anomaly.score:.3f}, status {anomaly.status})"
            )
        blob = " ".join(anomaly.summary.lower() for anomaly in anomalies)
        if "cpu" in blob:
            lines.append(
                "CPU playbook: check the last deploy, runaway workers, and noisy neighbors. "
                "If CPU stays pinned, scale the service or roll back."
            )
        if "error" in blob:
            lines.append(
                "Error-rate playbook: split 5xx by route, look for a bad config or a failing "
                "dependency, and roll back the newest change if the burst started with a deploy."
            )
        if "latency" in blob:
            lines.append(
                "Latency playbook: check thread pools, downstream timeouts, and lock contention. "
                "A latency cliff with flat CPU often points at a dependency."
            )
        if "memory" in blob:
            lines.append(
                "Memory playbook: look for a leak or a cache that stopped evicting. Capture a "
                "heap snapshot before restarting if usage is still climbing."
            )
        if "disk" in blob:
            lines.append(
                "Disk playbook: check volume headroom, inode use, and log rotation before the "
                "volume fills."
            )
    if similar:
        lines.append("Similar past incidents (TF-IDF over title, summary, and RCA text):")
        for incident, score in similar[:3]:
            prior = (incident.rca_text or incident.summary).replace("\n", " ")
            if len(prior) > 220:
                prior = prior[:217] + "..."
            lines.append(
                f"- #{incident.id} {incident.title} [{incident.status}, similarity {score:.2f}]: {prior}"
            )
    else:
        lines.append("No similar past incident text matched this case.")
    lines.append(
        "Next steps: confirm customer impact, acknowledge the open anomaly, page the service "
        "owner, and record whether a rollback cleared the signal."
    )
    return "\n".join(lines)
