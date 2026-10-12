interface AssistantHeaderProps {
  onNewConversation: () => void;
  disabled: boolean;
}

export function AssistantHeader({ onNewConversation, disabled }: AssistantHeaderProps) {
  return (
    <header className="assistant-header">
      <div>
        <p className="eyebrow">HOME AI</p>
        <h1>Home Assistant</h1>
        <p className="subtitle">
          Your household assistant for questions, information, and actions.
        </p>
      </div>
      <div className="header-actions">
        <button className="new-conversation" type="button" onClick={onNewConversation} disabled={disabled}>
          New conversation
        </button>
        <div className="header-mark" aria-hidden="true">⌂</div>
      </div>
    </header>
  );
}
