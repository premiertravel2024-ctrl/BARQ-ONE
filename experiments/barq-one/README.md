# BARQ ONE — OpenHub visual integration

This feature branch stages the integration of the BARQ AI assistant and AM OpenHub software catalog without replacing the existing BARQ application.

## Prototype status
A standalone Vite visual prototype has been prepared locally (Arabic RTL, dark glass UI, holographic CSS orb, 16 GitHub tools, search, filters, favorites, task board, and demo chat). **A self-contained interactive HTML preview is committed as `preview.html`; the full Vite prototype source has not yet been committed.**

The prototype is not an operational AI assistant and does not install software, control Windows, provide voice chat, or produce a Windows EXE.

## Integration approach
1. Port the visual design into BARQ's existing frontend and preserve voice, chat, and command infrastructure.
2. Add an OpenHub catalog module backed by a reviewed list of official GitHub repositories.
3. Implement Windows package management behind an explicit permission boundary with installer provenance verification.
4. Connect the catalog to BARQ's execution engine through typed commands, not unrestricted shell interpolation.
5. Add Windows CI build and smoke tests before shipping an installer.

## Source prototype
See the BARQ ONE Visual Prototype ZIP supplied in the ChatGPT conversation. The current branch includes a runnable standalone HTML preview and catalog, but is not a completed integration.
