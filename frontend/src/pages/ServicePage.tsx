import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ackAnomaly, ApiError, loadService } from "../api";
import { Sparkline } from "../components/Sparkline";
import { formatRisk, formatTime } from "../format";
import type { MetricPoint, ServiceDetail } from "../types";

const SERIES: Array<{
  key: keyof Pick<MetricPoint, "cpu" | "memory" | "disk" | "latency_ms" | "error_rate">;
  label: string;
  color: string;
  format: (value: number) => string;
}> = [
  { key: "cpu", label: "CPU %", color: "var(--amber)", format: (value) => value.toFixed(1) },
  { key: "memory", label: "Memory %", color: "var(--ok)", format: (value) => value.toFixed(1) },
  { key: "disk", label: "Disk %", color: "var(--info)", format: (value) => value.toFixed(1) },
  { key: "latency_ms", label: "Latency ms", color: "var(--red)", format: (value) => value.toFixed(0) },
  {
    key: "error_rate",
    label: "Error %",
    color: "#ffb4a8",
    format: (value) => (value * 100).toFixed(2),
  },
];

export function ServicePage() {
  const params = useParams();
  const id = Number(params.id);
  const [data, setData] = useState<ServiceDetail | null>(null);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  useEffect(() => {
    if (!Number.isFinite(id)) {
      setError("Unknown service");
      return;
    }
    let alive = true;
    setData(null);
    loadService(id)
      .then((detail) => {
        if (alive) setData(detail);
      })
      .catch((err: unknown) => {
        if (!alive) return;
        if (err instanceof ApiError && err.status === 401) return;
        setError(err instanceof Error ? err.message : "Could not load the service");
      });
    return () => {
      alive = false;
    };
  }, [id]);

  async function ack(anomalyId: number) {
    setBusyId(anomalyId);
    try {
      await ackAnomaly(anomalyId);
      setData(await loadService(id));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return;
      setError(err instanceof Error ? err.message : "Could not acknowledge");
    } finally {
      setBusyId(null);
    }
  }

  if (error && !data) return <p className="form-error">{error}</p>;
  if (!data) return <p className="muted">Loading service…</p>;

  const latest = data.metrics[data.metrics.length - 1];
  const recent = [...data.metrics].slice(-18).reverse();

  return (
    <div className="stack">
      <p className="crumb">
        <Link to="/">Overview</Link> / {data.service.name}
      </p>
      <header className="detail-head">
        <div>
          <h1>{data.service.name}</h1>
          <p className="mono muted">
            {data.service.region} · {data.service.environment} · owner {data.service.owner}
          </p>
        </div>
        <div className="risk-pill">
          <span>Failure risk</span>
          <strong>{formatRisk(data.risk_score)}</strong>
        </div>
      </header>
      {error ? <p className="form-error">{error}</p> : null}

      <section className="chart-grid">
        {SERIES.map((series) => (
          <article key={series.key} className="panel">
            <div className="chart-label">
              <span>{series.label}</span>
              <strong className="mono">{latest ? series.format(latest[series.key]) : "—"}</strong>
            </div>
            <Sparkline values={data.metrics.map((point) => point[series.key])} color={series.color} />
          </article>
        ))}
      </section>

      <section>
        <h2>Recent samples</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>CPU</th>
                <th>Memory</th>
                <th>Disk</th>
                <th>Latency</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((point) => (
                <tr key={point.ts}>
                  <td className="mono">{formatTime(point.ts)}</td>
                  <td>
                    <Bar value={point.cpu} />
                    <span className="mono">{point.cpu.toFixed(1)}</span>
                  </td>
                  <td className="mono">{point.memory.toFixed(1)}</td>
                  <td className="mono">{point.disk.toFixed(1)}</td>
                  <td className="mono">{point.latency_ms.toFixed(0)}</td>
                  <td className="mono">{(point.error_rate * 100).toFixed(2)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2>Anomalies</h2>
        {data.anomalies.length === 0 ? (
          <p className="muted">No grouped anomalies for this service.</p>
        ) : (
          <ul className="anomaly-list">
            {data.anomalies.map((anomaly) => (
              <li key={anomaly.id}>
                <div>
                  <span className={`band band-${anomaly.band}`}>{anomaly.band}</span>
                  <span className="mono muted">{formatTime(anomaly.ts)}</span>
                  <span className="mono">score {anomaly.score.toFixed(3)}</span>
                  <span className={`status status-${anomaly.status}`}>{anomaly.status}</span>
                </div>
                <p>{anomaly.summary}</p>
                {anomaly.status === "open" ? (
                  <button type="button" className="ghost" disabled={busyId === anomaly.id} onClick={() => ack(anomaly.id)}>
                    {busyId === anomaly.id ? "Ack…" : "Ack"}
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Bar({ value }: { value: number }) {
  return (
    <span className="inline-bar" aria-hidden="true">
      <span style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </span>
  );
}
