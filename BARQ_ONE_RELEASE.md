# BARQ ONE 2.40.0

The Command Center now leads with live CPU/GPU usage and temperatures, memory and disk usage. Charts retain up to 30 observed samples, split gaps, and show missing or stale readings explicitly. The shell, chat and animated/lite holograms share BARQ's burgundy/red identity.

Catalog commands such as `ممكن تنزل Windows-MCP` now queue verified setup rather than downloading source code. LibreHardwareMonitor has a dedicated verified setup recipe, with runtime files installed in a writable BARQ toolkit folder. Source-only entries remain clearly labelled. Previously downloaded jobs offer an Install tool now action when a supported recipe exists.

CPU sensor access can require Windows administrator approval. The monitor page provides an explicit action to launch only the installed sensor provider through the Windows UAC prompt. BARQ itself is not elevated. The UI distinguishes binaries installed from successful temperature readings.

Install `BARQ_Setup_2.40.0.exe` from the Windows build artifact. Existing settings and conversations remain in the same data directory. Physical sensor availability and microphone behavior still require testing on the target Windows PC.
