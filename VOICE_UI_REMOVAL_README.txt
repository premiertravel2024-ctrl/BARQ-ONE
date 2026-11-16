BARQ v2.30 — Remove the floating voice panel
=============================================

Changes:
- Remove the always-on floating voice panel (not the live voice service).
- Start or stop Live Voice using the AudioLines / MicOff button in chat composer.
- Ctrl+Alt+B toggles the voice session.
- Voice transcripts continue to be stored in the selected conversation.
- GitHub voice search results now appear as messages in the conversation.
- For sensitive computer control or launch approvals ONLY, a temporary confirmation dialog appears.
- Workspace is available in the sidebar; no duplicate topbar button.
- Chat actions moved to the opposite header side.

Installation (complete source):
1. Back up your current project folder.
2. Extract this archive to a separate folder.
3. Open the BARQ directory and use the project's BUILD_BARQ.bat launcher.

Installation (patch):
1. Back up your current project folder.
2. Extract the patch contents into your BARQ folder preserving relative paths.
3. Build with BUILD_BARQ.bat.

Validation completed: JS UI tests, TypeScript syntax/transpilation checks,
ZIP integrity, and UI tests run from the extracted complete archive.
A Windows EXE build is not validated in this environment.
