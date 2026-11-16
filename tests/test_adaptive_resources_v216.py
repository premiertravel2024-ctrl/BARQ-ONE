"""v2.16 portable budgets: deterministic, local and independent of a GPU/API key."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from core.adaptive_resources import AdaptiveResources
from brain.coordinator import Brain
from brain.state import TaskStore
from studio import security_monitor

GIB = 1024 ** 3


def profile(cpu=8, ram=6*GIB, load=20):
    return lambda: {'logical_cpu_cores': cpu, 'cpu_load_percent': load,
                    'ram_total_bytes': 16 * GIB, 'ram_available_bytes': ram}


def test_persistent_modes_and_budget_scale_with_machine(tmp_path):
    config = tmp_path / 'policy.json'
    manager = AdaptiveResources(config, profile())
    assert manager.mode() == 'balanced'
    assert manager.policy()['scan_workers'] == 4
    manager.set_mode('eco')
    assert manager.policy()['scan_workers'] == 1
    assert manager.policy()['scan_max_files'] == 120
    assert AdaptiveResources(config, profile()).mode() == 'eco'
    manager.set_mode('performance')
    assert manager.policy()['scan_workers'] == 8
    assert manager.policy()['scan_max_files'] == 500
    assert config.read_text() == '{"mode": "performance"}'


def test_pressure_preempts_performance_mode(tmp_path):
    tiny = AdaptiveResources(tmp_path / 'tiny.json', profile(cpu=16, ram=400*1024**2, load=93))
    tiny.set_mode('performance')
    limits = tiny.policy()
    assert limits['scan_workers'] == 1
    assert limits['scan_max_files'] <= 60
    assert limits['routing_history_messages'] <= 4


def test_low_end_hardware_never_overcommits(tmp_path):
    tiny = AdaptiveResources(tmp_path / 'tiny.json', profile(cpu=1, ram=2*GIB, load=None))
    tiny.set_mode('performance')
    assert tiny.policy()['scan_workers'] == 1
    assert tiny.policy()['scan_max_files'] == 500


def test_invalid_mode_and_bad_file_do_not_change_mode(tmp_path):
    file = tmp_path / 'bad.json'
    file.write_text('{broken')
    a = AdaptiveResources(file, profile())
    assert a.mode() == 'balanced'
    with pytest.raises(ValueError):
        a.set_mode('dangerous')
    assert a.mode() == 'balanced'
    assert file.read_text() == '{broken'


def test_adaptive_security_scanning_has_stable_order_and_no_source_leak(tmp_path, monkeypatch):
    (tmp_path / 'a.py').write_text('eval("unsafe")\n')
    (tmp_path / 'b.py').write_text('x=2\n')
    (tmp_path / 'c.ts').write_text('eval(userInput)\n')
    (tmp_path / '.env').write_text('private=secret\n')
    a = AdaptiveResources(tmp_path / '.barq' / 'governor.json', profile(cpu=8))
    a.set_mode('performance')
    monkeypatch.setattr(security_monitor, 'adaptive_resources', a)
    result = security_monitor.scan_project(str(tmp_path))
    assert result['checked'] == 3
    assert result['scan_workers'] == 8  # hardware's maximum; three files are actually submitted
    assert result['adaptive_mode'] == 'performance'
    assert result['summary']['high'] >= 2
    assert '.env' not in repr(result)
    a.set_mode('eco')
    result2 = security_monitor.scan_project(str(tmp_path))
    assert result2['scan_workers'] == 1
    assert [f['id'] for f in result['findings']] == [f['id'] for f in result2['findings']]


def test_api_modes_are_local_and_validated(monkeypatch, tmp_path):
    from api import app
    import api
    local = AdaptiveResources(tmp_path/'policy.json', profile(cpu=4))
    monkeypatch.setattr(api, 'adaptive_resources', local)
    client = TestClient(app)
    result = client.get('/v1/system/resources')
    assert result.status_code == 200
    assert result.json()['limits']['mode'] == 'balanced'
    assert result.json()['hardware']['logical_cpu_cores'] == 4
    updated = client.post('/v1/system/resources/mode', json={'mode': 'eco'})
    assert updated.status_code == 200
    assert updated.json()['limits']['scan_workers'] == 1
    assert client.post('/v1/system/resources/mode', json={'mode':'root'}).status_code == 422
    assert local.mode() == 'eco'


@pytest.mark.asyncio
async def test_brain_route_uses_adaptive_context_and_no_extra_model_call(monkeypatch, tmp_path):
    import brain.coordinator as coordinator
    governor = AdaptiveResources(tmp_path/'brain-mode.json', profile(cpu=2))
    governor.set_mode('eco')
    monkeypatch.setattr(coordinator, 'adaptive_resources', governor)
    observed = {}
    async def fake_understand(*args, **kwargs):
        observed.update(kwargs)
        return {'intent': {'kind': 'chat'}, 'reply': 'ok'}
    monkeypatch.setattr(coordinator, 'understand', fake_understand)
    mock = SimpleNamespace(run=AsyncMock())
    brain = Brain(mock, TaskStore(tmp_path/'tasks.sqlite'))
    history = [{'role':'user','content':f'question{i}'} for i in range(11)]
    await brain.route(history,conversation_id='adaptive-test',workspace=str(tmp_path))
    assert len(observed['context']) <= 4
    mock.run.assert_not_called()
