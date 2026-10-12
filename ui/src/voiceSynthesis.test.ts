import { afterEach, describe, expect, it } from "vitest";
import {
  isSpeechSynthesisSupported,
  VoiceSynthesisController,
  type VoiceOutputError,
  type VoiceOutputState,
} from "./voiceSynthesis";
import {
  installSpeechSynthesisMock,
  removeSpeechSynthesisMock,
} from "./test/speechSynthesisMock";

afterEach(removeSpeechSynthesisMock);

function createController() {
  const states: VoiceOutputState[] = [];
  const errors: VoiceOutputError[] = [];
  const controller = new VoiceSynthesisController({
    onStateChange: (state) => states.push(state),
    onError: (error) => errors.push(error),
  });
  return { controller, states, errors };
}

describe("VoiceSynthesisController", () => {
  it("detects supported and unsupported browsers", () => {
    expect(isSpeechSynthesisSupported()).toBe(false);
    installSpeechSynthesisMock();
    expect(isSpeechSynthesisSupported()).toBe(true);
  });

  it("rejects blank text without using the browser API", () => {
    const { synthesis } = installSpeechSynthesisMock();
    const { controller } = createController();
    expect(controller.speak("   ")).toBe(false);
    expect(synthesis.speak).not.toHaveBeenCalled();
  });

  it("cancels queued speech, trims text, and follows playback events", () => {
    const { synthesis, utterances } = installSpeechSynthesisMock();
    const { controller, states } = createController();

    expect(controller.speak("  Hello home  ")).toBe(true);
    expect(synthesis.cancel).toHaveBeenCalledTimes(1);
    expect(utterances[0].text).toBe("Hello home");
    expect(states.at(-1)).toBe("speaking");

    controller.pause();
    expect(synthesis.pause).toHaveBeenCalledTimes(1);
    expect(states.at(-1)).toBe("paused");

    controller.resume();
    expect(synthesis.resume).toHaveBeenCalledTimes(1);
    expect(states.at(-1)).toBe("speaking");

    utterances[0].onend?.(new Event("end") as SpeechSynthesisEvent);
    expect(states.at(-1)).toBe("idle");
  });

  it("replaces active speech and ignores a stale completion event", () => {
    const { synthesis, utterances } = installSpeechSynthesisMock();
    const { controller, states } = createController();

    controller.speak("First");
    const staleEnd = utterances[0].onend;
    controller.speak("Second");
    staleEnd?.(new Event("end") as SpeechSynthesisEvent);

    expect(synthesis.cancel).toHaveBeenCalledTimes(2);
    expect(utterances.map((utterance) => utterance.text)).toEqual(["First", "Second"]);
    expect(states.at(-1)).toBe("speaking");
  });

  it("reports synthesis failures without throwing", () => {
    const { utterances } = installSpeechSynthesisMock();
    const { controller, states, errors } = createController();
    controller.speak("Hello");

    utterances[0].onerror?.(new Event("error") as SpeechSynthesisErrorEvent);
    expect(states.at(-1)).toBe("error");
    expect(errors).toEqual(["synthesis-failed"]);
  });

  it("stops and disposes safely", () => {
    const { synthesis, utterances } = installSpeechSynthesisMock();
    const { controller, states } = createController();
    controller.speak("Hello");
    const staleEnd = utterances[0].onend;

    controller.stop();
    staleEnd?.(new Event("end") as SpeechSynthesisEvent);
    expect(states.at(-1)).toBe("idle");

    controller.dispose();
    expect(controller.speak("Ignored")).toBe(false);
    expect(synthesis.speak).toHaveBeenCalledTimes(1);
  });

  it("reports an unavailable browser", () => {
    const { controller, states, errors } = createController();
    expect(controller.speak("Hello")).toBe(false);
    expect(states.at(-1)).toBe("unsupported");
    expect(errors).toEqual(["unavailable"]);
  });

  it("converts a throwing browser API into a visible voice error", () => {
    const { synthesis } = installSpeechSynthesisMock();
    synthesis.speak.mockImplementation(() => { throw new Error("blocked"); });
    const { controller, states, errors } = createController();

    expect(() => controller.speak("Hello")).not.toThrow();
    expect(states.at(-1)).toBe("error");
    expect(errors).toEqual(["synthesis-failed"]);
  });
});
