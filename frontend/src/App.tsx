import { Navigate, Route, Routes } from "react-router-dom";
import type { ReactElement } from "react";
import { getToken } from "./api";
import { Shell } from "./components/Shell";
import { IncidentsPage } from "./pages/IncidentsPage";
import { LoginPage } from "./pages/LoginPage";
import { OverviewPage } from "./pages/OverviewPage";
import { ServicePage } from "./pages/ServicePage";
import { StatusPage } from "./pages/StatusPage";

function RequireAuth({ children }: { children: ReactElement }) {
  if (!getToken()) return <Navigate to="/login" replace />;
  return <Shell>{children}</Shell>;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/status" element={<StatusPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <OverviewPage />
          </RequireAuth>
        }
      />
      <Route
        path="/services/:id"
        element={
          <RequireAuth>
            <ServicePage />
          </RequireAuth>
        }
      />
      <Route
        path="/incidents"
        element={
          <RequireAuth>
            <IncidentsPage />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
