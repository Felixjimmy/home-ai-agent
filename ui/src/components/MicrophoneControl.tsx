import { useEffect, useRef, useState } from "react";
import {
  isSpeechRecognitionSupported,
  VoiceRecognitionController,
  type VoiceRecognitionError,
  type VoiceRecognitionState,
} from "../voiceRecognition";

interface MicrophoneControlProps {
  disabled: boolean;
  onInterimTranscript: (transcript: string) => void;
  onFinalTranscript: (transcript: string) => void;
  onVoiceInputStart: () => void;
}

function errorMessage(error: VoiceRecognitionError): string {
  if (error === "permission-denied") return "Microphone permission was denied. You can still type your message.";
  if (error === "aborted") return "Voice input stopped. You can try again or edit the draft.";
  return "Voice input is temporarily unavailable. You can still type your message.";
}

export function MicrophoneControl({ disabled, onInterimTranscript, onFinalTranscript, onVoiceInputStart }: MicrophoneControlProps) {
  const [state, setState] = useState<VoiceRecognitionState>(() =>
    isSpeechRecognitionSupported() ? "idle" : "unsupported",
  );
  const [error, setError] = useState<string>();
  const controllerRef = useRef<VoiceRecognitionController | undefined>(undefined);

  useEffect(() => {
    const controller = new VoiceRecognitionController({
      onInterimTranscript,
      onFinalTranscript,
      onStateChange: (nextState) => {
        setState(nextState);
        if (nextState !== "error") setError(undefined);
      },
      onError: (nextError) => {
        setState("error");
        setError(errorMessage(nextError));
        onInterimTranscript("");
      },
    });
    controllerRef.current = controller;
    return () => controller.dispose();
  }, [onFinalTranscript, onInterimTranscript]);

  const unavailable = state === "unsupported";
  const listening = state === "listening";
  const buttonDisabled = disabled || unavailable || state === "processing";
  const label = listening ? "Stop voice input" : "Start voice input";

  return (
    <div className={`microphone-row microphone-state-${state}`}>
      <button
        type="button"
        className="microphone-button"
        disabled={buttonDisabled}
        aria-label={label}
        aria-pressed={listening}
        onClick={() => {
          setError(undefined);
          if (listening) controllerRef.current?.stop();
          else {
            onVoiceInputStart();
            controllerRef.current?.start();
          }
        }}
      >
        <span className={listening ? "microphone-indicator microphone-indicator-active" : "microphone-indicator"} aria-hidden="true">●</span>
        {listening ? "Listening…" : unavailable ? "Voice unavailable" : "Voice input"}
      </button>
      <span role="status" aria-live="polite">
        {error ?? (unavailable
          ? "Use Chrome or Edge for browser voice input, or type your message."
          : listening ? "Speak now. Press Stop when you are finished."
            : state === "processing" ? "Finishing transcript…"
              : "Review the transcript before sending.")}
      </span>
    </div>
  );
}
