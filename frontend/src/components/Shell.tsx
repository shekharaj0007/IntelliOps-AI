import type { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { clearSession, getEmail } from "../api";

export function Shell({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const email = getEmail() ?? "operator";

  function signOut() {
    clearSession();
    navigate("/login", { replace: true });
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="mark" aria-hidden="true" />
          <div>
            <div className="wordmark">
              INTELLIOPS <span>AI</span>
            </div>
            <div className="brand-sub">Operations console</div>
          </div>
        </div>
        <nav className="nav">
          <NavLink to="/" end>
            Overview
          </NavLink>
          <NavLink to="/incidents">Incidents</NavLink>
        </nav>
        <div className="who">
          <span className="badge">Synthetic</span>
          <span className="email">{email}</span>
          <button type="button" className="ghost" onClick={signOut}>
            Sign out
          </button>
        </div>
      </header>
      <p className="banner">Synthetic metrics and incidents. This console is a local prototype, not a live environment.</p>
      <main className="main">{children}</main>
    </div>
  );
}
