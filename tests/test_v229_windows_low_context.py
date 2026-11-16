"""Windows low-free-RAM regression: model may run at num_ctx=2048.

Reproduces the original five failures without live Ollama or network.
"""
import json
import pytest
from coding.source_context import fit_source_messages
from tests import test_source_recovery_v224 as recovery_tests
from tests import test_v222_source_mission as stream_tests


@pytest.mark.asyncio
@pytest.mark.parametrize('stream,truncated',[(False,False),(True,False),(True,True),(False,True)])
async def test_engine_repair_reaches_local_model_under_windows_low_memory(
    tmp_path, monkeypatch, stream, truncated,
):
    monkeypatch.setattr('core.adaptive_resources.resources.ollama_context', lambda model=None: 2048)
    await recovery_tests.test_actual_engine_repairs_rejected_source_before_proposing_save(
        tmp_path, monkeypatch, stream, truncated,
    )


@pytest.mark.asyncio
async def test_live_source_stream_starts_under_windows_low_memory(tmp_path, monkeypatch):
    monkeypatch.setattr('core.adaptive_resources.resources.ollama_context', lambda model=None: 2048)
    await stream_tests.test_file_reply_accepted_and_streamed_by_real_pinned_ollama(tmp_path, monkeypatch)


def test_source_compaction_preserves_goal_target_repair_and_security():
    goal = 'User requested branded custom settings UI with saved preferences'
    content = ('You are BARQ AI implementing a real user-requested application. '
               'Return only the fixed source. ' * 45)
    data = {
        'goal': goal,
        'target':'app/storage.py',
        'purpose':'Persistent storage',
        'requirements':[{'id':'required','files':['storage.py']}],
        'ui_contract': {'layout':'Detailed UI requirements' * 50},
        'manifest':[{'path':'app/storage.py','purpose':'Source details'*30}],
        'rejected_source':'def load(:\n    return {}',
        'repair_error':'SyntaxError: invalid syntax',
    }
    sent = fit_source_messages([{'role':'system','content':content+' PROJECT DATA: '+json.dumps(data)}],2048)[0]['content']
    prefix,raw=sent.split('PROJECT DATA: ',1)
    result=json.loads(raw)
    assert len(sent.encode('utf-8')) <= 3072
    assert result['goal']==goal and result['target']=='app/storage.py'
    assert result['requirements']==data['requirements']
    assert result['repair_error']==data['repair_error']
    assert result['rejected_source']==data['rejected_source']
    assert 'no JSON' in prefix and 'untrusted' in prefix


def test_unfit_mandatory_goal_still_rejected_not_truncated():
    content='You are BARQ AI implementing a real user-requested application. PROJECT DATA: '
    with pytest.raises(ValueError, match='Source context too small'):
        fit_source_messages([{'role':'system','content':content+json.dumps({'goal':'X'*6000,'target':'app/main.py'})}],2048)
