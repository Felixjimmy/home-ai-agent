interface MessageComposerProps {
  draft: string;
  disabled: boolean;
  onDraftChange: (draft: string) => void;
  onSubmit: () => void;
  interimTranscript: string;
}

export function MessageComposer({ draft, disabled, onDraftChange, onSubmit, interimTranscript }: MessageComposerProps) {
  return (
    <form className="composer" onSubmit={(event) => { event.preventDefault(); onSubmit(); }}>
      <label className="sr-only" htmlFor="message-input">Message</label>
      <textarea
        id="message-input"
        placeholder="Ask your assistant…"
        rows={1}
        value={draft}
        disabled={disabled}
        onChange={(event) => onDraftChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            onSubmit();
          }
        }}
        aria-describedby="composer-note"
      />
      <button type="submit" disabled={disabled || !draft.trim()} aria-label="Send message">Send</button>
      <p id="composer-note" className="phase-note">
        {interimTranscript ? <>Hearing: <span className="interim-transcript">{interimTranscript}</span></> : "Press Enter to send · Shift+Enter for a new line."}
      </p>
    </form>
  );
}
