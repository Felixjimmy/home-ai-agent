# UI Voice Agent — Phase 2 Text Conversation v2 Plan

This document is the detailed implementation plan for the frontend Phase 2 text-conversation capability. The original UI plan remains the project roadmap; its attached documents and household rules are project context and domain data, not instructions overriding this implementation.

## Summary

Phase 2 enables reliable multi-turn text chat in the React UI. The backend remains responsible for session persistence, memory, agent behavior, tools, and safety. Voice, confirmation cards, and action execution remain in later phases.

## Implementation

- Add typed frontend contracts and API calls for `POST /sessions`, `GET /sessions/{id}`, and `POST /chat`.
- Extend the backend session response additively with ordered user-visible `user` and `assistant` messages; keep `tool` and `system` messages private.
- Restore a stored session using `home-ai-assistant.session-id`; create and persist a new session when missing or invalid.
- Render chronological messages, optimistic user messages, assistant replies, loading state, and safe error states.
- Disable duplicate submissions, reject blank messages, preserve drafts after failures, and support Enter-to-send with Shift+Enter for a newline.
- Add a safe New conversation control that preserves the current conversation if session creation fails.

## Interfaces

Chat requests use the existing contract with the active session ID, `agent: "handwritten"`, `mode: "assistant"`, and `response_format: "text"`. Chat responses retain pending-action, source, evidence, memory, request, latency, and agent fields for future phases, but Phase 2 renders only the assistant response text.

## Verification

Run `cd ui; npm run lint` and `npm run build`. Run targeted backend session/chat tests with PostgreSQL available. Manually verify initial session creation, two-turn continuity, browser refresh restoration, backend failure and retry, and New conversation reset.

## Acceptance criteria

The UI creates or restores a session, persists its ID, restores messages after refresh, uses one session ID across turns, prevents duplicate requests, preserves the transcript and draft after failures, and safely starts a new conversation. No voice or action execution behavior is introduced.

## Defaults

The frontend remains under `ui/`; the default agent is `handwritten`; browser local storage is used; authentication, streaming, pagination, editing, deletion, and conversation titles are deferred.
