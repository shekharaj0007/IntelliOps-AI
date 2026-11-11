import { FormEvent, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { ApiError, getToken, login } from "../api";

export function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("operator@intelliops.ai");
  const [password, setPassword] = useState("operator123");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (getToken()) return <Navigate to="/" replace />;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email, password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={onSubmit}>
        <div className="brand">
          <span className="mark" aria-hidden="true" />
          <div>
            <div className="wordmark">
              INTELLIOPS <span>AI</span>
            </div>
            <div className="brand-sub">Operations console</div>
          </div>
        </div>
        <p className="lede">
          Sign in to review fleet health, acknowledge anomalies, and draft a playbook RCA. The metrics behind this demo are synthetic.
        </p>
        <label>
          Email
          <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" autoComplete="username" required />
        </label>
        <label>
          Password
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            autoComplete="current-password"
            required
          />
        </label>
        {error ? <p className="form-error">{error}</p> : null}
        <button type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Enter console"}
        </button>
        <p className="hint">
          Demo operator <span className="mono">operator@intelliops.ai</span> / <span className="mono">operator123</span>
        </p>
      </form>
    </div>
  );
}
