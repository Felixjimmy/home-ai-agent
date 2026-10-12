import type { VoiceOutputState } from "../voiceSynthesis";

interface VoiceOutputControlProps {
  enabled: boolean;
  supported: boolean;
  state: VoiceOutputState;
  error?: string;
  onEnabledChange: (enabled: boolean) => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
}

function statusMessage(supported: boolean, enabled: boolean, state: VoiceOutputState): string {
  if (!supported || state === "unsupported") return "Speech synthesis is unavailable. Text replies remain available.";
  if (!enabled) return "Spoken replies are off.";
  if (state === "speaking") return "Speaking the latest assistant reply.";
  if (state === "paused") return "Spoken reply paused.";
  if (state === "error") return "Spoken reply failed.";
  return "New assistant replies will be spoken automatically.";
}

export function VoiceOutputControl({
  enabled,
  supported,
  state,
  error,
  onEnabledChange,
  onPause,
  onResume,
  onStop,
}: VoiceOutputControlProps) {
  const active = state === "speaking" || state === "paused";

  return (
    <section className={`voice-output-row voice-output-state-${state}`} aria-label="Voice output controls">
      <label className="voice-output-toggle">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(event) => onEnabledChange(event.target.checked)}
        />
        <span>Spoken replies</span>
      </label>
      <div className="voice-output-buttons">
        {state === "paused" ? (
          <button type="button" onClick={onResume} disabled={!enabled || !supported} aria-label="Resume spoken reply">
            Resume
          </button>
        ) : (
          <button type="button" onClick={onPause} disabled={!enabled || !supported || state !== "speaking"} aria-label="Pause spoken reply">
            Pause
          </button>
        )}
        <button type="button" onClick={onStop} disabled={!enabled || !supported || !active} aria-label="Stop spoken reply">
          Stop
        </button>
      </div>
      <span className="voice-output-status" role="status" aria-live="polite">
        {error ?? statusMessage(supported, enabled, state)}
      </span>
    </section>
  );
}
