import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { VoiceOutputControl } from "./VoiceOutputControl";

function renderControl(overrides: Partial<React.ComponentProps<typeof VoiceOutputControl>> = {}) {
  const props: React.ComponentProps<typeof VoiceOutputControl> = {
    enabled: true,
    supported: true,
    state: "idle",
    onEnabledChange: vi.fn(),
    onPause: vi.fn(),
    onResume: vi.fn(),
    onStop: vi.fn(),
    ...overrides,
  };
  render(<VoiceOutputControl {...props} />);
  return props;
}

describe("VoiceOutputControl", () => {
  it("toggles spoken replies with an accessible checkbox", async () => {
    const user = userEvent.setup();
    const props = renderControl();
    await user.click(screen.getByRole("checkbox", { name: "Spoken replies" }));
    expect(props.onEnabledChange).toHaveBeenCalledWith(false);
  });

  it("offers pause and stop while speaking", async () => {
    const user = userEvent.setup();
    const props = renderControl({ state: "speaking" });
    await user.click(screen.getByRole("button", { name: "Pause spoken reply" }));
    await user.click(screen.getByRole("button", { name: "Stop spoken reply" }));
    expect(props.onPause).toHaveBeenCalledOnce();
    expect(props.onStop).toHaveBeenCalledOnce();
    expect(screen.getByRole("status")).toHaveTextContent("Speaking the latest assistant reply.");
  });

  it("offers resume while paused", async () => {
    const user = userEvent.setup();
    const props = renderControl({ state: "paused" });
    await user.click(screen.getByRole("button", { name: "Resume spoken reply" }));
    expect(props.onResume).toHaveBeenCalledOnce();
  });

  it("keeps the preference visible while disabling playback in unsupported browsers", () => {
    renderControl({ supported: false, state: "unsupported" });
    expect(screen.getByRole("checkbox", { name: "Spoken replies" })).toBeChecked();
    expect(screen.getByRole("button", { name: "Pause spoken reply" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("Speech synthesis is unavailable");
  });
});
