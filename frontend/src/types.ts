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
  similarity?: number;
}

export interface Overview {
  data_origin: string;
  risk_threshold: number;
  counts: {
    services: number;
    open_anomalies: number;
    acked_anomalies: number;
    open_incidents: number;
  };
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
