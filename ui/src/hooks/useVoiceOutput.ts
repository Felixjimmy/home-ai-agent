import { useCallback, useEffect, useRef, useState } from "react";
import {
  isSpeechSynthesisSupported,
  VoiceSynthesisController,
  type VoiceOutputError,
  type VoiceOutputState,
} from "../voiceSynthesis";

const VOICE_OUTPUT_STORAGE_KEY = "home-ai-assistant.voice-output-enabled";

function readInitialPreference(): boolean {
  try {
    return localStorage.getItem(VOICE_OUTPUT_STORAGE_KEY) !== "false";
  } catch {
    return true;
  }
}

function errorMessage(error: VoiceOutputError): string {
  if (error === "unavailable") {
    return "Spoken replies are not available in this browser. Text chat still works.";
  }
  return "The reply could not be spoken. You can still read it in the conversation.";
}

export function useVoiceOutput() {
  const supported = isSpeechSynthesisSupported();
  const [enabled, setEnabledState] = useState(readInitialPreference);
  const [state, setState] = useState<VoiceOutputState>(() => supported ? "idle" : "unsupported");
  const [error, setError] = useState<string>();
  const controllerRef = useRef<VoiceSynthesisController | null>(null);

  useEffect(() => {
    const controller = new VoiceSynthesisController({
      onStateChange: (nextState) => {
        setState(nextState);
        if (nextState !== "error") setError(undefined);
      },
      onError: (nextError) => setError(errorMessage(nextError)),
    });
    controllerRef.current = controller;
    return () => {
      controller.dispose();
      controllerRef.current = null;
    };
  }, []);

  const stop = useCallback(() => controllerRef.current?.stop(), []);

  const setEnabled = useCallback((nextEnabled: boolean) => {
    setEnabledState(nextEnabled);
    try {
      localStorage.setItem(VOICE_OUTPUT_STORAGE_KEY, String(nextEnabled));
    } catch {
      // The preference still applies for this page when storage is unavailable.
    }
    if (!nextEnabled) controllerRef.current?.stop();
  }, []);

  const speak = useCallback((text: string) => {
    if (!enabled) return false;
    setError(undefined);
    return controllerRef.current?.speak(text) ?? false;
  }, [enabled]);

  const pause = useCallback(() => controllerRef.current?.pause(), []);
  const resume = useCallback(() => controllerRef.current?.resume(), []);

  return {
    enabled,
    supported,
    state,
    error,
    setEnabled,
    speak,
    pause,
    resume,
    stop,
  };
}
