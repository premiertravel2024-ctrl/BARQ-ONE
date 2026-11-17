# BARQ v2.41.0 Core + UI incremental update

This artifact upgrades an existing compatible BARQ 2.41.0 onedir installation. It is **not** a full installer.
It contains a fresh dist/BARQ/BARQ.exe with bundled backend code plus new web/react static files only.
It preserves user conversations, original wallpaper media, downloaded models, voice helper, settings and other components.
The patch is built after the Windows build, tests and installed binary self-test. It must not be used for an older or incompatible installation.
GitHub artifact: BARQ-v2.41.0-Core-and-UI-update; verify its SHA256 before running.

The UI-only update does NOT contain built-in wallpaper engine fixes. To use safe wallpaper deletion and the native Windows wallpaper-engine changes, install the verified Core+UI update after it is available.

Actual Windows desktop visibility must still be tested on a user-owned desktop; headless GitHub CI cannot prove the wallpaper is visible behind Explorer icons.
