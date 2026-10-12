export type VoiceRecognitionState = "unsupported" | "idle" | "listening" | "processing" | "error";

export type VoiceRecognitionError = "permission-denied" | "aborted" | "unavailable" | "unknown";

export interface VoiceRecognitionCallbacks {
  onInterimTranscript: (transcript: string) => void;
  onFinalTranscript: (transcript: string) => void;
  onStateChange: (state: VoiceRecognitionState) => void;
  onError: (error: VoiceRecognitionError) => void;
}

interface SpeechRecognitionResultLike {
  isFinal: boolean;
  [index: number]: { transcript: string };
}

interface SpeechRecognitionEventLike extends Event {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: SpeechRecognitionResultLike;
  };
}

interface SpeechRecognitionErrorEventLike extends Event {
  error: string;
}

interface SpeechRecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

interface SpeechRecognitionWindow extends Window {
  SpeechRecognition?: SpeechRecognitionConstructor;
  webkitSpeechRecognition?: SpeechRecognitionConstructor;
}

export function getSpeechRecognitionConstructor(): SpeechRecognitionConstructor | undefined {
  const browserWindow = window as SpeechRecognitionWindow;
  return browserWindow.SpeechRecognition ?? browserWindow.webkitSpeechRecognition;
}

export function isSpeechRecognitionSupported(): boolean {
  return Boolean(getSpeechRecognitionConstructor());
}

export class VoiceRecognitionController {
  private recognition?: SpeechRecognitionLike;
  private callbacks: VoiceRecognitionCallbacks;
  private active = false;
  private disposed = false;
  private failed = false;

  constructor(callbacks: VoiceRecognitionCallbacks) {
    this.callbacks = callbacks;
  }

  start(): boolean {
    if (this.disposed || this.active) return false;
    const Recognition = getSpeechRecognitionConstructor();
    if (!Recognition) {
      this.callbacks.onStateChange("unsupported");
      return false;
    }

    const recognition = new Recognition();
    this.recognition = recognition;
    this.active = true;
    this.failed = false;
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = navigator.language || "en-GB";
    recognition.onresult = (event) => {
      if (this.disposed) return;
      let interim = "";
      let finalTranscript = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const transcript = event.results[index][0]?.transcript ?? "";
        if (event.results[index].isFinal) finalTranscript += transcript;
        else interim += transcript;
      }
      this.callbacks.onInterimTranscript(interim.trim());
      if (finalTranscript.trim()) this.callbacks.onFinalTranscript(finalTranscript.trim());
    };
    recognition.onerror = (event) => {
      if (this.disposed) return;
      this.active = false;
      this.failed = true;
      this.callbacks.onError(event.error === "not-allowed" || event.error === "service-not-allowed"
        ? "permission-denied"
        : event.error === "aborted" ? "aborted" : "unknown");
    };
    recognition.onend = () => {
      if (this.disposed) return;
      this.active = false;
      this.callbacks.onInterimTranscript("");
      this.callbacks.onStateChange(this.failed ? "error" : "idle");
    };
    this.callbacks.onStateChange("listening");
    try {
      recognition.start();
      return true;
    } catch {
      this.active = false;
      this.callbacks.onError("unavailable");
      return false;
    }
  }

  stop(): void {
    if (!this.active || !this.recognition) return;
    this.callbacks.onStateChange("processing");
    this.recognition.stop();
  }

  dispose(): void {
    this.disposed = true;
    this.active = false;
    if (this.recognition) {
      this.recognition.onresult = null;
      this.recognition.onerror = null;
      this.recognition.onend = null;
      this.recognition.abort();
    }
    this.recognition = undefined;
  }
}
