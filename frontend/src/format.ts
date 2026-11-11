export function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function formatRisk(value: number): string {
  return value.toFixed(2);
}

export function formatLatency(value: number | null): string {
  if (value == null) return "n/a";
  return `${Math.round(value)} ms`;
}

export function formatErrorPct(value: number | null): string {
  if (value == null) return "n/a";
  return `${(value * 100).toFixed(2)}%`;
}
