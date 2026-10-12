export interface HealthResponse {
  status: string;
  database?: string;
}

export type MessageRole = "user" | "assistant";

export interface ConversationMessage {
  id: string;
  sequence: number;
  role: MessageRole;
  content: string;
  created_at?: string;
}

export interface SessionResponse {
  id: string;
  status: "active" | "deleted" | "expired" | string;
  created_at: string;
  last_used_at: string;
  message_count: number;
  messages: ConversationMessage[];
}

export interface PendingActionSummary {
  id: string;
  tool_name: string;
  description: string;
  expires_at: string;
}

export type PendingActionUiState =
  | "pending"
  | "confirming"
  | "confirmed"
  | "rejected"
  | "expired"
  | "failed"
  | "already_completed";

export interface ActionDecisionRequest {
  confirm: boolean;
}

export interface ActionDecisionResponse {
  status: "confirmed" | "rejected" | "failed" | "expired";
  result?: unknown;
  already_completed?: boolean;
}

export interface ChatRequest {
  message: string;
  session_id: string;
  agent: "handwritten" | "langgraph" | "multi_agent";
  mode: "assistant" | "knowledge";
  response_format: "text" | "calendar_event";
}

export interface ChatResponse {
  response: string;
  model: string;
  latency_ms: number;
  pending_actions: PendingActionSummary[];
  sources: Record<string, unknown>[];
  evidence_status: string;
  request_id?: string;
  session_id?: string;
  memory_refs: string[];
  agent: "handwritten" | "langgraph" | "multi_agent";
}
