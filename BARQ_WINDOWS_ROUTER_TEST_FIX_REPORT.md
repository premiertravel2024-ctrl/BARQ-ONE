# BARQ Windows cloud routing test isolation fix

## Confirmed defect
The test fixture patched router.select.key_for but CommandNetwork.Registry imports router.config.key_for independently. That left its configured-provider check reading Windows secrets instead of fake credentials; Gemini was silently excluded and only Groq attempted.

## Change
tests/test_cloud_diversity_and_dropdown.py: isolate both key_for call sites using the same test-only fake. No production routing, permission, paid/free policy, or cloud connection code changed.

## Results (Linux environment, Python)
- 20 focused tests passed.
- Full suite: 840 passed, 6 failed; remaining six require esbuild installed under frontend/node_modules.
- verify_source_integrity.py PASS
- verify_release_consistency.py PASS
- Real Windows EXE build and real cloud/Ollama not verified.

## Windows build
Use the FULL SOURCE archive and run BUILD_WINDOWS_EXE.bat. If frontend dependencies are not installed, run npm ci from frontend, then rebuild.
