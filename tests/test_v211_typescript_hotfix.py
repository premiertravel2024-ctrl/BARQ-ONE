"""Regression for the two TS2367 errors seen during BARQ 2.11 Windows builds."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_workspace_handoff_matches_actual_discriminated_union():
    store = (ROOT / "frontend/src/store/index.ts").read_text(encoding="utf-8")
    studio = (ROOT / "frontend/src/components/workspace/WorkspaceStudio.tsx").read_text(encoding="utf-8")
    match = re.search(r"export type ToolHandoff\s*=\s*\{[^}]*tab:([^;}]+)", store)
    assert match, "ToolHandoff.tab contract missing"
    variants = set(re.findall(r"'([^']+)'", match.group(1)))
    # Github preview is now an explicit handoff (not a desktop command).
    assert variants == {"tools", "agent", "computer", "github"}
    assert "handoff.tab==='github'" in (ROOT / "frontend/src/components/workspace/WorkspaceTools.tsx").read_text(encoding="utf-8")
    assert "handoff.tab==='agent'?'commands':handoff.tab" in studio
    assert "handoff.tab==='overview'" not in studio


def test_voice_launch_decision_matches_backend_selected_case():
    contracts = (ROOT / "frontend/src/lib/launcher.ts").read_text(encoding="utf-8")
    composer = (ROOT / "frontend/src/components/chat/Composer.tsx").read_text(encoding="utf-8")
    match = re.search(r"export type LaunchResponse\s*=\s*\{decision:([^;]+);", contracts)
    assert match, "LaunchResponse.decision contract missing"
    variants = set(re.findall(r"'([^']+)'", match.group(1)))
    assert "auto" in variants
    assert "selected" in variants
    backend = (ROOT / "launcher/api.py").read_text(encoding="utf-8")
    assert "'decision':'selected'" in backend
    # Voice launcher moved to the single server-side brain/launcher bridge.
    control=(ROOT/'voice/computer_tools.py').read_text(encoding='utf-8')
    assert "if opened['status']=='opened'" in control
    assert "'approval_token':opened['approval_id']" in control
    assert '/v1/launch/voice' not in composer
