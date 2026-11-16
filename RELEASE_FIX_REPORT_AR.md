# BARQ — Cloud Config Test Regression Fix (2026-10-28)

## Root cause
On the user's Windows build, nine cloud regression tests failed during `Config.model_validate` rather than within their cloud/router assertions. Those tests used synthetic model/provider configurations that were unnecessarily coupled to runtime allowlist and bundled catalog validation. The production free policy must remain intact.

## Changes
- `tests/test_cloud_connections.py`: build isolated, in-memory `Provider` / `Model` test doubles for read-only discovery scenarios, instead of passing synthetic test configs through the production `Config` validator. Use explicit `free=True` only inside these fakes.
- `tests/test_cloud_diversity_and_dropdown.py`: use test-only model constructs for the fake cloud and local candidates and use allowlisted model names to preserve Free Guard routing logic under test.
- `tests/test_v218_resources_and_security.py`: exercise IPv6 loopback using `[::1]` Host header, avoiding a known `httpx` URL parser incompatibility when constructing `TestClient` with an IPv6 base_url. The production origin/host checks are unchanged.

## Verification
- Targeted cloud, diversity, and resource/security tests: 26 passed.
- Broad Python run with frontend-related filters: 823 passed, one frontend smoke failure due to missing local Node `esbuild` package, 22 deselected.
- `scripts/verify_source_integrity.py`: PASS.
- `scripts/verify_release_consistency.py`: PASS.

## Limitations
- These are test-fixture/compatibility repairs. They do not prove that cloud providers can be contacted, that coding missions execute end-to-end, or that a Windows installer builds.
- No production runtime security checks or Free Guard rules were loosened.
- Frontend tests need `npm ci` in the frontend directory, on a system that has the npm packages available.
