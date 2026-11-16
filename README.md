# تحديث 2.29.0 — مكالمة صوتية متواصلة

التقرير: docs/v2.29/LIVE_VOICE_AR.md. اضغط أيقونة موجات الصوت في الشات بعد ضبط Gemini. حزمة سورس؛ تشغيل Windows والمكالمة الحقيقية غير مختبرين هنا.

# تحديث 2.28.0 — شات أقرب وأوامر فتح أوضح

التقرير: docs/v2.28/CHAT_LAUNCH_AR.md. سورس كامل؛ شغّل BUILD_BARQ.bat للبناء على Windows.

# تحديث 2.27.0 — تحسين هندسة ومراجعة UI

التقرير الحالي: docs/v2.27/UI_ENGINEERING_AR.md. سورس كامل مع فحوص UI محددة وتعليمات تصميم مشتركة؛ لا يدعي تحققًا بصريًا من التطبيقات المولدة.

# تحديث 2.26.0 — تخطيط المشروع وربط المتطلبات بالتحقق

التقرير الحالي: docs/v2.26/PROJECT_PIPELINE_AR.md. فك الحزمة وشغّل BUILD_BARQ.bat. اختبارات التشغيل الجديدة تخص Python؛ الحزمة سورس كامل وليست EXE مختبرًا على Windows.

# تحديث 2.25.0 — مراجعة جودة ملفات المشروع

التقرير الحالي: docs/v2.25/QUALITY_AR.md. السورس الكامل مع اختبارات الجودة؛ ليس نسخة EXE مختبرة على Windows.

# تحديث 2.24.0 — إصلاح تعافي توليد الكود

التقرير الحالي: docs/v2.24/RECOVERY_AR.md؛ الأدلة: verification/v2.24. سورس كامل وليس EXE مختبرًا على Windows.

# تحديث 2.23.0 — مراجعة البرنامج وتنسيق مساحة العمل

التقرير الحالي: docs/v2.23/REVIEW_AR.md. السجلات: verification/v2.23. حزمة سورس كاملة، وليست EXE مختبرًا على Windows.

> **2.22.2 — مراجعة عقل برق:** تصحيح الاعتماد على نتائج اختبارات قديمة وفرض تحديد مشروع تجهيز البيئة. التقرير في `docs/v2.22.2/BRAIN_AUDIT_AR.md`.

> **تحديث 2.22.1:** إصلاح توقف الاختبارات بسبب غياب pytest. تجهيز بيئة مشروع وتنزيل الاعتماد يحتاج موافقة واضحة، ثم تُستأنف الاختبارات. انظر `docs/v2.22.1/REPORT_AR.md`.

> **BARQ v2.22.0 — إصلاح توليد الملفات وعرض الكود أثناء العمل.** تحقق صحيح لردود FILE، بث مباشر داخل مساحة العمل، واستكمال المهمة للاختبار وبناء Windows بموافقتك. [التقرير والاختبارات والحدود](docs/v2.22/BUILD_REPORT_AR.md).
>
> فك السورس كاملًا في مجلد جديد وشغّل `BUILD_BARQ.bat` من مجلد `BARQ`. عند نجاح كل المراحل: `release/BARQ_Setup_2.22.0.exe` و`release/BARQ_Portable_2.22.0.zip`.
> هذه حزمة سورس مختبرة على Linux؛ لم يُبنَ أو يُختبر EXE/مثبت v2.22.0 على Windows هنا.

## BARQ v2.5.0 — Free Coding Models + Fast Responses + BARQ AI

New opt-in Windows desktop control module with user approvals, local vision privacy and audit logging. See [COMPUTER_CONTROL_README_AR.md](COMPUTER_CONTROL_README_AR.md). Existing data paths, app ID, chat routing and models are unchanged.

# BARQ — AI workspace (Windows source, original project)

**Status: tested source code, not an approved production Windows installer.** The end-to-end Windows EXE, REA MCP, external cloud API, and Egyptian live voice hardware tests have **not** yet been performed on the target computer. This project must not be advertised as a finished Windows executable until those checks pass.

AI Router Agent combines a dark Arabic desktop-style interface, cloud-first free-tier LLM routing, existing local **Ollama** models for offline fallback, coding workspace workflows, MCP tools (including optional REA), optional GitHub CLI actions, and an EXE building frontend. The Python backend is bundled with a pywebview Windows shell when packaged. The UI uses GE SS Two.

## Free-first model selection

- **Cloud**: Gemini 3.8 Flash and 3.5 Flash-Lite, Groq GPT-OSS models and OpenRouter's free route are configured. Other providers remain disabled until their free limits/terms are confirmed. A free account/API key may still be required; model availability, free eligibility, and quotas can change.
- **Offline**: use Ollama models **already downloaded on the target computer** at `http://127.0.0.1:11434`. The app does not install Ollama or download a model. Auto mode prefers cloud and fails back to installed local models; Local mode never sends chats to a cloud model; Cloud mode disables fallback.
- **Coding**: coding-specific router scoring and an agent prompt for inspecting repository context, making small guarded edits, checking syntax, reviewing test evidence, and avoiding fabricated actions.
- **Privacy**: code and chat content selected for a cloud model will be transmitted to that provider. Secret masking is best effort, not a guarantee. Use **Local only** for source code that must not leave your computer.

## Coding Studio / approval process

1. Enter an absolute local **workspace folder** (for example `C:\\Projects\\AM-PDF-Studio`). The assistant can map source/test filenames, inspect functions/classes and their line numbers, search for literal phrases, and run a read-only repo diagnostic scan.
2. Switch on **Agent** mode and describe a coding task. AI proposes **one tool action at a time**, allowing you to inspect its arguments and explicitly approve it.
3. A source edit is only a **preview**. Even after approving the tool action, the file is **not changed** until you review the diff and approve saving a second time.
4. On save, a local backup supports undo. The agent can **propose its next step** based on evidence of the saved change; each follow-up tool action still requires separate approval.
5. `run_tests` can launch `python -m pytest -q` on a project, but only after explicit confirmation because repository tests execute code. Failures and logs are shown instead of declaring false success.

Built-in source checks: Python AST syntax and warnings about potentially risky calls/hardcoded credentials, JSON/YAML/TOML parse checks. These are limited static checks, not a full security audit, type checker or semantic compiler. JS/TS outlines do not yet implement semantic parsing. Repo and test discovery is intentionally bounded. File edits are confined to permitted workspace paths and create recoverable backups. The application does not autonomously execute arbitrary shell commands or install GitHub repos.

Useful endpoints (localhost only):

| Function | Endpoint |
| --- | --- |
| Health / connectivity | `GET /health`, `GET /v1/router/connectivity` |
| Models / providers | `GET /v1/router/models`, `GET /v1/router/providers` |
| Codebase overview | `GET /v1/coding/map?workspace=...` |
| Project diagnostics | `GET /v1/coding/diagnostics?workspace=...` |
| Literal code search | `GET /v1/coding/search?workspace=...&phrase=...` |
| Source outline | `GET /v1/coding/outline?workspace=...&path=...` |
| Exact-match diff preview | `POST /v1/coding/replace/preview` |
| Agent plan / approved tool | `POST /v1/agent/plan`, `POST /v1/agent/execute` |
| Continue from saved edit | `POST /v1/agent/resume` |
| Approve source save / undo | `POST /v1/workspace/edit/apply`, `POST /v1/workspace/edit/undo` |
| MCP discovery / invocation | `GET /v1/mcp/tools`, `POST /v1/mcp/run` |
| Build preview / run | `POST /v1/build/preview`, `POST /v1/build/run` |

## Local development (Python 3.11+)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
python -m pytest -q
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/` or use `START_WINDOWS.bat` (development launcher). Do **not** bind the service to a public address: it has no multi-user authentication. On Windows, installed API keys can also be saved to the local credentials manager from the interface; never commit `.env` to Git.

## Windows EXE and installer

The source includes `desktop.py`, `scripts/build_windows.ps1`, `scripts/installer.iss`, and `.github/workflows/windows-build.yml`. **On Windows with Python 3.11**, execute:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

The PowerShell build installs pinned-range dependencies in `.buildvenv`, runs Python tests, packages pywebview/uvicorn/web resources with PyInstaller, and optionally creates a `Setup.exe` with Inno Setup 6. A GitHub Actions Windows workflow can build and upload the output **after this code is published in an authorized repository**. An actual Windows EXE has not been built or smoke-tested by this Linux development environment. For other projects, the EXE Builder supports recognized Python, Tauri, and Electron workflows, subject to their required local build tools and separate approval.

## REA, GitHub and other tools

REA is integrated as a configurable **MCP client**, not a hardcoded guessed CLI. It remains disabled by default until its runtime and tool schemas are discovered on the target PC. Enabling a third-party MCP server may execute installed code; review package provenance and permissions first. GitHub actions use the locally authenticated GitHub CLI (`gh auth login`) where available. No default arbitrary-shell facility is granted to models.

## Voice

Gemini transcription, Egyptian-Arabic prompt style, Charon and other male voices, and experimental Gemini Live flow are included. They require a compatible **Google API key, online access, microphone/audio devices and available free quota**. Egyptian accent fidelity, interrupts and latency must be tested on the real Windows machine. **Offline Ollama text chat continues without Internet, but Gemini speech recognition and TTS do not.**

## Quality gates and outstanding integration checks

Run `python -m pytest -q` and `node --check` on the script extracted from `web/index.html`. Test with offline Ollama already installed, a live free-tier cloud account, REA MCP tool discovery, actual GitHub CLI authorization, the Windows package, clean-install/upgrade/uninstall cycles, microphone permissions and end-to-end EXE builds. Successful unit tests are not proof that these external integrations work on every machine.

**User release agreement:** do not hand off a partial ZIP/installer or claim final delivery before the complete Windows acceptance test on the target PC.

## React interface expansion (October 2026)

The `frontend/` subproject contains the complete React 18 / Vite / TypeScript / Tailwind / Framer Motion UI. It keeps the original Python agent tools and routing intact; the main React chat flow now uses the real FastAPI router through `frontend/src/lib/backend.ts` and `/v1/router/chat/stream`. The isolated `frontend/src/lib/mockAI.ts` remains only as an optional showcase/test fixture; it is not called by the production chat flow. See [`frontend/README.md`](frontend/README.md) for architecture, full file tree, dev commands and behavioral limitations. Once `npm run build` succeeds, FastAPI serves React at `/` and `/playground`; until then the legacy UI remains intact. The Windows build script now builds React before packing files into the executable. Node.js/npm package installation and `npm run build` still need a successful run, followed by Windows/Edge WebView, real providers, and accessibility testing before any final installer release.

## React-to-backend integration progress (current working tree)

- `frontend/src/lib/backend.ts`: abortable SSE events (`routing`, `context`, `model`, `token`, `metrics`, `done`, `error`) carrying actual upstream model/provider tokens as they arrive. A route may fall back before its first visible token; a mid-answer failure is explicitly marked incomplete rather than mixing another model into the answer.
- The React store fetches real provider/model status, dynamically disables unavailable selections, and syncs completed conversations to the local SQLite history. Browser-local history remains available if the local API fails. The default UI locale is Arabic RTL.
- `frontend/src/components/workspace/WorkspaceStudio.tsx`: inspect projects, read files, run static diagnostics, search, propose agent steps, approve tools, preview/save/undo edits, inspect build profiles and approved Windows jobs, discover MCP servers including REA, and preview/approve GitHub actions.
- `frontend/src/components/workspace/ModelControls.tsx`: configure free-tier provider priorities, enable/disable providers, save API keys via the operating system secret store on Windows, and test connection. Secrets are not persisted in localStorage.
- A user-controlled project memory note is stored in `coding/project_state.py` (local SQLite). Sharing the note with the selected model is opt-in for each coding plan. The metadata-only agent activity log does not save prompts, source contents, command arguments or secrets.
- Document attachments supported by the backend are uploaded for text extraction only when sent; original file blobs remain in memory and are not saved to the chat database. Image analysis is not supported by this route and produces an explicit error rather than a fabricated result.
- React voice recording is transcribed through the local Gemini voice endpoint; AI messages try the configured Gemini male TTS voice, with system speech as a best-effort fallback. Gemini needs Internet.

**Verified here:** Python API/unit tests, legacy Chromium DOM regression checks, and TypeScript syntax parsing. **Not verified:** npm dependency installation, actual React Vite compilation/type checking, live cloud/REA/voice sessions, Windows packaging and hardware testing.


## Response latency / true streaming improvements (October 2026)

The browser route `POST /v1/router/chat/stream` and the OpenAI-compatible `POST /v1/chat/completions` with `stream:true` now call the upstream streaming API instead of buffering the full provider reply. Cloud providers use OpenAI-compatible SSE and local Ollama uses native `POST /api/chat` NDJSON. The browser can stop generation via AbortController, which closes the streaming response and upstream generator. Routing status changes are shown during provider fallback; fallback is permitted only before any response text has appeared. If a stream dies after text begins, the partial answer is kept and an error is shown, not silently completed with another model.

Ollama native options default to `OLLAMA_KEEP_ALIVE=10m` and `OLLAMA_NUM_CTX=8192`; these values can be overridden in `.env`. They are conservative defaults, not VRAM auto-detection. You must already have Ollama and a locally downloaded model. The local route never installs or downloads a model or uses Ollama Cloud.

New `router/context.py` selects recent and relevant older turns when a conversation exceeds the chosen model's approximate context capacity, keeping the latest user request and system instructions; omitted older turns are announced as an SSE `context` event. This is heuristic context filtering **not** a model-produced memory summary. The existing opt-in local project-memory feature remains separate.

`GET /v1/performance` provides measured time-to-first-token, total response time, fallback count and recent responding models **for completed streamed requests in the current process**. Both UIs expose reply-timing information; the React right panel refreshes measured stats while open, and legacy settings offers a refresh control. These figures are not benchmark guarantees, nor are character rates tokens-per-second. Routing considers observed first-token latency once measured. Model availability and free quotas still vary by provider.

Existing approved EXE Builder operations already run as separate async jobs, so builds do not need to block the chat event loop. **Not covered by this update:** truly incremental Gemini speech synthesis/recognition, a verified Gemini Live microphone session, runtime VRAM measurement, React npm dependency compilation, live provider rate-limit measurements, or Windows installer and REA integration testing. The local HTML/JS browser DOM suite and Python mocked-provider suite are the available checks here. No incomplete ZIP or installer should be handed off as a final release.

## Windows Setup.exe packaging (build-ready source)

Windows one-click builder: `BUILD_WINDOWS_EXE.bat` → React production build → project tests → PyInstaller `AI Router Agent.exe` → *self-test the frozen EXE* → Inno Setup `AI_Router_Agent_Setup_2.1.0.exe`. A headless self-test inside `desktop.py` verifies React/assets/config/API without using cloud keys or UI devices, and the builder fails rather than producing a misleading installer if it fails. `scripts/build_windows.ps1`, `scripts/installer.iss`, and `.github/workflows/windows-build.yml` implement this workflow. See `WINDOWS_BUILD_GUIDE_AR.md`.

**Build state:** this project was prepared and Python-tested on Linux; the Windows executable and installer are *not created yet*. A native Windows x64 runner (or PC) with Python 3.11, Node 22, Inno Setup 6 and network access to dependencies must execute the build script. A WebView2 Runtime is also required on end-user PCs. The installer is unsigned and may trigger Windows SmartScreen until digitally signed. Full Windows GUI / REA / Ollama / Gemini acceptance testing remains outstanding.


## BARQ v2.3.0 identity update

BARQ replaces the user-facing name and uses the original BARQ icon. Existing AppId, Windows install path, app data directory, provider IDs, keyring identifiers, SQLite databases and localStorage keys remain unchanged for compatibility. See `BARQ_BRANDING_RELEASE_AR.md` for exact build instructions. React and HTML fallback now share the red/black design tokens. This Linux checkout is not a verified native Windows installer.


## Cloud providers integration — v2.4.1

For Arabic step-by-step instructions, see `CLOUD_MODELS_GUIDE_AR.md`.

- Gemini 3.8 Flash / 3.5 Flash-Lite: Google's OpenAI-compatible API.
- Groq GPT-OSS 120B / 20B: Groq OpenAI-compatible API on a supported free-plan account.
- OpenRouter `openrouter/free`: a free-only router; after authenticating the key,
  BARQ can discover a bounded set of advertised `:free` variants. Never add paid
  model IDs to `providers.yaml` for automatic routing.
- Mistral, Cerebras, Cloudflare and Hugging Face are opt-in/disabled by default,
  because their free-tier access and spending policies vary by account.
- `POST /v1/cloud/check` and `/v1/cloud/check-all` check credentials + advertised
  model IDs without sending chat prompts; the explicit Test reply action does
  use an actual inference request and consumes the provider's quota.
- Keys stay in the existing Windows Credential Manager (`AI Router Agent`) or
  the user's local .env; they are never sent to the React frontend. The existing
  AppId, installation location and conversation database remain unchanged.
- API auth success is **not** a promise of free usage on a billed provider account.
  Use the provider's free-only plan/account and monitor its dashboard.

The Windows executable for v2.4.1 has not been built or tested in this Linux
runtime; build and self-test it on Windows with `BUILD_WINDOWS_EXE.bat`.


## BARQ AI — Free coding & response speed (v2.5.0)

- BARQ AI answers in its own identity, not as ChatGPT. External providers are still
  disclosed in each model's reply metadata. Existing model routing, secrets and
  `%LOCALAPPDATA%\AI Router Agent` user data path remain unchanged.
- OpenRouter discovery only accepts **actual provider-listed `:free` endpoints**.
  A DeepSeek entry for coding appears after **Settings → Models → Check API & models**
  only if OpenRouter currently offers that exact variant for free. A paid DeepSeek
  model is never submitted. Coding alternatives are prioritized among other
  provider-listed free models and `openrouter/free` remains a safe fallback.
- `BARQ_FIRST_TOKEN_TIMEOUT` can be used to change the cloud waiting threshold,
  in seconds (default 13s for chat and 21s for coding/reasoning). Timeouts only
  apply to the **first visible token**. Once streaming begins, it is left alone;
  failed models before the first token are safely retried using other providers.
- Ollama remains an offline fallback when locally installed; Gemini voice and
  cloud inference still require network access. Nothing is downloaded silently.
- You may need to check providers again after relaunching BARQ: the free catalog
  changes, and for safety dynamically discovered options are not treated as
  verified after a restart.

Windows: run `BUILD_WINDOWS_EXE.bat` in this source folder; after npm / Python
unit tests and frozen EXE self-test, the installer is
`release/BARQ_Setup_2.5.0.exe`. A Windows build has NOT been run in this Linux
workspace, so the binary must be built and tested on Windows.

## BARQ Studio workspace source update (v2.7 preview)

Review `BARQ_STUDIO_V27_RELEASE_AR.md` for the exact implemented/deferred
features and `BARQ_v2.7_CHANGE_PLAN_AR.md` for the change plan and wireframe.
The included prebuilt React files are from the previous version. Before launching
the redesigned workspace, rebuild the new React source with
`UPDATE_STUDIO_UI_WINDOWS.bat` on Windows (Node.js LTS + npm required).
No Windows installer for this update has been built or verified here.

## BARQ v2.8 — Command Network (experimental source update)

See `BARQ_NETWORK_V28_RELEASE_AR.md` for exact feature status and limitations, `docs/BARQ_NETWORK_ARCHITECTURE_AR.md` for module tree and setup, and `docs/BARQ_ROUTE_DEMO_5_CASES.json` for five **synthetic offline routing examples**. The React network-map screen must be rebuilt with `UPDATE_STUDIO_UI_WINDOWS.bat`; the shipped prebuilt UI is unchanged. No real free-provider health or Windows installer validation is claimed.

## BARQ v2.17 — Stability & Architecture

See `BARQ_v2.17_STABILITY_REPORT_AR.md` for the complete Arabic change-by-change
verification report and explicit unverified Windows/React build status.

Windows primary build entry: `BUILD_BARQ.bat` (run `CHECK_BARQ_UI.bat` first).
`BUILD_WINDOWS_EXE.bat` is kept for compatibility; do not bypass the strict gates.

### BARQ UI Polish (v2.30.0)
واجهة المحادثات والإعدادات ومساحة البرمجة حصلت على تحديث تنسيقي مع بحث في أقسام الإعدادات وترتيب الأدوات على المقاسات الصغيرة. تفاصيل التعديلات والاختبارات في `BARQ_V230_UI_POLISH_AR.md`. اختبارات واجهة إضافية: `cd frontend && npm run test:ui`.
