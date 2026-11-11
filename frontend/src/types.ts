export interface FleetService {
  id: number;
  name: string;
  environment: string;
  region: string;
  owner: string;
  open_anomalies: number;
  risk_score: number;
}

export interface Anomaly {
  id: number;
  service_id: number;
  service_name: string;
  region: string;
  ts: string;
  score: number;
  summary: string;
  status: string;
  band: "critical" | "warning" | string;
}

export interface MetricPoint {
  ts: string;
  cpu: number;
  memory: number;
  error_rate: number;
  latency_ms: number;
  disk: number;
}

export interface ServiceDetail {
  data_origin: string;
  service: {
    id: number;
    name: string;
    environment: string;
    region: string;
    owner: string;
  };
  risk_score: number;
  metrics: MetricPoint[];
  anomalies: Anomaly[];
}

export interface IncidentComment {
  id: number;
  incident_id: number;
  author: string;
  body: string;
  ts: string;
}

export interface Incident {
  id: number;
  title: string;
  severity: string;
  status: string;
  service_id: number;
  service_name: string;
  summary: string;
  rca_text: string | null;
  created_at: string;
  comments: IncidentComment[];
  similarity?: number;
}

export interface SloRow {
  service_id: number;
  name: string;
  region: string;
  latency_ms_target: number | null;
  error_rate_target: number | null;
  samples: number;
  latency_ms_observed: number | null;
  error_rate_observed: number | null;
  latency_breach: boolean;
  error_breach: boolean;
  breaching: boolean;
  breach_on: string[];
}

export interface AlertItem {
  id: number;
  service_id: number;
  service_name: string;
  region: string;
  rule_id: number;
  rule_name: string;
  metric: string;
  comparator: string;
  threshold: number;
  consecutive: number;
  status: string;
  opened_at: string;
  summary: string;
}

export interface StatusService {
  name: string;
  region: string;
  status: "up" | "degraded" | "down" | string;
}

export interface StatusFeed {
  data_origin: string;
  generated_at: string;
  window_hours: number;
  note: string;
  services: StatusService[];
}

export interface Overview {
  data_origin: string;
  risk_threshold: number;
  slo_window_hours: number;
  counts: {
    services: number;
    open_anomalies: number;
    acked_anomalies: number;
    open_incidents: number;
    slo_breaches: number;
    open_alerts: number;
  };
  slos: SloRow[];
  open_alerts: AlertItem[];
  regions: Array<{
    region: string;
    services: number;
    open_anomalies: number;
    highest_risk: number;
  }>;
  fleet: FleetService[];
  open_anomalies: Anomaly[];
  services_at_risk: Array<{
    service_id: number;
    name: string;
    region: string;
    environment: string;
    risk_score: number;
    open_anomalies: number;
    reason: string;
  }>;
}

export interface RcaResult {
  data_origin: string;
  incident: Incident;
  similar: Incident[];
}
