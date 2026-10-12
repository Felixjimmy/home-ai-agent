import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { installSpeechSynthesisMock, removeSpeechSynthesisMock } from "../test/speechSynthesisMock";
import { useVoiceOutput } from "./useVoiceOutput";

afterEach(removeSpeechSynthesisMock);

describe("useVoiceOutput", () => {
  it("defaults to enabled and speaks new text", () => {
    const { synthesis } = installSpeechSynthesisMock();
    const { result } = renderHook(() => useVoiceOutput());
    expect(result.current.enabled).toBe(true);

    act(() => { result.current.speak("A new reply"); });
    expect(synthesis.speak).toHaveBeenCalledOnce();
    expect(result.current.state).toBe("speaking");
  });

  it("restores the disabled preference and does not speak", () => {
    localStorage.setItem("home-ai-assistant.voice-output-enabled", "false");
    const { synthesis } = installSpeechSynthesisMock();
    const { result } = renderHook(() => useVoiceOutput());
    expect(result.current.enabled).toBe(false);

    act(() => { result.current.speak("Do not speak"); });
    expect(synthesis.speak).not.toHaveBeenCalled();
  });

  it("persists disabling and stops current speech", () => {
    const { synthesis } = installSpeechSynthesisMock();
    const { result } = renderHook(() => useVoiceOutput());
    act(() => { result.current.speak("Speaking"); });

    act(() => { result.current.setEnabled(false); });
    expect(localStorage.getItem("home-ai-assistant.voice-output-enabled")).toBe("false");
    expect(synthesis.cancel).toHaveBeenCalledTimes(2);
    expect(result.current.enabled).toBe(false);
    expect(result.current.state).toBe("idle");
  });
});
