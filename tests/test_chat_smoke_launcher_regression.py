"""Run launcher/chat behavior instead of searching source phrases."""
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def run_smoke(*args):
    node=shutil.which('node')
    assert node, 'Install Node.js to run mandatory chat regression tests'
    return subprocess.run([node,str(ROOT/'scripts/chat_coordination_smoke.mjs'),*map(str,args)],
                          cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=60)


def test_local_launch_and_chat_approval_behavior():
    result=run_smoke()
    assert result.returncode==0, result.stdout+'\n'+result.stderr


def test_runner_preserves_real_child_assertion_failure(tmp_path):
    entry=tmp_path/'failure.ts'
    entry.write_text("import assert from 'node:assert/strict'; assert.equal(1,2,'deliberate regression sentinel');")
    result=run_smoke(entry)
    assert result.returncode!=0
    assert 'deliberate regression sentinel' in result.stderr
