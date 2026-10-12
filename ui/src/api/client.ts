import { API_BASE_URL } from "../config/environment";
import type {
  ChatRequest,
  ChatResponse,
  ActionDecisionResponse,
  HealthResponse,
  SessionResponse,
} from "./types";

export class ApiClientError extends Error {
  status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    throw new ApiClientError(
      "The assistant backend could not be reached. Check that it is running.",
    );
  }

  if (!response.ok) {
    let message = `The backend returned HTTP ${response.status}.`;

    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      // Preserve the generic HTTP message for non-JSON responses.
    }

    throw new ApiClientError(message, response.status);
  }

  const body: unknown = await response.json();
  if (body === null || typeof body !== "object") {
    throw new ApiClientError("The backend returned an invalid response.", response.status);
  }
  return body as T;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export function createSession(): Promise<SessionResponse> {
  return request<SessionResponse>("/sessions", { method: "POST" });
}

export function getSession(sessionId: string): Promise<SessionResponse> {
  return request<SessionResponse>(`/sessions/${encodeURIComponent(sessionId)}`);
}

export function sendChat(requestBody: ChatRequest): Promise<ChatResponse> {
  return request<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify(requestBody),
  });
}

export function decideAction(actionId: string, confirm: boolean): Promise<ActionDecisionResponse> {
  return request<ActionDecisionResponse>(`/actions/${encodeURIComponent(actionId)}/decision`, {
    method: "POST",
    body: JSON.stringify({ confirm }),
  });
}
