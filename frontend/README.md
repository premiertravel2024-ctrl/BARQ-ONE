# BARQ — premium React front end

## Design rationale (8 lines)
1. Calm, high-contrast surfaces (#0B0D12 / #12151C / #181C25) for long coding sessions.
2. An indigo → violet gradient is reserved for primary actions, not large text blocks.
3. Messages are limited to a comfortable reading width; chat and composer typography is 16px, with 1.65–1.7 line height.
4. Cairo supports Arabic and Inter supports Latin; JetBrains Mono anchors code.
5. Borders stay subtle; shadows signal elevation without a glossy dashboard feel.
6. Tokens and animation constants live in `styles/tokens.css` and `lib/motion.ts`.
7. Motion is interruptible, transform/opacity-based, and respects reduced motion.
8. Menus, dialogs and focus states support mouse, keyboard, and touch.

## Repository layout

```text
frontend/
├── index.html
├── package.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
├── tsconfig.json
├── README.md
└── src/
    ├── App.tsx
    ├── main.tsx
    ├── i18n/index.ts
    ├── lib/chat.ts
    ├── lib/mockAI.ts                 # Replace this file to connect the live API
    ├── lib/motion.ts
    ├── store/index.ts
    ├── styles/tokens.css
    ├── styles/global.css
    ├── components/ui/
    │   ├── Button.tsx, IconButton.tsx, Switch.tsx, Tooltip.tsx
    │   ├── Dropdown.tsx, Modal.tsx, Toast.tsx, Skeleton.tsx
    │   └── CommandPalette.tsx
    ├── components/chat/
    │   ├── MessageList.tsx, Message.tsx, CodeBlock.tsx
    │   ├── Composer.tsx, Attachments.tsx, ModelSelector.tsx
    │   └── EmptyState.tsx
    ├── components/layout/
    │   ├── Sidebar.tsx, TopBar.tsx, RightPanel.tsx
    │   └── SettingsModal.tsx
    └── pages/Playground.tsx
```

## Setup (Node.js 20.19+ / 22+)

```bash
cd frontend
npm install
npm run dev
npm run build
```

- Dev: <http://127.0.0.1:5173> (Python requests to `/v1` are proxied).
- Production build: `web/react/`. FastAPI serves this at `/` when the build exists and leaves the legacy HTML UI as a fallback when it doesn't.
- Button lab: <http://127.0.0.1:5173/playground> (also works via packaged Python service).
- Windows `scripts/build_windows.ps1` builds the React bundle before PyInstaller.

## Mock service boundary

`src/lib/mockAI.ts` exposes `aiService.stream(request)` as an `AsyncGenerator<AIEvent>`. The chat engine, state, composer and message views know nothing about the HTTP protocol. To connect a real provider, change **only this one file** to call Python's `POST /v1/chat/completions` with `stream: true`; parse `data:` SSE lines into `{type:'token',value:string}` events. The backend must approve agent actions independently; the frontend must not silently execute tools. Current model names are preview choices. Attaching files in the prototype previews images and filenames; actual binary uploading requires implementation in the replacement service.

### Example real-service adapter (documentation only; mock ships as the default)

```typescript
// Replace the mock stream implementation with something like this:
const response = await fetch('/v1/chat/completions', {
  method: 'POST',
  headers: {'Content-Type':'application/json'},
  body: JSON.stringify({model: request.model, stream: true,
    messages: request.messages.map(m => ({role:m.role,content:m.content}))}),
  signal: request.signal
});
if (!response.ok) throw new Error(`HTTP ${response.status}`);
// Read response.body via ReadableStream reader and buffer partial SSE frames.
// Yield {type:'token', value: frame.choices[0].delta.content} for content frames.
```

## Behavior and limitations

- Mock async token streaming, stop, regenerate, edit, copy, ratings, text-to-speech via browser synthesis, speech input via browser SpeechRecognition *where available*.
- Real Gemini voice, REA, GitHub, Ollama and EXE builds remain served by the existing **Python backend** and are **not** simulated as successful in the frontend.
- Theme, language, chats and sidebar mode persist using guarded localStorage. Stored attachments preserve filenames and sizes, not the original binary data across browser restarts.
- Floating scroll control and automatic bottom-follow; Virtuoso takes over after 100 messages.
- Right settings panel is a side panel on wide desktop and a bottom sheet at smaller breakpoints.
- English/Arabic toggle changes document `lang` and `dir`; per-message `dir="auto"` follows message text.
- Reduced motion disables large transitions and button ripple, magnetic pull and shine.
- Mobile navigation includes a drawer; keyboard positioning uses VisualViewport.

## Verification

In an Internet-enabled environment, run:

```bash
npm install
npm run typecheck
npm run build
npm run preview
```

Manually review button states at `/playground`, keyboard focus, mobile resize, speech permissions, long chats and RTL. `npm install` was not possible in the development container without registry DNS access, so the React bundle has **not** been executed there. Source transpilation checks are not an acceptable replacement for runtime testing, accessibility auditing or Lighthouse measurement.

## Recent interaction fixes (source audit)

- Dropdown uses the underlying button's native keyboard activation, avoiding double toggles on Enter/Space, and supports arrow-key navigation.
- Tooltips now resolve top/bottom placement using actual viewport space.
- Edited user messages remove stale replies and regenerate the assistant response instead of leaving conflicting conversation history.
- Loading buttons preserve their measured width; keyboard-triggered ripples originate at the button center.
- Toggle thumb movement now mirrors correctly in RTL; code blocks use the active theme's surface tokens.

These changes passed source syntax/import inspection and Python backend tests. The complete React TypeScript type check, bundle, interaction test, and Lighthouse audit still require an npm installation in a network-enabled build environment.


### Real router integration

The main chat now calls `src/lib/backend.ts`, not `src/lib/mockAI.ts`.
Backend (FastAPI at `127.0.0.1:8000`) exposes an additive SSE UI route
`POST /v1/router/chat/stream` with routing and fallback metadata. Vite's `/v1`
proxy is configured in `vite.config.ts`; build artifacts go to `../web/react`.
Model and provider lists come from `/v1/router/models` and
`/v1/router/providers`; chat history is synchronized to local SQLite.
The sidebar's Coding Workspace button opens live project/agent/build/REA/GitHub
controls. Every tool, edit, GitHub write, and build requires user approval.

The prior mock service is retained as a non-production fixture, not silently
used by the real chat. Node packages were unavailable in the development
container, so `npm run build` and Playwright tests of the React bundle remain
mandatory on a network-enabled build machine. No native Windows installer is
included in this source tree.


### Streaming, fallback and performance

The default chat is connected to `/v1/router/chat/stream` and now displays actual upstream pieces as they arrive, with a visible interruption error for truncated responses. The server only attempts another provider before any part of the answer has been displayed. The assistant-message metadata includes provider, fallback and measured first-token timing when available. The optional right panel shows the in-memory measured performance data via `/v1/performance`; it is not live-provider benchmarking. Ollama native stream uses a bounded configurable context and model retention time for responsive offline sessions.

## Chat typography sizing (Nov 2026)

BARQ chat has a consistent ChatGPT-like font scale for both Arabic and English: user and assistant messages are 16px (line heights 1.65–1.7); the composer and edit field are 16px; the main heading hierarchy is 21/19/17px. Compact helper labels and programming monospace blocks remain unchanged. Styling is in `src/styles/barqPolish.css` and the text-area class is in `src/components/chat/Composer.tsx`. Verify with `npm run test:ui`.
