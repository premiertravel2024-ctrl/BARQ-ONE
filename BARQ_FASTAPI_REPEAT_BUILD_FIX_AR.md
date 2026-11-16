# BARQ v2.30 — Fix for recurring FastAPI errors on Windows

## Why the same 11 errors can recur

The original v2.30 API called `app.add_event_handler("startup", ...)`, a legacy API that may not be supported by every installed FastAPI/Starlette combination. A new build creates a **fresh short-path staging folder** under `%LOCALAPPDATA%\Bq\b\...`. Re-running BUILD_BARQ.bat from an older source folder repeats the same error even when an updated ZIP exists elsewhere.

**Do not edit anything inside AppData.** `FIX_AND_BUILD_BARQ.bat` first patches the actual project folder beside it, then invokes the build. It preserves your previous `api.py` as `api.py.before-fastapi-repair.bak`. Only known v2.30 patterns are auto-edited; unexpected code is left unchanged.

The full-source ZIP additionally prints the selected project path, staging path, and matching SHA-256 hashes. It rejects the legacy startup call before npm installation, and after dependency setup imports the actual API module to display an **untruncated traceback** if the Python environment has another issue. It does not skip or weaken release tests.

## Installation

Option A (recommended): Extract the **FULL SOURCE ZIP** into a NEW folder. Run `FIX_AND_BUILD_BARQ.bat` **there**, not from an older copy of the project. The file `api.py` must be alongside `BUILD_BARQ.bat`.

Option B: Extract the **ONE-CLICK PATCH ZIP** into the ROOT of your existing BARQ v2.30 folder, overwriting only the supplied repair/verification scripts. Run `FIX_AND_BUILD_BARQ.bat` in that same folder. The patch has a narrow scope; the full-source ZIP is safer if your old project files were altered or mixed.

If it fails again, send **`release/BARQ_DIAGNOSTICS.zip`** or the full **`release/python-tests.log`**. The single-line errors on the CMD window are truncated; the full `AttributeError` attribute name has not been established from the screenshot alone.

**Limits**: verified by Python tests and static inspection in Linux; full Windows build and EXE are not verified in this environment. No security test gates have been disabled.
