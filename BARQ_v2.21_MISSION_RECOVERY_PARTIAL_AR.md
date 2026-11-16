# BARQ v2.21 — Mission Recovery Foundations (partial integration)

## Implemented
- Router `try_models`: bad validator output / schema / empty completion no longer calls provider-health cooldown or circuit-breaker failure; failure is recorded as output quality only. Real timeout, network and HTTP failures retain existing handling and quota guards.
- Persistent EMA for output quality on `Health`, separate from infrastructure availability.
- Safe `coding.blocks` parser for FILE blocks and SEARCH/REPLACE blocks, with path, size and duplicate validation; parsed text is never written automatically.
- `mission.state` atomic JSON persistence for mission metadata, a first-unfinished selector, and a truthful deterministic summary.
- Eleven new offline tests (including path rejection, parsing and persistent state).

## Not yet integrated / not verified
- The new parser and mission-state primitives are NOT wired to the main orchestrator, workspace approvals, chat progress channel or resume UI. This is not a complete S0–S7 mission engine.
- `workspace_write_files`, `code_edit_blocks`, streaming UI, local thinking suppression and adaptive context/token budgets remain unimplemented.
- Existing `test_auto_handoff_rejects_invalid_plan_before_accepting_model` expects `health.fail > 0` for a bad JSON/schema result; it now fails by design because the desired semantics are the opposite. The existing test was not modified.
- Windows EXE, npm frontend build, real models and networking have not been verified.
- Version remains 2.21.0 because no complete 2.22 release is claimed.

## Commands and results
- `python -m pytest tests/test_mission_primitives.py tests/test_router_format_health_split.py -q`: 11 passed.
- `python scripts/verify_source_integrity.py`: PASS.
- `python scripts/verify_release_consistency.py`: PASS.
- `python -m pytest -q --disable-warnings --maxfail=5`: 644 passed, five failures before stopping (4 frontend smoke failures from missing `esbuild`, one intentionally changed output-quality semantic assertion). Not a full green suite.

## Safety
These new modules do not execute user commands, write workspace files or grant permission. All existing approval gates and path policies stay intact. No additional model calls, paid services or dependencies have been added.
