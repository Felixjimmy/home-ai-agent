export type VoiceOutputState =
  | "unsupported"
  | "idle"
  | "speaking"
  | "paused"
  | "error";

export type VoiceOutputError = "unavailable" | "synthesis-failed";

export interface VoiceSynthesisCallbacks {
  onStateChange: (state: VoiceOutputState) => void;
  onError: (error: VoiceOutputError) => void;
}

export function isSpeechSynthesisSupported(): boolean {
  return typeof window !== "undefined"
    && "speechSynthesis" in window
    && typeof window.SpeechSynthesisUtterance === "function";
}

export class VoiceSynthesisController {
  private readonly callbacks: VoiceSynthesisCallbacks;
  private currentUtterance?: SpeechSynthesisUtterance;
  private generation = 0;
  private disposed = false;

  constructor(callbacks: VoiceSynthesisCallbacks) {
    this.callbacks = callbacks;
  }

  speak(text: string): boolean {
    const content = text.trim();
    if (!content || this.disposed) return false;

    if (!isSpeechSynthesisSupported()) {
      this.callbacks.onStateChange("unsupported");
      this.callbacks.onError("unavailable");
      return false;
    }

    const synthesis = window.speechSynthesis;
    const generation = ++this.generation;
    this.detachCurrentUtterance();
    synthesis.cancel();

    const utterance = new window.SpeechSynthesisUtterance(content);
    this.currentUtterance = utterance;
    utterance.lang = navigator.language || "en-GB";

    const isCurrent = () => !this.disposed
      && generation === this.generation
      && utterance === this.currentUtterance;

    utterance.onstart = () => {
      if (isCurrent()) this.callbacks.onStateChange("speaking");
    };
    utterance.onpause = () => {
      if (isCurrent()) this.callbacks.onStateChange("paused");
    };
    utterance.onresume = () => {
      if (isCurrent()) this.callbacks.onStateChange("speaking");
    };
    utterance.onend = () => {
      if (!isCurrent()) return;
      this.detachCurrentUtterance();
      this.callbacks.onStateChange("idle");
    };
    utterance.onerror = () => {
      if (!isCurrent()) return;
      this.detachCurrentUtterance();
      this.callbacks.onStateChange("error");
      this.callbacks.onError("synthesis-failed");
    };

    try {
      synthesis.speak(utterance);
      this.callbacks.onStateChange("speaking");
      return true;
    } catch {
      if (isCurrent()) this.detachCurrentUtterance();
      this.callbacks.onStateChange("error");
      this.callbacks.onError("synthesis-failed");
      return false;
    }
  }

  pause(): void {
    if (this.disposed || !this.currentUtterance || !isSpeechSynthesisSupported()) return;
    window.speechSynthesis.pause();
    this.callbacks.onStateChange("paused");
  }

  resume(): void {
    if (this.disposed || !this.currentUtterance || !isSpeechSynthesisSupported()) return;
    window.speechSynthesis.resume();
    this.callbacks.onStateChange("speaking");
  }

  stop(): void {
    if (this.disposed) return;
    this.cancelCurrent();
    this.callbacks.onStateChange(isSpeechSynthesisSupported() ? "idle" : "unsupported");
  }

  dispose(): void {
    if (this.disposed) return;
    this.cancelCurrent();
    this.disposed = true;
  }

  private cancelCurrent(): void {
    this.generation += 1;
    this.detachCurrentUtterance();
    if (isSpeechSynthesisSupported()) window.speechSynthesis.cancel();
  }

  private detachCurrentUtterance(): void {
    if (!this.currentUtterance) return;
    this.currentUtterance.onstart = null;
    this.currentUtterance.onpause = null;
    this.currentUtterance.onresume = null;
    this.currentUtterance.onend = null;
    this.currentUtterance.onerror = null;
    this.currentUtterance = undefined;
  }
}
