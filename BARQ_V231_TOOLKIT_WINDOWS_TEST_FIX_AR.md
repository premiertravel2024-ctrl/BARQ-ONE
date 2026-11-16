# BARQ v2.31 — Windows build regression fixes

## Source
Based on `BARQ_AI_v2.31_WINDOWS_TOOLKIT_INTEGRATED_FULL_SOURCE.zip`.

## Fixed
1. `test_find_tool_prefers_process_path_without_installer_inventory` used `/usr/local/bin/git`, an invalid cross-platform assertion under Windows path semantics. It now creates an isolated executable placeholder in the test temp directory and checks the *resolved* discovered path on both Windows and Linux. Production tool discovery still tries PATH first and fixed, vetted vendor locations second.
2. `test_voice_media_search_returns_only_filenames_and_no_execution` depended on the real machine's persisted device index state, causing it to return another index's results on Windows. This test now explicitly tests the no-index consented-folder fallback instead of reading the real user's index. Production `discover_movies` also falls back to a bounded, metadata-only scan of allowed/default video folders when the global index is disabled, empty, unavailable or still starting. It continues to use matching non-empty index results.

## Verification on this environment
- 28 local-media + toolkit + index regressions: PASS.
- 101 selected Windows-MCP, voice, controller, execution, sensors, toolkit, build tests: PASS.
- Full suite: NOT COMPLETE; an early unrelated test failed because `esbuild` is not installed in this Linux environment, and a separate full run exceeded the time limit. The attached new fixes were not verified on a real Windows machine.
- Windows EXE/Inno installer: NOT VERIFIED here.

## Windows validation
On the actual Windows source directory run:

```powershell
py -3.11 -m pytest -q tests/test_v231_toolkit_setup_and_discovery.py tests/test_v231_local_media_workspace.py tests/test_v231_toolkit_index_platform_regressions.py tests/test_v231_full_device_search.py
```

Then run `BUILD_BARQ.bat` from the full corrected source. Do not build `installer.iss` directly.

## Safety
- No test skipped, no build gate disabled, no modification to Windows permissions.
- Movie discovery only returns file metadata, never plays videos or uploads content.
