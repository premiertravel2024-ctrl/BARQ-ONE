# BARQ AI v2.30.0 — Integrated Workspace & Live Voice Repair

## What changed
- Workspace defaults to the code editor, not a full-screen rendering of the original task prompt. New coding missions move to the live-code panel. The Work Center collapses the original brief.
- Workspace live-code polling is adaptive: 350ms while streaming, 1300ms otherwise; identical data no longer triggers re-render.
- Gemini Live can query the current coding mission status supplied by the local BARQ client, with task id, phase, status and short summary. Project files and secrets are NOT sent automatically.
- An explicit spoken request such as «تابع» can send a continuation instruction into the current chat for the matching task; actual edits and system operations still require the existing approvals.
- Recent speech is required for voice-triggered stop/continue actions. Background audio and another speaker cannot be reliably authenticated by the transcript gate; voice biometric recognition is NOT implemented.
- Voice transcript chunks are merged with basic duplicate/overlap handling and interrupted assistant messages are not saved as final answers.
- Desktop-open requests missing from the app/file index are handed to the audited Windows task manager only when permissions allow; disabled file kinds cannot bypass policy.
- The Gemini Live desktop Google-open tool is included in the local dispatcher allowlist, while public read-only Google link remains separate.
- Fast-path chat commands recognize more Egyptian variations of continuation.

## Validation (this build environment is Linux, NOT Windows)
- 49 focused tests: PASSED.
- 71 TypeScript/TSX files syntax-transpiled: 0 syntax errors.
- 6 transcript-merge examples executed with Node: PASSED.
- Comprehensive pytest: 1218 passed, 1 skipped, 7 failed. Six failures require `esbuild`, one requires `google-genai`; these dependencies are not installed in this environment. These are not counted as passes.
- No verified full Windows EXE or installer build, no measured speech diarization accuracy, no end-to-end Gemini Live hardware test. This is a SOURCE update, not a Windows-ready binary.

## Recommended verification on Windows
1. Extract the full ZIP to a NEW folder; do not stack old patches.
2. Run `BUILD_BARQ.bat` with network access to restore project dependencies.
3. Test workspace with a short and long coding task; verify actual generated code is displayed and old prompt is collapsed.
4. Enroll a wake phrase and test in quiet and noisy environments; do not enable voice computer control unless wanted.
5. Confirm the microphone has good echo cancellation. Use a headset for strong background audio; speaker identity authentication is not guaranteed.
6. Run live call and say «وصلت لفين؟» then «تابع». Confirm that progress comes from the active task and file changes still await on-screen confirmation.
7. Inspect `release/BARQ_DIAGNOSTICS.zip` if Windows build gate fails.
