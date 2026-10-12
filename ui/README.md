# Home Assistant UI

This is the independent React frontend for the Home AI Assistant. The FastAPI backend remains in the repository's `src/` directory.

## Local development

1. Start the backend from the repository root:

   ```powershell
   .\run.ps1
   ```

2. Install frontend dependencies:

   ```powershell
   cd ui
   npm install
   ```

3. Copy `.env.example` to `.env` if needed and set the backend URL:

   ```env
   VITE_API_BASE_URL=http://127.0.0.1:9000
   ```

4. Start the frontend:

   ```powershell
   npm run dev
   ```

The UI normally runs at `http://localhost:5173`. It checks `GET /health` when it loads.

## Phase 4 voice input

Voice input uses the browser-native Web Speech API. Chrome and Edge are the primary supported local browsers. Open the UI on `localhost`, allow microphone permission when prompted, speak, press Stop, and review or edit the transcript before pressing Send. Voice input never submits automatically and uses the same `/chat` request and session as typed messages.

If the browser does not support speech recognition, or microphone permission is denied, the normal text composer remains fully usable. Browser speech recognition support and behavior can vary by browser version and operating system; no audio is uploaded to the backend.

For the local checks, run `npm run lint` and `npm run build` from `ui/`, then perform the microphone permission, listening, transcript editing, backend submission, denial, unsupported-browser, cleanup, and pending-action checks manually in Chrome or Edge.

## Phase 5 voice output

New successful assistant replies are spoken with the browser-native Speech Synthesis API and always remain visible as text. Spoken replies are enabled by default. The setting is stored under `home-ai-assistant.voice-output-enabled`; disabling it stops current playback, and enabling it affects future replies without replaying conversation history.

The global controls provide Pause/Resume and Stop. Starting another message, starting microphone input, or creating a new conversation stops current speech. Only the assistant's `response` text is spoken: request metadata, restored history, sources, and pending-action cards are not narrated. Action proposals still require the existing visual Confirm or Reject workflow.

The browser and operating system provide the voice, so voice availability and exact playback behavior vary. If synthesis is unsupported or fails, text chat remains fully usable. Chrome and Edge are the primary manual test targets.

Run the Phase 5 checks from `ui/`:

```powershell
npm run lint
npm run build
npm run test:run
```

Automated tests mock speech synthesis and cannot verify audible sound. Also test real playback, Pause/Resume, Stop, interruption, preference persistence, microphone coordination, and silent history restoration in the browser.

## Current scope

Phase 5 is complete: the UI provides session-backed text chat, browser session restoration, message history rendering, error-safe submission, backend-gated action confirmation cards, review-first browser voice input, and optional browser voice output.

The active session ID is stored under `home-ai-assistant.session-id` in browser local storage.
