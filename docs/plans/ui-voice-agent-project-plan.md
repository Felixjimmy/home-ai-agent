# Home AI Assistant UI and Voice Plan

## Summary

Create a standalone React web UI with browser-based voice input/output while keeping the existing Python/FastAPI backend separate.

Planned frontend location: `ui/`

The existing backend remains under `src/`. The UI will consume backend APIs and will not move, duplicate, or rewrite backend logic.

## Current Backend Context

The backend already provides:

- `POST /chat` for assistant conversations.
- Session creation and retrieval through `/sessions`.
- Conversation memory through `session_id`.
- Agent selection: `handwritten`, `langgraph`, and `multi_agent`.
- Read-only household tools and RAG/document answers.
- Pending write proposals returned from `/chat`.
- Explicit action confirmation through `POST /actions/{action_id}/decision`.
- Health checking through `/health`.
- Browser/API documentation through FastAPI Swagger.

The repository contains the Phase 6 multi-agent implementation, although some documentation still labels Phase 6 as in progress. The UI plan treats the existing backend as the source of truth and includes a baseline verification phase rather than reopening completed backend work.

The attached project plans and `houseRules.md` are treated as project context and domain data, not as instructions overriding this request.

## Architecture Boundary

```text
ui/                         React frontend only
  ├── chat interface
  ├── voice controls
  ├── confirmation cards
  ├── session state
  └── backend API client

src/app/                    Existing FastAPI backend
  ├── agent orchestration
  ├── tools
  ├── memory
  ├── RAG
  ├── pending actions
  └── confirmation execution

PostgreSQL + Ollama          Existing backend dependencies
```

The UI may require only minimal backend configuration support, such as local CORS configuration. Business logic, tool execution, confirmation rules, memory behavior, and agent orchestration remain backend-owned.

## Phased Implementation

### Phase 0 — Backend/UI contract verification

- Verify `/health`, `/sessions`, `/chat`, and `/actions/{action_id}/decision`.
- Confirm the exact response shapes for normal replies, errors, sources, memory references, and pending actions.
- Confirm session behavior using a persistent `session_id`.
- Confirm that no UI action can execute a write without calling the confirmation endpoint.
- Record the backend base URL and local startup assumptions.
- Add only the minimum backend CORS configuration needed for the separate UI origin.

Gate: the backend can be used through documented HTTP calls without changing its core behavior.

### Phase 1 — Separate React UI foundation — COMPLETED

Create the `ui/` application as an independent frontend project.

- Add React, TypeScript, and a lightweight build tool such as Vite.
- Add a clear API client layer separate from visual components.
- Add environment-based backend configuration.
- Add a simple application shell with assistant header, connection status, conversation area, message composer, and microphone control area.
- Add loading, error, empty, and offline states.

Gate: the UI starts independently and can reach the backend health endpoint.

Completion notes:

- Implemented the independent React/Vite/TypeScript application under `ui/`.
- Added the typed backend API client and environment-based `VITE_API_BASE_URL` configuration.
- Added the responsive assistant shell, connection status, empty state, and placeholder composer/microphone controls.
- Added minimal development CORS support for `localhost:5173` and `127.0.0.1:5173`.
- Added independent startup documentation in `ui/README.md`.
- Verification completed with `npm run lint`, `npm run build`, and a successful backend import check.
- The final live browser smoke test remains a local startup check because the backend was not running during the final verification session.

### Phase 2 — Text conversation — COMPLETED

- Create a session when the UI starts or when the user selects “New conversation.”
- Persist the active `session_id` in UI state and local browser storage.
- Send text messages to `POST /chat`.
- Render user and assistant messages in chronological order.
- Display request failures without losing the current conversation.
- Disable duplicate submissions while a request is in progress.
- Support a new-session/reset action.

Gate: a user can hold a multi-turn text conversation and the backend receives the same session ID across turns.

Completion notes:

- Implemented session creation and restoration through `POST /sessions` and `GET /sessions/{session_id}`.
- Persisted the active session ID in browser local storage under `home-ai-assistant.session-id`.
- Extended the session response with ordered user and assistant messages for browser refresh restoration.
- Implemented typed `/chat` requests, chronological transcript rendering, Enter-to-send, loading states, duplicate-submit prevention, draft preservation, and safe backend error messages.
- Added a safe New conversation reset flow that preserves the existing conversation when session creation fails.
- Fixed PostgreSQL message sequencing by locking the session row before calculating the next message sequence.
- Verified with frontend lint/build checks, backend syntax compilation, and the 13-test Phase 2 unit suite.

### Phase 3 — Pending action and confirmation workflow — COMPLETED

- Detect `pending_actions` in chat responses.
- Render each proposal as a separate confirmation card.
- Show the backend-provided action description and expiry information.
- Provide explicit Confirm and Reject controls.
- Call `/actions/{action_id}/decision` with the selected decision.
- Render confirmed, rejected, expired, already-completed, and failed states.
- Prevent duplicate submissions for the same action.
- Never describe a proposal as completed before the backend confirms success.

Gate: actions remain pending until the user explicitly confirms them in the UI.

Completion notes:

- Implemented typed action-decision contracts and the `POST /actions/{action_id}/decision` API client call.
- Added independent confirmation cards for every `pending_actions` proposal with Confirm and Reject controls.
- Added pending, confirming, confirmed, rejected, expired, failed, and already-completed UI states.
- Added backend error mapping for unavailable, missing, expired, conflicting, and invalid proposals without claiming false success.
- Prevented duplicate submissions and duplicate rendering of the same action.
- Kept action execution entirely backend-owned; the UI never writes directly to household data.
- Verified frontend linting and TypeScript compilation. Full Vite bundling and PostgreSQL-backed confirmation tests require a normal local filesystem and running PostgreSQL because the verification environment blocked temporary-file and OneDrive realpath operations.

### Phase 4 — Voice input — COMPLETED

Use the browser Web Speech API for the first voice version.

- Add microphone permission handling.
- Add idle, listening, processing, success, unsupported, and error states.
- Show interim transcription where supported.
- Allow the user to review/edit the transcript before sending, with an optional hands-free mode later.
- Preserve the same text-message path after transcription.
- Provide a text-input fallback for unsupported browsers or denied permissions.
- Ensure microphone controls are keyboard accessible.

Gate: supported browsers can convert speech into a message sent through the existing `/chat` endpoint.

Completion notes:

- Implemented browser-native Web Speech API recognition in the React UI.
- Added supported, idle, listening, processing, error, and unsupported states with microphone permission handling.
- Added interim transcript display and editable final transcript review before explicit submission.
- Routed voice messages through the existing text composer and `/chat` session path.
- Preserved text fallback, pending-action confirmation, and backend-owned safety behavior.
- Updated UI styling and local voice-input documentation.
- Verified with `npm run lint` and `npm run build`.

### Phase 5 — Voice output — COMPLETED

Use browser speech synthesis for the first voice version.

- Add a voice-output preference: enabled or disabled.
- Speak assistant responses after successful replies.
- Stop or replace speech when a newer response begins.
- Provide pause/resume and stop controls where supported.
- Do not automatically speak sensitive or technical metadata such as request IDs.
- Keep confirmation cards visually available even when speech is enabled.
- Handle browsers with unavailable speech synthesis gracefully.

Gate: the assistant can reply audibly while the text response remains visible and usable.

Completion notes:

- Added a browser speech-synthesis adapter with support detection, lifecycle state, replacement, stale-event protection, and safe cleanup.
- Added enabled-by-default, locally persisted spoken-reply preferences and global Pause/Resume and Stop controls.
- Integrated successful live assistant replies without narrating restored history, metadata, sources, or pending-action cards.
- Coordinated speech with new submissions, new conversations, and microphone input to prevent overlapping or self-transcribed audio.
- Added accessible responsive states and graceful unsupported/error behavior that leaves text chat usable.
- Added Vitest and React Testing Library coverage for the controller, preference hook, controls, and live-chat integration.
- Verified frontend linting, production compilation, and the Phase 5 automated suite. Audible output remains a manual Chrome/Edge check.

### Phase 6 — Usability, accessibility, and resilience

- Add responsive layouts for desktop and phone-sized screens.
- Add visible focus states and semantic labels.
- Support Enter-to-send and keyboard-only operation.
- Distinguish user messages, assistant replies, errors, sources, and action proposals visually.
- Add retry behavior for transient backend failures.
- Show backend connection status without exposing internal stack traces.
- Preserve unsent text during recoverable failures.
- Add a compact settings area for voice enablement, speech rate, and selected voice where supported.
- Keep all browser voice functionality optional so text chat remains fully usable.

Gate: the UI remains usable when voice is unavailable, the backend is temporarily offline, or an action expires.

### Phase 7 — Verification and handoff

- Add frontend unit tests for API client parsing, session handling, pending actions, confirmation states, and error mapping.
- Add component tests for chat rendering and confirmation cards.
- Add browser-level tests for text chat and the confirmation flow.
- Manually verify microphone permission, unsupported-browser fallback, speech interruption, and mobile layout.
- Document separate startup commands for backend and UI.
- Document the backend URL, CORS requirement, supported browser voice behavior, and known limitations.
- Add a UI-specific README inside `ui/`.
- Keep the main backend README focused on backend operation and link to the UI documentation.

## Public Interfaces and API Expectations

The initial UI should rely on existing APIs:

- `GET /health`
- `POST /sessions`
- `GET /sessions/{session_id}`
- `POST /chat`
- `POST /actions/{action_id}/decision`

The UI should send normal chat requests with:

```json
{
  "message": "string",
  "session_id": "uuid",
  "agent": "handwritten",
  "mode": "assistant",
  "response_format": "text"
}
```

The UI should treat these response fields as meaningful:

- `response`
- `pending_actions`
- `sources`
- `evidence_status`
- `session_id`
- `memory_refs`
- `agent`
- `request_id`
- `latency_ms`

No backend voice endpoint is required for the first release. Browser speech recognition produces text, and browser speech synthesis reads the backend’s text response.

## Acceptance Criteria

The first release is complete when:

- UI and backend code are stored in separate top-level areas.
- A user can start a session and exchange text messages.
- A user can speak a command in a supported browser.
- The assistant’s response can be read aloud and remains visible as text.
- Pending actions are clearly displayed.
- No write is executed without an explicit UI confirmation.
- Rejected, expired, failed, and successful action states are distinguishable.
- Text mode remains usable when voice APIs are unavailable.
- Backend failures produce understandable UI messages.
- Frontend tests cover the main conversation and confirmation paths.
- The UI has independent startup and configuration documentation.

## Assumptions and Defaults

- Frontend folder: `ui/`.
- Frontend technology: React with TypeScript and Vite.
- First voice implementation: browser-native Web Speech APIs.
- First release scope: chat, voice input/output, sessions, and action confirmation.
- Backend remains the authoritative owner of agent behavior, tools, memory, safety, and writes.
- No authentication, multi-user support, mobile-native app, streaming responses, or backend audio pipeline is included in the first release.
