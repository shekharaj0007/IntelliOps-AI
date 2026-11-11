import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { addComment, ApiError, createIncident, generateRca, loadIncidents, loadServices, searchSimilar } from "../api";
import { formatTime } from "../format";
import type { FleetService, Incident, RcaResult } from "../types";

export function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [services, setServices] = useState<FleetService[]>([]);
  const [error, setError] = useState("");
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [severity, setSeverity] = useState("high");
  const [serviceId, setServiceId] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [rcaBusy, setRcaBusy] = useState<number | null>(null);
  const [rca, setRca] = useState<RcaResult | null>(null);
  const [query, setQuery] = useState("latency cliff");
  const [similar, setSimilar] = useState<Incident[]>([]);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [commentBusy, setCommentBusy] = useState<number | null>(null);

  async function reload() {
    const [incidentBody, serviceBody] = await Promise.all([loadIncidents(), loadServices()]);
    setIncidents(incidentBody.incidents);
    setServices(serviceBody.services);
    setServiceId((current) => current || serviceBody.services[0]?.id || "");
  }

  useEffect(() => {
    let alive = true;
    Promise.all([loadIncidents(), loadServices()])
      .then(([incidentBody, serviceBody]) => {
        if (!alive) return;
        setIncidents(incidentBody.incidents);
        setServices(serviceBody.services);
        setServiceId(serviceBody.services[0]?.id ?? "");
      })
      .catch((err: unknown) => {
        if (!alive) return;
        if (err instanceof ApiError && err.status === 401) return;
        setError(err instanceof Error ? err.message : "Could not load incidents");
      });
    return () => {
      alive = false;
    };
  }, []);

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    if (serviceId === "") return;
    setBusy(true);
    setError("");
    try {
      await createIncident({ title, summary, severity, service_id: serviceId });
      setTitle("");
      setSummary("");
      await reload();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return;
      setError(err instanceof Error ? err.message : "Could not create the incident");
    } finally {
      setBusy(false);
    }
  }

  async function onRca(id: number) {
    setRcaBusy(id);
    setError("");
    try {
      const result = await generateRca(id);
      setRca(result);
      await reload();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return;
      setError(err instanceof Error ? err.message : "Could not generate RCA");
    } finally {
      setRcaBusy(null);
    }
  }

  async function onComment(event: FormEvent, incidentId: number) {
    event.preventDefault();
    const body = (drafts[incidentId] ?? "").trim();
    if (!body) return;
    setCommentBusy(incidentId);
    setError("");
    try {
      await addComment(incidentId, body);
      setDrafts((current) => ({ ...current, [incidentId]: "" }));
      await reload();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return;
      setError(err instanceof Error ? err.message : "Could not add the comment");
    } finally {
      setCommentBusy(null);
    }
  }

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const body = await searchSimilar(query);
      setSimilar(body.results);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return;
      setError(err instanceof Error ? err.message : "Search failed");
    }
  }

  return (
    <div className="stack">
      <div className="split">
        <section className="panel grow">
          <h2>Incidents</h2>
          {error ? <p className="form-error">{error}</p> : null}
          {incidents.length === 0 ? (
            <p className="muted">No incidents yet.</p>
          ) : (
            <ul className="incident-list">
              {incidents.map((incident) => (
                <li key={incident.id}>
                  <div className="incident-top">
                    <strong>{incident.title}</strong>
                    <span className={`band band-${incident.severity === "critical" ? "critical" : "warning"}`}>
                      {incident.severity}
                    </span>
                    <span className={`status status-${incident.status}`}>{incident.status}</span>
                  </div>
                  <p className="muted">
                    <Link to={`/services/${incident.service_id}`}>{incident.service_name}</Link>
                    <span className="mono"> · {formatTime(incident.created_at)}</span>
                  </p>
                  <p>{incident.summary}</p>
                  <div className="comments">
                    <div className="comment-label">Comments</div>
                    {(incident.comments ?? []).length === 0 ? (
                      <p className="muted">No comments yet.</p>
                    ) : (
                      <ul className="comment-list">
                        {(incident.comments ?? []).map((comment) => (
                          <li key={comment.id}>
                            <div className="mono muted">
                              {comment.author} · {formatTime(comment.ts)}
                            </div>
                            <p>{comment.body}</p>
                          </li>
                        ))}
                      </ul>
                    )}
                    <form className="comment-form" onSubmit={(event) => onComment(event, incident.id)}>
                      <label>
                        Add a comment
                        <textarea
                          value={drafts[incident.id] ?? ""}
                          onChange={(event) =>
                            setDrafts((current) => ({ ...current, [incident.id]: event.target.value }))
                          }
                          rows={2}
                          maxLength={2000}
                          placeholder="Synthetic note for this incident"
                        />
                      </label>
                      <button type="submit" className="ghost" disabled={commentBusy === incident.id || !(drafts[incident.id] ?? "").trim()}>
                        {commentBusy === incident.id ? "Saving…" : "Add comment"}
                      </button>
                    </form>
                  </div>
                  {incident.rca_text ? <pre className="rca">{incident.rca_text}</pre> : null}
                  <button type="button" className="ghost" disabled={rcaBusy === incident.id} onClick={() => onRca(incident.id)}>
                    {rcaBusy === incident.id ? "Writing RCA…" : "Generate RCA"}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <aside className="stack side">
          <form className="panel stack" onSubmit={onCreate}>
            <h2>Open an incident</h2>
            <label>
              Title
              <input value={title} onChange={(event) => setTitle(event.target.value)} required minLength={3} />
            </label>
            <label>
              Service
              <select
                value={serviceId}
                onChange={(event) => setServiceId(Number(event.target.value))}
                required
              >
                {services.map((service) => (
                  <option key={service.id} value={service.id}>
                    {service.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Severity
              <select value={severity} onChange={(event) => setSeverity(event.target.value)}>
                <option value="low">low</option>
                <option value="medium">medium</option>
                <option value="high">high</option>
                <option value="critical">critical</option>
              </select>
            </label>
            <label>
              Summary
              <textarea value={summary} onChange={(event) => setSummary(event.target.value)} required minLength={3} rows={4} />
            </label>
            <button type="submit" disabled={busy || serviceId === ""}>
              {busy ? "Saving…" : "Create incident"}
            </button>
          </form>

          <form className="panel stack" onSubmit={onSearch}>
            <h2>Similar incidents</h2>
            <label>
              Search text
              <input value={query} onChange={(event) => setQuery(event.target.value)} />
            </label>
            <button type="submit" className="ghost">
              Search
            </button>
            <ul className="similar-list">
              {similar.map((item) => (
                <li key={item.id}>
                  <strong>{item.title}</strong>
                  <div className="mono muted">
                    {item.service_name} · similarity {item.similarity?.toFixed(2)}
                  </div>
                </li>
              ))}
            </ul>
          </form>
        </aside>
      </div>

      {rca ? (
        <section className="panel">
          <h2>Latest playbook RCA</h2>
          <p className="muted">{rca.incident.title}</p>
          <pre className="rca">{rca.incident.rca_text}</pre>
          {rca.similar.length > 0 ? (
            <ul className="similar-list">
              {rca.similar.map((item) => (
                <li key={item.id}>
                  <strong>{item.title}</strong>
                  <div className="mono muted">similarity {item.similarity?.toFixed(2)}</div>
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
