# BARQ AI v2.36.2 — Egyptian natural voice + Windows toolkit patch

## Changes applied

1. `voice/live.py`: added a natural Egyptian conversational prompt for Live calls: follow dialogue context, allow casual exchanges, interruptions, and tone variation; do not recite the user's question or claim unverified execution. Verified tool status remains the sole authority for PC actions. Actual voice quality depends on the configured Gemini Live service, microphone, network and TTS voice.
2. `voice/intent.py`: recognize colloquial requests such as «ممكن تفتحلي»، «محتاجك تشغللي»، «دورلي»، «ينفع تكمل»، including natural prefaces «بقولك إيه يا برق». Negations and hypothetical questions remain non-executable.
3. `voice/command_guard.py`: direct Live tools now use the same canonicalization as BARQ's intent parser, **without removing recency, single-use, negation or model-target verification**.
4. `voice/brain_bridge.py`: natural device-specification questions route to on-device facts rather than a web search, while explicit file searches remain file searches.
5. `voice/computer_tools.py`: the existing approved launcher retries a canonicalized explicit spoken command only when the legacy launcher grammar cannot parse it; all launches still go through the existing policy, index and approval checks. Never run a shell command supplied by the model.
6. `scripts/installer.iss`: include `INSTALL_BARQ_TOOLKIT.ps1` and add a **visible, checked-by-default** Windows toolkit installation task; provide an Install/Repair Toolkit Start Menu shortcut. Users can uncheck the task. Installer retains normal Windows permission boundaries and the existing approval controls; it does not silently grant microphone access or administrator rights. Internet and WinGet are required for some downloads.
7. `INSTALL_BARQ_TOOLKIT.ps1`: fix a path-traversal-validation regular expression for the pinned LibreHardwareMonitor archive. Installation reports go to `%LOCALAPPDATA%\BARQ\toolkit\logs\install.log` and `%LOCALAPPDATA%\BARQ\toolkit\installed-tools.json`.
8. `tests/test_v2363_natural_dialogue_toolchain.py`: new explicit-dialogue, safety and toolkit integration regressions.

## Validation performed

- 450 passed, 3 skipped, 1260 deselected (`pytest -k 'voice or toolkit or github_repository or installer or windows_mcp or computer_control'`).
- 105 passed in the focused voice + command-guard + toolkit + launcher regressions.
- Python module compilation (`compileall`) passed.
- A full pytest run **did not finish** in the available environment; the first failure is from the frontend Node `esbuild` module not being installed here. This is not a successful full-suite claim.
- The Windows installer, third-party tool installation, microphone loopback, speaker and desktop actions **cannot be exercised on this Linux testing machine**. This is a revised full-source ZIP, not an already built EXE.

## Windows installation and verification

1. Unzip the source and run `BUILD_BARQ.bat` on Windows with the standard build prerequisites; do not compile `installer.iss` directly.
2. In BARQ Setup keep `Install BARQ Windows toolchain` checked to download/integrate tools (Git, Node.js, Python, VS Code, FFmpeg, Windows-MCP, LibreHardwareMonitor, and other fixed tools). Some require Windows approval or internet access.
3. The tools are installed in Windows's normal user/system tool locations, not granted hidden privileges inside BARQ. If an installation fails, inspect the toolkit logs and use the Start Menu `BARQ - Install or Repair Toolkit` shortcut to retry.
4. Configure microphone permission and BARQ's voice/desktop-control consent in Settings, start an open Live conversation, and try normal talk followed by «ممكن تفتحلي المفكرة» and «بص شوفلي مواصفات الجهاز»; confirm actual execution instead of trusting narration.
5. If build fails due to npm dependencies, run the project's dependency/setup step with internet access and consult `scripts/build_windows.ps1` / `WINDOWS_BUILD_GUIDE_AR.md`.

## Limitations

The app uses Gemini Live for speech. This patch makes replies and command parsing less robotic, but cannot make the model/voice identical to ChatGPT's real-time voice service. Safety confirmations are not removed. Installation has not been executed on the user's device.
