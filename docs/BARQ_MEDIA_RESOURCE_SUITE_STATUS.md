# BARQ ONE – Media and Resource Suite (development)

This is an incremental feature branch, not a signed or installed Windows release. It is based on the existing BARQ 2.40 repair branch, leaving the main branch unchanged.

## Verified source integration points
- Python 3.11 + FastAPI backend is defined in `api.py`. New API routers are registered there.
- React 18 / TypeScript / Vite UI navigation is in `frontend/src/pages/BarqOne.tsx` and `frontend/src/components/layout/OperationsFrame.tsx`.
- Typed chat fast paths enter through `frontend/src/lib/chat.ts`; voice tool declarations and dispatch live in `voice/computer_tools.py`, using the existing Computer Control enabled policy.
- The computer control policy is read from `computer_control/api.py`. None of the new features bypasses its enabled flag.

## Current scope
1. **Resource Saver**: real process/RAM sampling through psutil; conservative whitelist and protected BARQ/Windows processes; read-only UI with explicit confirmation before limited background-app suspend. Timed two-minute restore and normal-exit/startup recovery are present. A separate detached guardian was added to attempt restore after unexpected BARQ exit, using an atomic journal and PID create-time checks. If it cannot start, BARQ refuses to suspend any process. No forced termination, no service modification, no automatic modes or admin elevation. **Crash recovery requires physical Windows acceptance testing** before release.
2. **Live Wallpapers**: BARQ controls independently installed Lively through its documented CLI. Library previews, apply, play/pause/stop, and volume. On 8.1, use official v0.9.6.0 or the compatible user-maintained AM Lively build. Modern Lively installer requirements depend on release and Windows build. Installation needs the user's consent. App's own settings own fullscreen/battery pause rules. CLI success is not visually verified playback. A native user-initiated file picker for local video/GIF has been added, with a fixed media-extension allowlist. Its real Lively import still requires a Windows acceptance test.
3. **Watch Together**: separate, isolated localhost signaling server; one guest per room; random host/guest tokens and six-digit code; host selects a local video File in their browser (never sends file to BARQ server); WebRTC sends A/V to guest P2P if browsers and NAT allow; text chat, reactions, guest control requests, and local SRT/VTT subtitles (only the currently displayed subtitle text is relayed, never the file); temporary Quick Tunnel option **only after explicit publish approval** for testing, not production. Closing a room terminates its state and the tunnel when no rooms remain. Automatic transcoding, alternative audio track selection and production relay connectivity are **not yet implemented**. Remote-stream performance is not verified.

## License inventory (free software; license depends on exact binary)
- **BARQ app:** existing project license remains unchanged.
- **Lively Wallpaper modern versions:** GPL-3.0; external process only, not redistributed as part of BARQ. Reference: https://github.com/lively-community/lively
- **Lively Wallpaper v0.9.6.0:** Microsoft Public License (Ms-PL); retain original attribution and license if distributed. Reference: historical v0.9.6.0 source.
- **psutil:** BSD-3-Clause. https://github.com/giampaolo/psutil
- **FastAPI:** MIT. https://github.com/fastapi/fastapi
- **Uvicorn:** BSD-3-Clause. https://github.com/encode/uvicorn
- **cloudflared:** Apache-2.0. https://github.com/cloudflare/cloudflared; free Quick Tunnels are for development/testing only. https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/
- **FFmpeg:** builds may be LGPL or GPL depending configuration. Not bundled or used by Watch Together yet.
- **WebRTC and HTMLMediaElement.captureStream:** built into supported browsers, no separate paid API. A free public STUN server may assist P2P but does not guarantee NAT traversal; TURN/relay is not bundled.

## Test requirements before merging
- CI: React strict build, Python backend tests, native Windows EXE self-test + installer, smoke test.
- Windows 10/11: actual Lively CLI and detected library; timing and playback verify.
- Windows 8.1: launch compatible version without unsupported modern commands.
- Resource Saver: precise PID identity validation, confirmation, normal stop/restore, stale PID recovery, unexpected BARQ crash and resume. **Block full safety acceptance until crash recovery has been tested under forced BARQ termination on Windows.**
- Watch: two modern browsers on localhost; WebRTC SDP/ICE, chat and guest login; one remote guest with explicit Quick Tunnel approval and real upload link; room closes and tunnel disappears; no data leak from selected file or BARQ admin API.
- Confirm microphone voice dispatch for all new commands on the target Windows computer.
