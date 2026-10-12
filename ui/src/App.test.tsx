import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { createSession, getHealth, getSession, sendChat } from "./api/client";
import type { ChatResponse, SessionResponse } from "./api/types";
import { installSpeechSynthesisMock, removeSpeechSynthesisMock } from "./test/speechSynthesisMock";

vi.mock("./api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api/client")>();
  return {
    ...actual,
    createSession: vi.fn(),
    decideAction: vi.fn(),
    getHealth: vi.fn(),
    getSession: vi.fn(),
    sendChat: vi.fn(),
  };
});

const SESSION_ID = "00000000-0000-0000-0000-000000000001";

function session(messages: SessionResponse["messages"] = []): SessionResponse {
  return {
    id: SESSION_ID,
    status: "active",
    created_at: "2026-10-07T20:00:00Z",
    last_used_at: "2026-10-07T20:00:00Z",
    message_count: messages.length,
    messages,
  };
}

function chatResponse(response: string): ChatResponse {
  return {
    response,
    model: "test-model",
    latency_ms: 1,
    pending_actions: [],
    sources: [],
    evidence_status: "not_required",
    request_id: "request-1",
    session_id: SESSION_ID,
    memory_refs: [],
    agent: "handwritten",
  };
}

beforeEach(() => {
  vi.mocked(getHealth).mockResolvedValue({ status: "ok" });
  vi.mocked(createSession).mockResolvedValue(session());
  vi.mocked(getSession).mockResolvedValue(session());
  vi.mocked(sendChat).mockReset();
});

describe("App voice output integration", () => {
  it("speaks a successful live assistant reply exactly once", async () => {
    const { synthesis, utterances } = installSpeechSynthesisMock();
    vi.mocked(sendChat).mockResolvedValue(chatResponse("The kitchen light is off."));
    const user = userEvent.setup();
    render(<App />);

    const composer = await screen.findByRole("textbox", { name: "Message" });
    await waitFor(() => expect(composer).toBeEnabled());
    await user.type(composer, "Is the kitchen light on?");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(await screen.findByText("The kitchen light is off.")).toBeVisible();
    await waitFor(() => expect(synthesis.speak).toHaveBeenCalledOnce());
    expect(utterances[0].text).toBe("The kitchen light is off.");
    removeSpeechSynthesisMock();
  });

  it("does not speak a failed chat request", async () => {
    const { synthesis } = installSpeechSynthesisMock();
    vi.mocked(sendChat).mockRejectedValue(new Error("offline"));
    const user = userEvent.setup();
    render(<App />);

    const composer = await screen.findByRole("textbox", { name: "Message" });
    await waitFor(() => expect(composer).toBeEnabled());
    await user.type(composer, "Hello");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong");
    expect(synthesis.speak).not.toHaveBeenCalled();
    removeSpeechSynthesisMock();
  });

  it("restores assistant history without speaking it", async () => {
    localStorage.setItem("home-ai-assistant.session-id", SESSION_ID);
    const { synthesis } = installSpeechSynthesisMock();
    vi.mocked(getSession).mockResolvedValue(session([{
      id: "message-1",
      sequence: 1,
      role: "assistant",
      content: "Previously saved reply",
    }]));
    render(<App />);

    expect(await screen.findByText("Previously saved reply")).toBeVisible();
    expect(synthesis.speak).not.toHaveBeenCalled();
    removeSpeechSynthesisMock();
  });

  it("honours a persisted disabled preference", async () => {
    localStorage.setItem("home-ai-assistant.voice-output-enabled", "false");
    const { synthesis } = installSpeechSynthesisMock();
    vi.mocked(sendChat).mockResolvedValue(chatResponse("A quiet reply"));
    const user = userEvent.setup();
    render(<App />);

    const composer = await screen.findByRole("textbox", { name: "Message" });
    await waitFor(() => expect(composer).toBeEnabled());
    await user.type(composer, "Reply quietly");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(await screen.findByText("A quiet reply")).toBeVisible();
    expect(synthesis.speak).not.toHaveBeenCalled();
    expect(screen.getByRole("checkbox", { name: "Spoken replies" })).not.toBeChecked();
    removeSpeechSynthesisMock();
  });
});
