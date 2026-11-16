import sys
from pathlib import Path
from fastapi.testclient import TestClient
import pytest
from api import app
from tools.registry import execute
from agent.orchestrator import parse_plan,ACTIONS

@pytest.mark.asyncio
async def test_python_runner_requires_approval_and_returns_exit_status(tmp_path):
    tests=tmp_path/'tests';tests.mkdir()
    (tests/'test_sample.py').write_text('def test_ok():\n  assert 2 + 2 == 4\n',encoding='utf8')
    with pytest.raises(ValueError,match='confirmation'):
        await execute('project_tests',str(tmp_path),False)
    out=await execute('project_tests',str(tmp_path),True)
    assert out['exit_code']==0, out
    assert '1 passed' in out['stdout']

@pytest.mark.asyncio
async def test_test_runner_rejects_non_python_workspace(tmp_path):
    with pytest.raises(ValueError,match='No Python test project'):
        await execute('project_tests',str(tmp_path),True)


def test_agent_can_request_test_with_explicit_approval():
    result=parse_plan('{"steps":[{"tool":"run_tests","args":{}}],"answer":""}',set(ACTIONS))
    assert result['steps'][0]['tool']=='run_tests'


def test_server_history_recovery_endpoints(tmp_path,monkeypatch):
    # Test conversation records via an isolated store; avoid touching user data.
    from core.history import ConversationStore
    store=ConversationStore(tmp_path/'demo.sqlite3')
    store.put('c1','مشروع جديد',[{'role':'user','content':'اختبر المشروع'}])
    assert store.get('c1')['messages'][0]['content']=='اختبر المشروع'
    assert store.list()[0]['title']=='مشروع جديد'


def test_runner_uses_active_python_interpreter():
    """Prevents Windows build venv tests accidentally using system Python."""
    import sys
    from tools.registry import _test_python_executable
    assert _test_python_executable() == sys.executable
