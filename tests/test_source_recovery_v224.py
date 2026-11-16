import json
import httpx
import pytest
from coding.source_context import fit_source_messages
from mission.engine import seed_manifest, propose_next_source
from mission.tracking import start, load_project
from router.config import Config, Provider, Model
from router.engine import Engine
from brain.live_code import LiveCode
from tests.test_v219_command_intake import controlled_http


def test_large_source_context_preserves_goal_and_target():
    data={'goal':'Build the requested calendar','target':'app/main.py',
          'committed_files':[{'path':'app/storage.py','symbols':['load','save'],'source':'x'*24000}],
          'current_source':'y'*16000}
    messages=[{'role':'system','content':'Contract. PROJECT DATA: '+json.dumps(data)}]
    result=fit_source_messages(messages,4096)
    assert len(result[0]['content'].encode()) <= 6144
    sent=json.loads(result[0]['content'].split('PROJECT DATA: ')[1])
    assert sent['goal']==data['goal'] and sent['target']==data['target']
    assert sent['committed_files'][0]['symbols']==['load','save']
    assert len(data['current_source'])==16000


def test_oversized_mandatory_goal_is_not_silently_cut():
    messages=[{'role':'system','content':'PROJECT DATA: '+json.dumps({'goal':'x'*10000})}]
    with pytest.raises(ValueError,match='larger context'):
        fit_source_messages(messages,2048)


@pytest.mark.asyncio
@pytest.mark.parametrize('stream,truncated',[(False,False),(True,False),(True,True),(False,True)])
async def test_actual_engine_repairs_rejected_source_before_proposing_save(tmp_path,monkeypatch,stream,truncated):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'state'))
    root=tmp_path/'workspace';(root/'app').mkdir(parents=True)
    start(str(root),'app','desktop_python','Build a settings application',['main.py'])
    seed_manifest(str(root),'app')
    engine=Engine(Config(providers=[Provider(name='ollama',kind='local',base_url='http://127.0.0.1:11434/v1',
        models=[Model(name='qwen3:4b',strengths=['coding'],context_window=32768)])]),cache_path=str(tmp_path/'cache.db'))
    calls=[]
    broken='### FILE: app/storage.py\n```python\ndef load(:\n    return {}\n```'
    fixed='### FILE: app/storage.py\n```python\ndef load():\n    return {}\n```'
    def respond(request):
        if request.url.path=='/api/tags':return httpx.Response(200,json={'models':[{'name':'qwen3:4b'}]})
        payload=json.loads(request.content);calls.append(payload)
        if len(calls)==2:
            prompt=payload['messages'][0]['content']
            assert 'rejected_source' in prompt and 'def load(:' in prompt and 'repair_error' in prompt
        content=broken if len(calls)==1 else fixed
        data={'message':{'content':content},'done':True,'done_reason':'length' if truncated and len(calls)==1 else 'stop'}
        if payload['stream']:
            return httpx.Response(200,headers={'content-type':'application/x-ndjson'},text=json.dumps(data)+'\n')
        return httpx.Response(200,json=data)
    controlled_http(monkeypatch,respond)
    if stream:
        with LiveCode().observe('recovery',str(root)):
            result=await propose_next_source(engine,str(root),'app','ollama/qwen3:4b')
    else:result=await propose_next_source(engine,str(root),'app','ollama/qwen3:4b')
    if len(calls)!=2:
        state=load_project(str(root),'app')
        raise AssertionError('Expected initial generation and one repair; '
                             f'actual_requests={len(calls)}, result={result!r}, '
                             f'file_diagnostic={state["manifest"][0].get("last_error")!r}')
    assert result[0]['args']['content']=='def load():\n    return {}\n'
    assert not (root/'app/storage.py').exists()
    assert load_project(str(root),'app')['manifest'][0]['status']=='writing'


@pytest.mark.asyncio
async def test_last_budget_slot_does_not_start_second_attempt(tmp_path,monkeypatch):
    from mission.state import MissionStore
    from core.paths import state_file
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'state'))
    root=tmp_path/'workspace';(root/'app').mkdir(parents=True)
    start(str(root),'app','desktop_python','Build an app',['main.py'])
    mission=seed_manifest(str(root),'app')
    mission['calls_used']=mission['call_budget']-1
    MissionStore(state_file('missions')).save(mission)
    class Broken:
        calls=0
        async def run(self,*args,**kwargs):
            self.calls+=1
            raise ValueError('Invalid source')
    engine=Broken()
    assert await propose_next_source(engine,str(root),'app') is None
    assert engine.calls==1
    after=load_project(str(root),'app')
    assert after['calls_used']==after['call_budget']
