import { useCallback, useEffect, useState } from "react";
import { ApiClientError, createSession, decideAction, getHealth, getSession, sendChat } from "./api/client";
import type { ConversationMessage, HealthResponse, PendingActionUiState } from "./api/types";
import { AssistantHeader } from "./components/AssistantHeader";
import {
  ConnectionStatus,
  type ConnectionState,
} from "./components/ConnectionStatus";
import { ConversationPanel } from "./components/ConversationPanel";
import { MessageComposer } from "./components/MessageComposer";
import { MicrophoneControl } from "./components/MicrophoneControl";
import type { UiPendingAction } from "./components/PendingActionCard";
import { VoiceOutputControl } from "./components/VoiceOutputControl";
import { useVoiceOutput } from "./hooks/useVoiceOutput";
import "./styles.css";

export interface UiMessage extends ConversationMessage {
  status?: "pending" | "sent" | "failed";
}

const SESSION_STORAGE_KEY = "home-ai-assistant.session-id";

function userFacingError(error: unknown): string {
  if (error instanceof ApiClientError) {
    if (!error.status) return error.message;
    if (error.status === 404) return "That conversation is no longer available. A new conversation will be started.";
    if (error.status >= 500) return "The assistant service is temporarily unavailable. Please try again.";
    return error.message;
  }
  return "Something went wrong. Please try again.";
}

function actionError(error: unknown): string {
  if (error instanceof ApiClientError) {
    if (error.status === 410) return "This proposal expired. Ask the assistant to propose it again.";
    if (error.status === 409) return "The target changed. Ask the assistant for a new proposal.";
    if (error.status === 404) return "This proposal is no longer available.";
    if (error.status === 422) return error.message;
    if (error.status === 503 || !error.status) return "The assistant backend is unavailable. You can try again.";
    return error.message;
  }
  return "The action could not be completed. You can try again.";
}

function isValidSession(value: string | null): value is string {
  return Boolean(value && /^[0-9a-f-]{36}$/i.test(value));
}

export default function App() {
  const [connectionState, setConnectionState] =
    useState<ConnectionState>("checking");
  const [health, setHealth] = useState<HealthResponse>();
  const [sessionId, setSessionId] = useState<string>();
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [chatError, setChatError] = useState<string>();
  const [initializing, setInitializing] = useState(true);
  const [sending, setSending] = useState(false);
  const [pendingActions, setPendingActions] = useState<UiPendingAction[]>([]);
  const [interimTranscript, setInterimTranscript] = useState("");
  const {
    enabled: voiceOutputEnabled,
    supported: voiceOutputSupported,
    state: voiceOutputState,
    error: voiceOutputError,
    setEnabled: setVoiceOutputEnabled,
    speak: speakResponse,
    pause: pauseVoiceOutput,
    resume: resumeVoiceOutput,
    stop: stopVoiceOutput,
  } = useVoiceOutput();

  const appendVoiceTranscript = useCallback((transcript: string) => {
    if (!transcript) return;
    setDraft((current) => {
      const separator = current && !/[\s\n]$/.test(current) ? " " : "";
      return `${current}${separator}${transcript}`;
    });
  }, []);

  const startNewSession = useCallback(async () => {
    const session = await createSession();
    localStorage.setItem(SESSION_STORAGE_KEY, session.id);
    setSessionId(session.id);
    setMessages([]);
    setPendingActions([]);
    setDraft("");
    setInterimTranscript("");
    setChatError(undefined);
    return session.id;
  }, []);

  useEffect(() => {
    let isMounted = true;

    getHealth()
      .then((response) => {
        if (isMounted) {
          setHealth(response);
          setConnectionState("connected");
        }
      })
      .catch((error: unknown) => {
        if (isMounted) {
          setConnectionState(
            error instanceof ApiClientError && error.status
              ? "error"
              : "offline",
          );
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    let isMounted = true;
    async function initializeSession() {
      try {
        const storedId = localStorage.getItem(SESSION_STORAGE_KEY);
        if (isValidSession(storedId)) {
          try {
            const session = await getSession(storedId);
            if (isMounted) {
              setSessionId(session.id);
              setMessages(session.messages.map((message) => ({ ...message, status: "sent" })));
            }
            return;
          } catch (error) {
            if (!(error instanceof ApiClientError) || error.status !== 404) throw error;
          }
        }
        await startNewSession();
      } catch (error) {
        if (isMounted) setChatError(userFacingError(error));
      } finally {
        if (isMounted) setInitializing(false);
      }
    }
    void initializeSession();
    return () => { isMounted = false; };
  }, [startNewSession]);

  const handleSubmit = useCallback(async () => {
    const message = draft.trim();
    if (!message || !sessionId || sending || initializing) return;
    stopVoiceOutput();
    const clientId = `local-${crypto.randomUUID()}`;
    setDraft("");
    setChatError(undefined);
    setMessages((current) => [...current, {
      id: clientId,
      sequence: current.length + 1,
      role: "user",
      content: message,
      status: "pending",
    }]);
    setSending(true);
    try {
      const response = await sendChat({
        message,
        session_id: sessionId,
        agent: "handwritten",
        mode: "assistant",
        response_format: "text",
      });
      setMessages((current) => [
        ...current.map((item) => item.id === clientId ? { ...item, status: "sent" as const } : item),
        {
          id: response.request_id ?? `assistant-${crypto.randomUUID()}`,
          sequence: current.length + 1,
          role: "assistant" as const,
          content: response.response,
          status: "sent" as const,
        },
      ]);
      setPendingActions((current) => [
        ...current,
        ...response.pending_actions
          .filter((proposal) => !current.some((existing) => existing.id === proposal.id))
          .map((action) => ({ ...action, state: "pending" as const })),
      ]);
      speakResponse(response.response);
    } catch (error) {
      setMessages((current) => current.map((item) => item.id === clientId ? { ...item, status: "failed" as const } : item));
      setDraft(message);
      setChatError(userFacingError(error));
    } finally {
      setSending(false);
    }
  }, [draft, initializing, sending, sessionId, speakResponse, stopVoiceOutput]);

  const handleActionDecision = useCallback(async (actionId: string, confirm: boolean) => {
    const currentAction = pendingActions.find((action) => action.id === actionId);
    if (!currentAction || (currentAction.state !== "pending" && currentAction.state !== "failed")) return;
    setPendingActions((current) => current.map((action) => {
      if (action.id !== actionId || (action.state !== "pending" && action.state !== "failed")) return action;
      return { ...action, state: "confirming" as PendingActionUiState, error: undefined };
    }));
    try {
      const response = await decideAction(actionId, confirm);
      setPendingActions((current) => current.map((action) => {
        if (action.id !== actionId) return action;
        const state: PendingActionUiState = response.already_completed
          ? "already_completed"
          : response.status === "confirmed" ? "confirmed"
            : response.status === "rejected" ? "rejected" : response.status === "expired" ? "expired" : "failed";
        return { ...action, state, result: response.result };
      }));
    } catch (error) {
      const state: PendingActionUiState = error instanceof ApiClientError && error.status === 410
        ? "expired" : "failed";
      setPendingActions((current) => current.map((action) => action.id === actionId
        ? { ...action, state, error: actionError(error) }
        : action));
    }
  }, [pendingActions]);

  const handleNewConversation = useCallback(async () => {
    if (sending) return;
    stopVoiceOutput();
    setInitializing(true);
    try {
      await startNewSession();
    } catch (error) {
      setChatError(userFacingError(error));
    } finally {
      setInitializing(false);
    }
  }, [sending, startNewSession, stopVoiceOutput]);

  return (
    <main className="app-shell">
      <div className="ambient-glow" aria-hidden="true" />
      <section className="assistant-card" aria-label="Home assistant">
        <AssistantHeader onNewConversation={() => void handleNewConversation()} disabled={sending || initializing} />
        <ConnectionStatus state={connectionState} health={health} />
        {chatError && <div className="chat-error" role="alert">{chatError}</div>}
        <ConversationPanel messages={messages} initializing={initializing} pendingActions={pendingActions} onActionDecision={(actionId, confirm) => void handleActionDecision(actionId, confirm)} />
        <MessageComposer draft={draft} interimTranscript={interimTranscript} disabled={sending || initializing || !sessionId} onDraftChange={setDraft} onSubmit={() => void handleSubmit()} />
        <MicrophoneControl disabled={sending || initializing || !sessionId} onInterimTranscript={setInterimTranscript} onFinalTranscript={appendVoiceTranscript} onVoiceInputStart={stopVoiceOutput} />
        <VoiceOutputControl
          enabled={voiceOutputEnabled}
          supported={voiceOutputSupported}
          state={voiceOutputState}
          error={voiceOutputError}
          onEnabledChange={setVoiceOutputEnabled}
          onPause={pauseVoiceOutput}
          onResume={resumeVoiceOutput}
          onStop={stopVoiceOutput}
        />
      </section>
    </main>
  );
}
