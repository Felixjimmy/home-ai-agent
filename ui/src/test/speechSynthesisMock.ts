import { vi } from "vitest";

export class MockSpeechSynthesisUtterance {
  readonly text: string;
  lang = "";
  onstart: ((event: SpeechSynthesisEvent) => void) | null = null;
  onpause: ((event: SpeechSynthesisEvent) => void) | null = null;
  onresume: ((event: SpeechSynthesisEvent) => void) | null = null;
  onend: ((event: SpeechSynthesisEvent) => void) | null = null;
  onerror: ((event: SpeechSynthesisErrorEvent) => void) | null = null;

  constructor(text: string) {
    this.text = text;
  }
}

export function installSpeechSynthesisMock() {
  const utterances: MockSpeechSynthesisUtterance[] = [];
  const synthesis = {
    cancel: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(),
    speak: vi.fn((utterance: MockSpeechSynthesisUtterance) => {
      utterances.push(utterance);
    }),
  };

  Object.defineProperty(window, "SpeechSynthesisUtterance", {
    configurable: true,
    value: MockSpeechSynthesisUtterance,
  });
  Object.defineProperty(window, "speechSynthesis", {
    configurable: true,
    value: synthesis,
  });

  return { synthesis, utterances };
}

export function removeSpeechSynthesisMock() {
  Reflect.deleteProperty(window, "SpeechSynthesisUtterance");
  Reflect.deleteProperty(window, "speechSynthesis");
}
