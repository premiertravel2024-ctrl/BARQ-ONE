# BARQ ONE — Media / Resource Suite: Implementation status

Branch: feature/barq-media-resource-suite
Base: fix/barq-cpu-sensors-app-dedupe (BARQ 2.40)
Status: staged source implementation. Physical Windows and remote-peer acceptance NOT yet done.

## Architecture reviewed
- Python/FastAPI backend; React/TypeScript/Vite frontend; PyInstaller/Inno Setup Windows packaging and GitHub Actions.
- Text commands enter frontend/src/lib/chat.ts. Voice commands originate in Gemini Live and voice/computer_tools.py, which delegates to permission-gated Windows tools.
- New commands use api_routes/feature_command.py, with computer_control.api.load_policy consent.
- At runtime, core/desktop_capabilities.py detects Windows 8.1 versus 10/11, Lively, ffmpeg, cloudflared, and psutil. No claim is made about installed tools on the owner's actual PC.

## Source features implemented
1. Resource Saver: measured process name, RAM, uptime and sampled CPU; conservative allowlist, protected BARQ/Windows/security/voice/media processes, review before temporarily suspending safe background processes, Restore All, timed resume, normal-exit and startup recovery. No force kill, uninstall, permanent service change or auto-stop profile.
2. Lively: separate official program controlled using vetted CLI, modern/legacy OS detection, native library listing, thumbnail preview, show, pause, play, stop, volume and modern random wallpaper. Returns command_sent rather than fabricated visual verification.
3. Watch Together: separate loopback signaling server, one host and one guest, unguessable tokens plus 6-digit room code, local host file selected only within the browser, WebRTC captureStream peer video, ephemeral chat, reactions and control requests. Explicitly approved cloudflared Quick Tunnel can expose only the watch server (not BARQ main API). Room closure cleans up connections.

## Not yet implemented or verified
- Actual two-browser/remote-network video and audio test, unsupported-codec ffmpeg transcode, audio-track picker, synced subtitles, calibrated bitrate/upload adaptation and guaranteed free TURN relay.
- Persistent editable automatic resource profile templates, full real publisher metadata, true graceful close of Windows services and crash-proof restore when a watchdog cannot run.
- Actual Lively CPU percentage, Windows 8.1 CLI verification, file import dialog, real fullscreen/battery playback rules, multi-display tests.
- One Windows EXE build and physical Windows 8.1/11 test; GitHub CI result is reported separately. Do not claim production acceptance.

## Free licenses verified
- Modern Lively GPL-3.0; Windows 8.1 legacy 0.9.6.0 MS-PL.
- psutil BSD-3-Clause; cloudflared Apache-2.0.
- FFmpeg LGPL-2.1+ or GPL-2+ depending on features selected. Not bundled yet.
- WebRTC standard browser feature with no paid license/key; peer connectivity not guaranteed.
- Cloudflare Quick Tunnels need no account but are documented as development/testing only.

## Security
- Never touch critical Windows/security/BARQ, audio, Lively, ffmpeg or tunnel processes.
- No unapproved process stop; no Windows elevation or arbitrary shell from feature commands.
- Only selected local browser File is streamed, not an arbitrary server path.
- Room URLs and codes are ephemeral; only one guest; no chat written to disk.
- Public networking requires visible explicit consent; never tunnel BARQ's administrative HTTP port.
- No DRM bypass or scraping.

## Acceptance tests still needed
- Check all backend and frontend tests on Windows, EXE smoke and installer.
- Validate actual process pause/restart, monitor stats and restore on two consecutive samples.
- Validate Lively command behavior on real Windows 11 and separately Windows 8.1.
- Test browser host/guest, codec support, audio, video, chat, room close, and a remote guest on another network.
