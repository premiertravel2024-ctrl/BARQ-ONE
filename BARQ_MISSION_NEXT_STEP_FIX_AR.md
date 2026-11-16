# BARQ AI — deterministic next step after an approved source edit

## Implemented
- A saved and SHA-256-confirmed project source edit is recorded as `written`, **not** `verified`.
- For Python/JSON/TOML/YAML mission files, the agent proposes `code_check` locally without requiring a fresh LLM plan. This reduces model calls and avoids another JSON failure in a common continuation path.
- The check is a new pending plan and still requires the existing user confirmation. No new source write, test, shell command, or permission grant is performed by this change.
- Outside tracked projects and for other extensions, the legacy planning behavior is retained.

## Verification
- Focused test group: 32 passed.
- Broader targeted group: 46 passed, 1 failed because `esbuild` is not installed in this test environment.
- `scripts/verify_source_integrity.py`: PASS.
- `scripts/verify_release_consistency.py`: PASS.

## Still unverified / incomplete
- True end-to-end multi-file mission execution and UI live token streaming.
- Real Ollama / cloud model reliability with provider quotas.
- Full npm frontend build and Windows EXE packaging.
- Automated GUI application runtime verification.

This is an incremental source repair, not proof of a completely autonomous coding assistant.
