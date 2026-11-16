# BARQ Voice Brain — real Windows acceptance

Run after installing the new BARQ EXE and enabling **Computer Control** AND the separate **Voice commands** permission. Keep Google Voice as your speaker. Never accept HIGH requests via speech; click the on-screen approval after reviewing it.

```powershell
py -3.11 scripts/voice_windows_e2e.py --interactive
```

The helper walks through **12 user-spoken cases**: open Notepad, find an invoice file, open the second result, volume, RAM/CPU, CPU temperature, public web search, GitHub search, deny when voice permissions are off, on-screen HIGH approval, start React project, and stop task.

Use a test folder with a few non-sensitive PDFs. Check exact tool names, status and real process/window state. Every PASS requires your evidence note. The helper does not pretend to press buttons or listen to the microphone; you perform the utterances and mark outcomes. It writes:

- `release/voice-e2e/voice-e2e.json`
- `release/voice-e2e/voice-e2e.md`

## Report limitations

The checklist is **NOT verified** until it has been run interactively on a real Windows 10/11 system with the actual microphone and installed EXE. `--interactive` is disabled when not running on Windows. Without it, all 12 cases are **not_verified** by design.

If a command is blocked, leave it unverified or mark FAIL with exact reported reason. An enabled toggle is not equivalent to real Windows UI Automation or a tested Gemini Live call.
