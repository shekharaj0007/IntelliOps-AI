import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ackAlert, ackAnomaly, ApiError, loadOverview } from "../api";
import { formatErrorPct, formatLatency, formatRisk, formatTime } from "../format";
import type { Overview } from "../types";

export function OverviewPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [busyAlertId, setBusyAlertId] = useState<number | null>(null);

  async function load() {
    try {
      setData(await loadOverview());
      setError("");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return;
      setError(err instanceof Error ? err.message : "Could not load the fleet");
    }
  }

  useEffect(() => {
    let alive = true;
    loadOverview()
      .then((overview) => {
        if (alive) setData(overview);
      })
      .catch((err: unknown) => {
        if (!alive) return;
        if (err instanceof ApiError && err.status === 401) return;
        setError(err instanceof Error ? err.message : "Could not load the fleet");
      });
    return () => {
      alive = false;
    };
  }, []);

  async function ackAlertRow(id: number) {
    setBusyAlertId(id);
    try {
      await ackAlert(id);
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return;
      setError(err instanceof Error ? err.message : "Could not acknowledge the alert");
    } finally {
      setBusyAlertId(null);
    }
  }

  async function ack(id: number) {
    setBusyId(id);
    try {
      await ackAnomaly(id);
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return;
      setError(err instanceof Error ? err.message : "Could not acknowledge");
    } finally {
      setBusyId(null);
    }
  }

  if (error && !data) return <p className="form-error">{error}</p>;
  if (!data) return <p className="muted">Loading fleet…</p>;

  return (
    <div className="stack">
      {error ? <p className="form-error">{error}</p> : null}
      <section className="stat-grid">
        <Stat label="Services" value={String(data.counts.services)} />
        <Stat label="Open anomalies" value={String(data.counts.open_anomalies)} tone={data.counts.open_anomalies ? "critical" : "ok"} />
        <Stat label="Acked" value={String(data.counts.acked_anomalies)} />
        <Stat label="Open incidents" value={String(data.counts.open_incidents)} tone={data.counts.open_incidents ? "warn" : "ok"} />
        <Stat label="SLO breaches" value={String(data.counts.slo_breaches)} tone={data.counts.slo_breaches ? "critical" : "ok"} />
        <Stat label="Open alerts" value={String(data.counts.open_alerts)} tone={data.counts.open_alerts ? "warn" : "ok"} />
      </section>

      <section>
        <h2>SLO, last {data.slo_window_hours} hours</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Service</th>
                <th>Latency</th>
                <th>Error rate</th>
                <th>Window</th>
              </tr>
            </thead>
            <tbody>
              {data.slos.map((slo) => (
                <tr key={slo.service_id} className={slo.breaching ? "row-breach" : undefined}>
                  <td>
                    <Link to={`/services/${slo.service_id}`}>{slo.name}</Link>
                    <div className="mono muted">{slo.region}</div>
                  </td>
                  <td className="mono">
                    {formatLatency(slo.latency_ms_observed)}
                    <span className="muted"> / {formatLatency(slo.latency_ms_target)}</span>
                  </td>
                  <td className="mono">
                    {formatErrorPct(slo.error_rate_observed)}
                    <span className="muted"> / {formatErrorPct(slo.error_rate_target)}</span>
                  </td>
                  <td>
                    {slo.breaching ? (
                      <span className="band band-critical">{slo.breach_on.join(", ")}</span>
                    ) : (
                      <span className="status status-resolved">inside</span>
                    )}
                    <div className="mono muted">{slo.samples} samples</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="hint">
          Observed values are means of the last {data.slo_window_hours} hours of synthetic samples. Targets are seeded.
          A breach is a mean above the target. These are not measured production SLOs.
        </p>
      </section>

      <section>
        <h2>Open alerts</h2>
        {data.open_alerts.length === 0 ? (
          <p className="muted">No open alerts. Rules are checked against the latest synthetic samples when the API starts.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Service</th>
                  <th>Rule</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.open_alerts.map((alert) => (
                  <tr key={alert.id}>
                    <td className="mono">{formatTime(alert.opened_at)}</td>
                    <td>
                      <Link to={`/services/${alert.service_id}`}>{alert.service_name}</Link>
                      <div className="mono muted">{alert.region}</div>
                    </td>
                    <td>
                      <strong>{alert.rule_name}</strong>
                      <div className="muted">{alert.summary}</div>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="ghost"
                        disabled={busyAlertId === alert.id}
                        onClick={() => ackAlertRow(alert.id)}
                      >
                        {busyAlertId === alert.id ? "Ack…" : "Ack"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <h2>Regions</h2>
        <div className="region-grid">
          {data.regions.map((region) => (
            <article key={region.region} className="panel">
              <div className="mono region-name">{region.region}</div>
              <p>
                {region.services} services · {region.open_anomalies} open
              </p>
              <p className="muted">Highest failure risk {formatRisk(region.highest_risk)}</p>
            </article>
          ))}
        </div>
      </section>

      <section>
        <h2>Fleet health</h2>
        <div className="fleet-grid">
          {data.fleet.map((service) => (
            <Link key={service.id} to={`/services/${service.id}`} className="fleet-cell">
              <div className="fleet-top">
                <strong>{service.name}</strong>
                <span className={service.risk_score >= data.risk_threshold ? "risk hot" : "risk"}>
                  {formatRisk(service.risk_score)}
                </span>
              </div>
              <div className="mono muted">
                {service.region} · {service.environment} · {service.owner}
              </div>
              <div className="meter" aria-hidden="true">
                <span style={{ width: `${Math.min(100, service.risk_score * 100)}%` }} />
              </div>
              <div className="muted">{service.open_anomalies} open</div>
            </Link>
          ))}
        </div>
      </section>

      <section>
        <h2>Services at risk</h2>
        {data.services_at_risk.length === 0 ? (
          <p className="muted">Nothing is over the failure-risk threshold and no anomalies are open.</p>
        ) : (
          <ul className="risk-list">
            {data.services_at_risk.map((service) => (
              <li key={service.service_id}>
                <Link to={`/services/${service.service_id}`}>{service.name}</Link>
                <span className="mono">{formatRisk(service.risk_score)}</span>
                <span className="muted">{service.reason}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="hint">Failure-risk threshold from the fitted model: {formatRisk(data.risk_threshold)}.</p>
      </section>

      <section>
        <h2>Open anomalies</h2>
        {data.open_anomalies.length === 0 ? (
          <p className="muted">No open anomalies.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Service</th>
                  <th>Signal</th>
                  <th>Score</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.open_anomalies.map((anomaly) => (
                  <tr key={anomaly.id}>
                    <td className="mono">{formatTime(anomaly.ts)}</td>
                    <td>
                      <Link to={`/services/${anomaly.service_id}`}>{anomaly.service_name}</Link>
                      <div className="mono muted">{anomaly.region}</div>
                    </td>
                    <td>
                      <span className={`band band-${anomaly.band}`}>{anomaly.band}</span>
                      {anomaly.summary}
                    </td>
                    <td className="mono">{anomaly.score.toFixed(3)}</td>
                    <td>
                      <button type="button" className="ghost" disabled={busyId === anomaly.id} onClick={() => ack(anomaly.id)}>
                        {busyId === anomaly.id ? "Ack…" : "Ack"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "ok" | "warn" | "critical" }) {
  return (
    <article className={`stat ${tone ?? ""}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
    </article>
  );
}
