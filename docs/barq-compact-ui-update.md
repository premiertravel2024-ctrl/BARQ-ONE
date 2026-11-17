# BARQ ONE v2.41.0 — compact UI-only update

This update is intentionally different from a full Windows installer.

- Contains only the compiled `web/react` interface for the existing Windows application.
- Does not replace BARQ.exe, Python runtime, AI models, voice helper, or user settings.
- Requires a compatible installed BARQ ONE v2.41.0 and its bundled React resources.
- Updates `_internal/web/react` for PyInstaller 6 or `web/react` for older onedir layouts.
- The installer refuses to run if it cannot find the existing application and React bundle.
- It uses the existing installation identifier and closes BARQ during the asset update.
- GitHub Actions workflow `ui-update.yml` produces the small `BARQ-v2.41.0-UI-only-update` artifact containing the executable and SHA256 text.
- For first-time installation, backend changes, or different base versions, use the full BARQ installer.
- Official Spotify and Anghami embeds follow provider playback limits and may require login.
- Required TMDB data and image attribution stays in a collapsed disclosure inside Cinema.
