import type { PendingActionSummary, PendingActionUiState } from "../api/types";

export interface UiPendingAction extends PendingActionSummary {
  state: PendingActionUiState;
  result?: unknown;
  error?: string;
}

interface PendingActionCardProps {
  action: UiPendingAction;
  onDecision: (actionId: string, confirm: boolean) => void;
}

const toolLabels: Record<string, string> = {
  add_to_shopping_list: "Shopping list change",
  add_calendar_event: "Calendar change",
  set_device_state: "Device change",
};

function formatExpiry(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function formatResult(result: unknown): string | undefined {
  if (result === undefined || result === null) return undefined;
  if (typeof result === "string") return result;
  try {
    return JSON.stringify(result, null, 2);
  } catch {
    return "The action completed, but its result could not be displayed.";
  }
}

function statusText(action: UiPendingAction): string {
  switch (action.state) {
    case "confirming": return "Updating…";
    case "confirmed": return "Confirmed";
    case "already_completed": return "Already completed";
    case "rejected": return "Rejected — no change was made";
    case "expired": return "Expired — ask the assistant to propose it again";
    case "failed": return action.error ?? "Could not complete this action. You can try again.";
    default: return `Pending · expires ${formatExpiry(action.expires_at)}`;
  }
}

export function PendingActionCard({ action, onDecision }: PendingActionCardProps) {
  const interactive = action.state === "pending" || action.state === "failed";
  const result = formatResult(action.result);
  return (
    <article className={`pending-action-card action-${action.state}`} aria-label="Pending action">
      <p className="action-label">{toolLabels[action.tool_name] ?? "Assistant action"}</p>
      <p className="action-description">{action.description}</p>
      <p className="action-status" role="status">{statusText(action)}</p>
      {result && <pre className="action-result">{result}</pre>}
      {interactive && (
        <div className="action-buttons">
          <button type="button" onClick={() => onDecision(action.id, true)} disabled={action.state === "confirming"}>Confirm</button>
          <button type="button" className="action-reject" onClick={() => onDecision(action.id, false)} disabled={action.state === "confirming"}>Reject</button>
        </div>
      )}
    </article>
  );
}
