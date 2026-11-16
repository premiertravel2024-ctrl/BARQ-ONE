# BARQ AI v2.21 — Mission Execution Integration (2026-10-28)

This is a targeted source integration, not a certified final Windows release.

## Confirmed defects addressed

1. A freshly approved scaffold used to trigger strict-JSON replanning after every single proposed source change. The coding path now uses a durable per-file manifest and direct FILE-block generation from the existing quota-limited router.
2. Only a single main.py or index.html was previously eligible for direct-generation fallback. The tracked mission now proposes supporting files one at a time (desktop: storage.py, main.py, README.md; web: styles.css, app.js, index.html, README.md), recording proposal attempts and commits. This is a bounded default plan, not a guarantee that all application features are implemented.
3. Explicitly named applications now receive a reasonable workspace folder name when the name is ASCII, without overwriting existing directories.
4. A persisted command interrupted before semantic routing may recover a directly typed, unambiguous coding intent. Ambiguous / computer-control requests are not promoted to execution.
5. The Studio live-code panel retains the actual proposed source while the user reviews the separate save approval instead of showing an empty view between preview and commit.
6. A file progression card distinguishes pending, proposed, saved-but-untested, and attention-needed states. No fake typing animation or implied file writes.
7. Known BARQ scaffold placeholders are rejected when generated as the proposed final entry point.
8. The brain coordinator now requires actual approved test or build evidence for an application before declaring its coding mission completed; static syntax checks alone are insufficient.

## Safety boundaries

- All generation uses Engine.run and the existing Free Guard, limiter, model-selection, and privacy infrastructure; no new paid dependencies.
- Source content is parsed as FILE blocks and checked; model-selected paths cannot change the current manifest target.
- Every file step remains an unapproved `workspace_edit` proposal until it passes the existing preview and explicit save approval flow. Code checks, tests and builds retain their existing approvals.
- Mission status `written` means a real approved commit with a matching hash; it is **not** a build, app launch, runtime test or finished product.
- No OS commands, installations or unapproved writes were added by this change.

## Tests run (in the development environment)

- Backend `python -m pytest -q tests`: **845 passed, 6 failed, 65 subtests passed**. All six failing tests invoke a Node.js chat smoke helper requiring `esbuild`, which was not available in the current container. This does not prove frontend correctness or Windows build success.
- Focused new fake-engine tests: **3 passed** (multi-file approved flow, explicit naming, malicious path / invalid model output refusing write).
- Source integrity: PASS.
- Release consistency: PASS.
- TypeScript syntactic transpilation of touched files with global TypeScript: PASS. Full frontend typecheck and npm build: NOT VERIFIED in this environment (Node dependencies incomplete).
- Windows PyInstaller/Inno Setup build, real Ollama/cloud model behavior, actual UI end-to-end operation: **NOT VERIFIED**.

## Remaining gaps

- No token-by-token code streaming from model to Studio. The Studio now displays the actual proposed file after generation and retains it through review.
- Runtime tests, screenshot/video-based design matching, and EXE building are still separate approved operations; this change cannot guarantee working apps without them.
- The default mission manifest is a conservative starter architecture; complex apps may require the agent to add files using the ordinary approved tools after this phase.
- No claim of zero defects. Complete reliability requires Windows real-provider, UI and installation acceptance testing.

## Windows validation sequence

From a clean extraction of the full ZIP:

1. Open `frontend` and run `npm ci --include=dev --no-audit --no-fund`, followed by `npm run build`.
2. From the project root run `python -m pytest -q tests` and the two release integrity scripts.
3. Run `BUILD_WINDOWS_EXE.bat` only after the above gates pass.
4. In the built app, test an explicit app creation command; approve the scaffold, source proposals and saves separately, verify the file list grows, and then run approved checks and tests. If a model is offline or cannot produce a valid file, the task should pause truthfully instead of inventing completion.
