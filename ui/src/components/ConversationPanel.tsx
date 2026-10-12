import type { UiMessage } from "../App";
import { PendingActionCard, type UiPendingAction } from "./PendingActionCard";

interface ConversationPanelProps {
  messages: UiMessage[];
  initializing: boolean;
  pendingActions: UiPendingAction[];
  onActionDecision: (actionId: string, confirm: boolean) => void;
}

export function ConversationPanel({ messages, initializing, pendingActions, onActionDecision }: ConversationPanelProps) {
  if (initializing) {
    return (
      <section className="conversation-panel" aria-label="Conversation" aria-busy="true">
        <div className="empty-state"><p>Loading your conversation…</p></div>
      </section>
    );
  }

  if (messages.length === 0 && pendingActions.length === 0) {
    return (
      <section className="conversation-panel" aria-label="Conversation">
        <div className="empty-state">
          <div className="empty-icon" aria-hidden="true">✦</div>
          <h2>Start a conversation</h2>
          <p>Ask about your home, devices, schedules, or household information.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="conversation-panel" aria-label="Conversation">
      <div className="message-list" aria-live="polite">
        {messages.map((message) => (
          <article className={`message message-${message.role}`} key={message.id}>
            <p className="message-label">{message.role === "user" ? "You" : "Assistant"}</p>
            <p className="message-content">{message.content}</p>
            {message.status === "pending" && <span className="message-status">Sending…</span>}
            {message.status === "failed" && <span className="message-status message-status-error">Not sent. You can try again.</span>}
          </article>
        ))}
        {pendingActions.map((action) => (
          <PendingActionCard key={action.id} action={action} onDecision={onActionDecision} />
        ))}
      </div>
    </section>
  );
}
