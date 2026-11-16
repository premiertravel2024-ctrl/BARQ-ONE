"""Actual router + native Ollama transport contracts, not a fake Engine.run."""
import asyncio,hashlib,json
from pathlib import Path
import httpx,pytest
from brain.live_code import LiveCode
from router.config import Config,Provider,Model
from router.engine import Engine
from router.quality import acceptable
from mission.engine import seed_manifest,propose_next_source
from mission.tracking import start,mark_saved,load_project
from tests.test_v219_command_intake import controlled_http


@pytest.mark.asyncio
async def test_file_reply_accepted_and_streamed_by_real_pinned_ollama(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'state'))
    monkeypatch.setenv('BARQ_PROVIDER_RETRIES','0')
    root=tmp_path/'workspace';(root/'app').mkdir(parents=True)
    start(str(root),'app','desktop_python','Build a Windows settings application',['main.py'])
    seed_manifest(str(root),'app')
    engine=Engine(Config(providers=[Provider(name='ollama',kind='local',base_url='http://127.0.0.1:11434/v1',
        models=[Model(name='qwen3:4b',context_window=32768,strengths=['coding'])])]),cache_path=str(tmp_path/'cache.db'))
    tracker=LiveCode();sent=asyncio.Event();finish=asyncio.Event();calls=[]
    prefix='### FILE: app/storage.py\n```python\nimport json\n'
    suffix='\ndef load(path):\n    return json.loads(path.read_text()) if path.exists() else {}\n```'
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield (json.dumps({'message':{'content':prefix},'done':False})+'\n').encode()
            sent.set();await finish.wait()
            yield (json.dumps({'message':{'content':suffix},'done':False})+'\n').encode()
            yield b'{"done":true,"done_reason":"stop"}\n'
    def respond(request):
        if request.url.path=='/api/tags':return httpx.Response(200,json={'models':[{'name':'qwen3:4b'}]})
        calls.append(request);payload=json.loads(request.content)
        assert str(request.url)=='http://127.0.0.1:11434/api/chat'
        assert payload['stream'] is True and payload['think'] is False
        assert payload['model']=='qwen3:4b' and payload['options']['num_predict']==8192
        assert 'no JSON' in payload['messages'][0]['content']
        assert not acceptable(prefix+suffix,payload['messages']) # reproduce old failure
        return httpx.Response(200,headers={'content-type':'application/x-ndjson'},stream=Stream())
    controlled_http(monkeypatch,respond)
    async def generate():
        with tracker.observe('mission',str(root)):
            return await propose_next_source(engine,str(root),'app',model='ollama/qwen3:4b')
    task=asyncio.create_task(generate())
    try:
        await asyncio.wait_for(sent.wait(),10)
    except asyncio.TimeoutError:
        state=load_project(str(root),'app')
        task.cancel()
        finish.set()
        await asyncio.gather(task,return_exceptions=True)
        pytest.fail('Pinned local model did not begin streaming within 10 seconds; '
                    f'HTTP_requests={len(calls)}, file_diagnostic={state["manifest"][0].get("last_error")!r}')
    await asyncio.sleep(0)
    view=tracker.view('mission',str(root));assert view['code']=='import json\n'
    assert not view['validated'] and not task.done() and not (root/'app/storage.py').exists()
    finish.set();step,model=await task
    assert step['args']['path']=='app/storage.py' and 'def load(path)' in step['args']['content']
    assert len(calls)==1 and model=='ollama/qwen3:4b'
    assert tracker.view('mission',str(root))['validated']
    assert not (root/'app/storage.py').exists()
    assert load_project(str(root),'app')['manifest'][0]['status']=='writing'


@pytest.mark.parametrize('response',[
    '### FILE: other.py\n```python\nx = 1\n```',
    '```python\nx=1\n```\n```python\ny=2\n```',
    '### FILE: app/main.py\n```python\ndef broken(',
    'Sorry',
])
def test_unusable_source_never_becomes_approved_code(response):
    from coding.source_contract import source_content
    with pytest.raises((ValueError,SyntaxError)):source_content(response,'app/main.py')


@pytest.mark.parametrize('response',['```python\nx=1\n```','x=1\n','<think>private reasoning</think>\n### FILE: app/main.py\n```python\nx=1\n```'])
def test_common_code_formats_accept_only_the_fixed_target(response):
    from coding.source_contract import source_content
    assert source_content(response,'app/main.py')=='x=1\n'


def ready_mission(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'state'))
    root=tmp_path/'workspace';(root/'app').mkdir(parents=True)
    start(str(root),'app','desktop_python','Build Windows EXE',['main.py','test_app.py'])
    for name,source in [('main.py','def total(items):\n    return sum(items)\n'),('test_app.py','from main import total\ndef test_total():\n    assert total([2,3])==5\n')]:
        (root/'app'/name).write_text(source)
        mark_saved(str(root),'app','app/'+name,hashlib.sha256(source.encode()).hexdigest())
    return root


@pytest.mark.asyncio
async def test_real_generated_project_tests_then_build_proposal_and_failure_repair(tmp_path,monkeypatch):
    from mission.validation import next_validation,record_validation,fingerprint,repair_context
    from tools.registry import execute
    root=ready_mission(tmp_path,monkeypatch);workspace=str(root)
    get=lambda:load_project(workspace,'app')
    next_step=lambda:next_validation(workspace,'app',get())
    assert next_step()['steps']==[{'tool':'run_tests','args':{'project':'app'}}]
    before=fingerprint(workspace,'app')
    result=await execute('project_tests',str(root/'app'),confirmed=True)
    assert result['exit_code']==0 and '1 passed' in result['stdout']
    record_validation(workspace,'app',{'tool':'run_tests','success':True,'result':json.dumps(result)},before)
    assert next_step()['steps'][0]['tool']=='project_build'
    record_validation(workspace,'app',{'tool':'project_build','success':False,'error':'Missing PyInstaller'},before)
    assert next_step() is None and 'Missing PyInstaller' in repair_context(workspace,'app',get())
    # A changed source invalidates stale test/build evidence even after a restart.
    (root/'app/main.py').write_text('def total(items):\n    return sum(items)+1\n')
    assert next_step()['steps'][0]['tool']=='run_tests'
    before=fingerprint(workspace,'app');failed=await execute('project_tests',str(root/'app'),confirmed=True)
    assert failed['exit_code']!=0 and 'FAILED' in failed['stdout']
    record_validation(workspace,'app',{'tool':'run_tests','success':False,'result':json.dumps(failed)},before)
    assert next_step() is None # repair is required, never blindly rerun unchanged code
    assert 'assert 6 == 5' in repair_context(workspace,'app',get())
