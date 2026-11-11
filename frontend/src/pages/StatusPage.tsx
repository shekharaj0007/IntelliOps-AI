import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, getToken, loadStatus } from "../api";
import { formatTime } from "../format";
import type { StatusFeed } from "../types";

export function StatusPage() {
  const [data, setData] = useState<StatusFeed | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    loadStatus()
      .then((feed) => {
        if (alive) setData(feed);
      })
      .catch((err: unknown) => {
        if (!alive) return;
        setError(err instanceof ApiError ? err.message : "Could not load status");
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="login-wrap">
      <div className="status-card stack">
        <div className="brand">
          <span className="mark" aria-hidden="true" />
          <div>
            <div className="wordmark">
              INTELLIOPS <span>AI</span>
            </div>
            <div className="brand-sub">Status</div>
          </div>
          <span className="badge">Synthetic</span>
        </div>
        <p className="lede">
          Read-only feed. Up, degraded, and down come from open anomalies and SLO breach on the latest synthetic samples.
          Signing in is not required.
        </p>
        {error ? <p className="form-error">{error}</p> : null}
        {!data && !error ? <p className="muted">Loading status…</p> : null}
        {data ? (
          <>
            <ul className="status-list">
              {data.services.map((service) => (
                <li key={service.name}>
                  <strong>{service.name}</strong>
                  <span className="mono muted">{service.region}</span>
                  <span className={`status-pill status-${service.status}`}>{service.status}</span>
                </li>
              ))}
            </ul>
            <p className="hint">
              {data.note} Generated {formatTime(data.generated_at)}.
            </p>
          </>
        ) : null}
        <p className="hint">
          {getToken() ? <Link to="/">Back to the console</Link> : <Link to="/login">Sign in</Link>}
        </p>
      </div>
    </div>
  );
}
