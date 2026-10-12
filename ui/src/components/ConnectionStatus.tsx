import type { HealthResponse } from "../api/types";

export type ConnectionState = "checking" | "connected" | "offline" | "error";

interface ConnectionStatusProps {
  state: ConnectionState;
  health?: HealthResponse;
}

const labels: Record<ConnectionState, string> = {
  checking: "Checking backend connection…",
  connected: "Backend connected",
  offline: "Backend is offline",
  error: "Backend unavailable",
};

export function ConnectionStatus({ state, health }: ConnectionStatusProps) {
  return (
    <div className={`connection-status connection-${state}`} role="status">
      <span className="status-dot" aria-hidden="true" />
      <span>{labels[state]}</span>
      {state === "connected" && health?.database && (
        <span className="status-detail">Database: {health.database}</span>
      )}
    </div>
  );
}
