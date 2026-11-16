# BARQ AI v2.8.6 — Recovery build

- Fixed the typed React `Button.onClick` Git refresh callback (`null | undefined` vs `void`), which prevented TypeScript compilation.
- Added `INSTALL_BARQ_NOW.bat`: builds Windows EXE using *existing* `web/react` assets without recompiling TypeScript. This restores a working installation path at the cost of using the bundled earlier UI snapshot (not all newest frontend changes).
- Preserved the strict fresh React build `BUILD_BARQ.bat` with `npm run build` and TypeScript checks.
- Both build paths keep Python tests, real packaged EXE self-test, and Inno Setup checks. No output is labeled successful without installer and self-test.
- Bundled React JS syntax validated with `node --check`; its declared JS/CSS assets are present. Full Windows build still requires Windows to verify.
- This archive contains **source and prebuilt UI assets**. It is NOT a precompiled Windows EXE installer.
