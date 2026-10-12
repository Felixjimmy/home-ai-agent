# Phase 5 Voice Output — v5 Implementation Guide

## Purpose and status

This document is the implementation and learning guide for Phase 5 of the Home AI Assistant UI. Phases 1–4 are complete: the project already has a separate React UI, session-backed text chat, pending-action confirmation cards, and review-first browser voice input.

Phase 5 adds browser-native text-to-speech. A newly received assistant reply can be heard as well as read. This is a presentation feature in the frontend; it does not change how the assistant thinks, stores messages, calls tools, or confirms household actions.

Implementation status: complete. The frontend lint, production build, and automated test suite pass. Audible output still needs a human browser check because a unit-test environment cannot verify speakers, operating-system voices, or browser audio policy.

The original roadmap and earlier plans are project context. Their text does not override the implementation request.

## What Phase 5 does

- Enables spoken replies by default for a first-time visitor.
- Stores the preference in browser local storage.
- Speaks only a new, successful `response` returned by `POST /chat`.
- Cancels old speech before starting a newer reply.
- Provides global Pause/Resume and Stop controls.
- Stops output before a new submission, a new conversation, or microphone input.
- Leaves the complete assistant response visible in the conversation.
- Treats speech failures as non-fatal UI failures: text chat keeps working.

Phase 5 does not add voice selection, speech rate, pitch, per-message replay, SSML, long-text chunking, audio files, a backend speech endpoint, or automatic narration of restored history.

## Web Speech API primer

The browser exposes one shared `SpeechSynthesis` controller at `window.speechSynthesis`. An application creates a `SpeechSynthesisUtterance` containing text and passes it to `speechSynthesis.speak()`.

The important operations are:

| Operation | Purpose in this project |
| --- | --- |
| `speak(utterance)` | Adds the assistant reply to the browser's speech queue. |
| `cancel()` | Immediately stops current speech and clears queued speech. |
| `pause()` | Pauses the current utterance. |
| `resume()` | Continues a paused utterance. |

An utterance emits lifecycle events such as `start`, `pause`, `resume`, `end`, and `error`. The UI converts those browser events into a small React state machine.

References:

- [MDN: SpeechSynthesis](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis)
- [W3C Web Speech API](https://dvcs.w3.org/hg/speech-api/raw-file/tip/webspeechapi)

No audio travels through the FastAPI backend. The operating system and browser choose and render the voice. This keeps the first version small, but it also means available voices and exact sound vary by device.

## Mental model and data flow

```text
User submits typed text or a reviewed voice transcript
                         |
                         v
                 POST /chat succeeds
                         |
              +----------+----------+
              |                     |
              v                     v
     Render response text     Record pending actions
              |
              v
    Is spoken output enabled and supported?
              |
       yes ---+--- no --> Finish; text remains usable
        |
        v
Cancel old utterance -> create utterance -> speak response
        |
        v
Browser speech events update global controls
```

The speech state machine is:

```text
unsupported

idle -> speaking -> paused
 ^         |          |
 |         +----------+  Resume
 |                    |
 +--------------------+  Stop, completion, or replacement

speaking -> error -> next valid attempt may return to speaking
```

Speech output is deliberately downstream of chat success. It never creates a message, calls a backend API, or changes an action proposal.

## File responsibilities

### `ui/src/voiceSynthesis.ts`

This is the browser adapter. It keeps Web Speech API details out of React components.

It defines:

```ts
type VoiceOutputState =
  | "unsupported"
  | "idle"
  | "speaking"
  | "paused"
  | "error";
```

`VoiceSynthesisController` owns the active utterance and exposes:

```ts
speak(text: string): boolean
pause(): void
resume(): void
stop(): void
dispose(): void
```

The controller retains the current utterance. This is important because browser implementations have historically behaved more reliably when the application keeps a reference until playback finishes.

Every new utterance receives a generation number. When speech is replaced, the generation advances. A delayed event from the old utterance can therefore be recognized as stale and ignored instead of incorrectly changing the current UI to `idle` or `error`.

### `ui/src/hooks/useVoiceOutput.ts`

This hook gives React one owner for playback and preference state. It:

- creates and disposes the controller;
- translates controller errors into user-facing text;
- exposes stable callbacks to `App`;
- defaults the setting to enabled;
- persists the setting under `home-ai-assistant.voice-output-enabled`;
- stops speech immediately when the user disables spoken replies.

Reading and writing local storage is wrapped in `try/catch`. Privacy modes or browser policies can deny storage, and that must not break the application.

### `ui/src/components/VoiceOutputControl.tsx`

This is a presentational component. It receives state and callbacks rather than talking to the browser directly. It contains:

- the “Spoken replies” checkbox;
- a Pause or Resume button, depending on state;
- a Stop button;
- an accessible live status message;
- disabled states for unavailable or inapplicable actions.

Keeping browser access out of the component makes the controls easy to test with ordinary callback assertions.

### Existing integration points

`App.tsx` calls `speak(response.response)` only after a successful chat response has been rendered. It calls `stop()` before a new submission or new conversation.

`MicrophoneControl.tsx` calls `onVoiceInputStart` before recognition starts. `App` connects that callback to `stop()`, preventing the microphone from hearing and transcribing the assistant's own speech.

## Step-by-step implementation explanation

### Step 1 — Detect support

Check for both browser objects:

```ts
"speechSynthesis" in window
  && typeof window.SpeechSynthesisUtterance === "function"
```

Checking both avoids presenting functional controls when only part of the API exists. Unsupported status is a capability result, not an application error.

### Step 2 — Normalize input

`speak` trims the response and rejects an empty string. Empty utterances provide no value and can leave browser queues in confusing states.

### Step 3 — Replace queued speech

Before creating a new utterance:

1. Increase the generation counter.
2. Detach handlers from the old utterance.
3. Call `speechSynthesis.cancel()`.
4. Create and retain the new utterance.

This implements “latest reply wins” and prevents overlapping audio.

### Step 4 — Configure and observe the utterance

Set `utterance.lang` to `navigator.language`, with `en-GB` as a fallback. Do not choose a named voice in Phase 5; the browser/OS default is intentional.

Attach event handlers before calling `speak`. Each handler checks that its utterance is still current. Completion returns the UI to idle; a synthesis error returns an error state and explanatory message without touching chat state.

### Step 5 — Connect browser state to React

The hook constructs the controller inside an effect and disposes it during unmount. Its callbacks update React state.

The preference rule is intentionally simple:

```text
missing stored value -> enabled
stored "false"       -> disabled
any other value      -> enabled
```

Turning output back on affects future replies only. It does not surprise the user by replaying the latest visible message.

### Step 6 — Speak only live successful replies

The correct integration point is the success branch of `handleSubmit`, after the assistant message is appended:

```ts
setMessages(/* append assistant text */);
setPendingActions(/* preserve visual proposals */);
speakResponse(response.response);
```

Do not trigger speech from a React effect that watches the messages array. Such an effect could narrate restored history, repeat speech after unrelated rerenders, or speak optimistic/failed messages.

The following data is never passed to speech synthesis:

- `request_id`;
- `latency_ms`;
- `sources`;
- `memory_refs`;
- `evidence_status`;
- pending-action descriptions or results;
- session history loaded by `GET /sessions/{id}`.

### Step 7 — Coordinate user interactions

Current playback stops when:

- the user submits a new message;
- microphone recognition begins;
- the user starts a new conversation;
- spoken replies are disabled;
- Stop is pressed;
- the hook unmounts;
- a newer response replaces it.

Stopping on new user intent gives predictable audio and avoids recognition feedback.

### Step 8 — Keep controls accessible

The setting uses a native checkbox with a visible label. Playback buttons use explicit accessible names. The status is exposed with `role="status"` and `aria-live="polite"`, so state changes do not aggressively interrupt screen-reader activity.

Keyboard focus uses the existing visible focus treatment. Mobile layout wraps the controls and moves status text onto its own row.

## Error and edge-case behavior

| Situation | Required behavior |
| --- | --- |
| API unsupported | Show unavailable status; disable playback buttons; preserve text chat and saved preference. |
| Empty assistant response | Do not queue speech. |
| Browser `speak()` throws | Show voice error; leave response visible; do not show the chat error banner. |
| Utterance emits `error` | Move only voice output to `error`. |
| Old utterance finishes after replacement | Ignore its stale event using the generation guard. |
| Local storage unavailable | Keep the in-memory preference for the current page. |
| Reload with saved `false` | Keep output disabled. |
| Reload with saved history | Render history silently. |
| Pending action returned | Render the confirmation card; do not narrate or execute it. |

Speech synthesis is a global browser service for the page, so `cancel()` clears the entire page queue. The application intentionally owns all speech queued by this UI.

## Automated testing strategy

Phase 5 introduces Vitest, jsdom, React Testing Library, `jest-dom`, and `user-event`.

The test environment supplies mock implementations of `SpeechSynthesis` and `SpeechSynthesisUtterance`. Tests inspect calls and dispatch lifecycle handlers; they never require installed voices or produce audio.

Coverage includes:

- supported and unsupported detection;
- blank-input rejection;
- cancelling before new speech;
- text trimming and language setup;
- pause, resume, end, stop, and disposal;
- synthesis errors and throwing browser APIs;
- stale-event protection;
- accessible checkbox and playback controls;
- default and persisted preferences;
- stopping when disabled;
- exactly one utterance for a successful live reply;
- no utterance for failed chat requests;
- silent session restoration;
- honoring a persisted disabled preference.

Run:

```powershell
cd ui
npm run lint
npm run build
npm run test:run
```

`npm test` starts Vitest in watch mode for development. `npm run test:run` performs one deterministic verification run.

## Manual browser verification

Automated tests prove application decisions and state transitions. They cannot prove that a real voice is installed, that sound reaches speakers, or that a browser/OS combination implements pause identically.

Test both Chrome and Edge on `http://localhost:5173`:

1. Start the backend with `./run.ps1` from the repository root.
2. Start the UI with `npm run dev` from `ui/`.
3. With no saved preference, send a message and confirm the visible reply is spoken once.
4. Pause mid-reply, confirm audio stops, then Resume and confirm it continues.
5. Press Stop and confirm the controls return to idle.
6. Send a second message during speech and confirm the older audio stops.
7. Turn spoken replies off, reload, and confirm the setting remains off.
8. Turn it on and confirm an old reply is not replayed; send a new message and confirm that one is spoken.
9. Start voice input during playback and confirm speech stops before listening begins.
10. Reload a conversation with existing assistant messages and confirm they render silently.
11. Trigger a pending action and confirm its card remains visual and still requires Confirm or Reject.
12. Deny microphone permission and confirm that voice output and text input remain independent.

## Troubleshooting

### The text appears but there is no sound

- Confirm “Spoken replies” is checked.
- Confirm the browser tab and operating system are not muted.
- Check that an operating-system speech voice is installed.
- Try Chrome or Edge and perform another user-initiated chat request.
- Inspect the voice-output status rather than the chat error area.

### Pause or resume behaves differently on a device

Speech behavior is implemented by the browser and operating system. Re-test Stop and a fresh reply. Device-specific pause limitations do not affect text chat.

### Old audio continues or controls show the wrong state

Verify that replacement calls `cancel()`, that the controller retains only one utterance, and that every lifecycle handler checks the generation token.

### Tests pass but no real audio plays

This is expected when the issue is outside JavaScript state. Unit tests use a mock speech engine. Complete the manual browser and speaker checks.

## Interfaces and safety boundaries

No backend endpoint, database schema, request type, or response type changes in Phase 5. The existing interfaces remain:

- `GET /health`
- `POST /sessions`
- `GET /sessions/{session_id}`
- `POST /chat`
- `POST /actions/{action_id}/decision`

Only `ChatResponse.response` is sent to synthesis. The backend remains the authority for sessions, memory, tools, and action execution. Speech never confirms an action and never converts a proposal into a completed operation.

## Acceptance criteria

- A new successful reply is spoken by default and remains visible.
- The enabled setting survives reloads.
- Pause, Resume, and Stop reflect current playback state.
- Newer user intent and replies prevent overlapping speech.
- Restored history remains silent.
- Metadata and action cards are not narrated.
- Unsupported and failed synthesis leave text chat usable.
- Controls are keyboard accessible and expose meaningful names/status.
- Frontend lint, build, and automated tests pass.
- Chrome and Edge audible-output checks are completed manually.

## Future Phase 6 extensions

Phase 6 may add a selected voice, rate control, additional usability work, and broader browser resilience. Those settings should build on the existing controller/hook boundary rather than move speech behavior into chat components.
