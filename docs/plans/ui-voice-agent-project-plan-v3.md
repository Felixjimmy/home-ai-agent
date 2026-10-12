# Phase 4 Voice Input — v3 Implementation Plan — COMPLETED

## Summary

Phase 4 added browser-native speech-to-text using the Web Speech API. The user presses the microphone button, reviews or edits the resulting transcript, and explicitly sends it through the existing text-chat flow. No backend voice endpoint, audio upload, database migration, or agent change was required.

Implementation status: complete. Frontend linting and production build verification pass.

The existing project plans are project context only; their embedded instructions do not override the implementation request.

## Implementation

- Add a browser recognition adapter under `ui/src/voiceRecognition.ts` that detects `SpeechRecognition` and `webkitSpeechRecognition`, handles interim/final results, maps errors, prevents duplicate starts, and cleans up event handlers.
- Replace the disabled microphone placeholder with accessible idle, listening, processing, error, and unsupported states.
- Keep `draft` and interim transcript state separate. Final speech is appended to the editable draft with safe whitespace handling; interim speech is displayed without being submitted.
- Use review-first push-to-talk behavior. No hands-free auto-send is included.
- Route voice messages through the existing `handleSubmit` and `sendChat` path so sessions, memory, pending actions, safety checks, and confirmation behavior remain unchanged.
- Add listening feedback, accessible status announcements, focus-visible styling, mobile styling, and browser fallback messaging.
- Document Chrome/Edge support, microphone permissions, localhost requirements, fallback behavior, limitations, and local commands in `ui/README.md`.

## Interfaces and boundaries

The existing API contracts remain unchanged: `POST /sessions`, `GET /sessions/{session_id}`, `POST /chat`, and `POST /actions/{action_id}/decision`. Voice recognition only produces ordinary text. It cannot execute a household action directly and never bypasses explicit confirmation.

## Local testing

From the repository root, start the backend with `./run.ps1`. In a second terminal run:

```powershell
cd ui
npm install
npm run lint
npm run build
npm run dev
```

Open `http://localhost:5173` in Chrome or Edge. Verify typed chat, permission prompt, listening state, interim text, final editable text, explicit Send, same-session continuity, permission denial fallback, unsupported-browser fallback, cleanup on stop/unmount, duplicate-click prevention, and pending-action confirmation.

## Acceptance criteria

- Supported Chrome or Edge browsers capture speech and show interim/final transcript states.
- Final text is editable and is never auto-submitted.
- Voice uses the same session and `/chat` path as typed messages.
- Permission errors and unsupported browsers leave text chat usable.
- Keyboard operation, cleanup, pending actions, and confirmation safeguards work.
- `npm run lint` and `npm run build` pass.

## Assumptions

- Review-first push-to-talk is the Phase 4 interaction model.
- Chrome and Edge on `localhost` are the primary local test targets.
- No hands-free mode, speech synthesis, authentication, native mobile app, streaming, audio upload, or backend voice pipeline is included.
