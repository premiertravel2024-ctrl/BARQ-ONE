import asyncio,json
from types import SimpleNamespace
from pathlib import Path
import httpx,pytest
from brain.live_code import LiveCode,Draft,partial_json,ACTIVE
from tests.test_v219_command_intake import actual_engine,controlled_http


@pytest.mark.parametrize('tool,key',[('workspace_edit','content'),('code_replace','after')])
def test_partial_plan_strings_decode_only_real_received_code(tool,key):
    source='print("hello")\n# مصر 😀\\tail\n'
    text=json.dumps({'steps':[{'tool':tool,'args':{'path':'main.py',key:source}}]})
    draft=Draft('/project');draft.begin('local/test')
    for char in text:
        draft.append(char);view=draft.public()
        assert source.startswith(view['code'])
        assert view['validated'] is False
    assert draft.public()['code']==source
    draft.finish(True);assert draft.public()['validated']
    draft.begin('other/test');assert draft.public()['code']==''
    draft.append(text[:60]);draft.finish(False);assert draft.public()['code']==''


@pytest.mark.asyncio
async def test_real_engine_exposes_code_before_stream_done_without_writes(actual_engine,monkeypatch,tmp_path):
    from agent import orchestrator
    gate=asyncio.Event();arrived=asyncio.Event();tracker=LiveCode()
    prefix='{"steps":[{"tool":"workspace_edit","args":{"path":"new.py","content":"def hello():\\n'
    suffix='    return 42\\n"}}],"reason":"Implement requested function","answer":"Review"}'
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield ('data: '+json.dumps({'choices':[{'delta':{'content':prefix}}]})+'\n\n').encode()
            arrived.set();await gate.wait()
            yield ('data: '+json.dumps({'choices':[{'delta':{'content':suffix}}]})+'\n\ndata: [DONE]\n\n').encode()
    def response(request):
        assert json.loads(request.content)['stream'] is True
        return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Stream())
    controlled_http(monkeypatch,response)
    async def generate():
        with tracker.observe('c',str(tmp_path)):
            return await orchestrator.plan(actual_engine,str(tmp_path),[{'role':'user','content':'Create hello function'}])
    task=asyncio.create_task(generate());await asyncio.wait_for(arrived.wait(),2)
    await asyncio.sleep(0)
    draft=tracker.view('c',str(tmp_path));assert draft['code']=='def hello():\n' and not draft['validated']
    assert not task.done() and not (tmp_path/'new.py').exists()
    assert tracker.view('c',str(tmp_path/'other')) is None
    gate.set();result=await task
    assert tracker.view('c',str(tmp_path))['validated']
    assert not (tmp_path/'new.py').exists()
    orchestrator.PENDING.pop(result['plan_id'],None)
    assert ACTIVE.get() is None


@pytest.mark.asyncio
async def test_cancel_discards_unvalidated_partial_draft(tmp_path):
    tracker=LiveCode();arrived=asyncio.Event()
    async def generate():
        with tracker.observe('c',str(tmp_path)):
            observer=ACTIVE.get();observer.begin('test');observer.append('{"steps":[{"tool":"workspace_edit","args":{"content":"partial')
            arrived.set();await asyncio.Event().wait()
    task=asyncio.create_task(generate());await arrived.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    view=tracker.view('c',str(tmp_path));assert view['status']=='interrupted' and not view['code']


def test_background_windows_git_and_gpu_hide_consoles(tmp_path,monkeypatch):
    import core.processes as processes
    import core.adaptive_resources as hardware
    import studio.project as project
    assert processes.background_options()=={} if processes.sys.platform!='win32' else True
    monkeypatch.setattr(processes,'sys',SimpleNamespace(platform='win32'))
    monkeypatch.setattr(__import__('subprocess'),'CREATE_NO_WINDOW',0x08000000,raising=False)
    calls=[]
    def run(*args,**kwargs):
        calls.append(kwargs);return SimpleNamespace(returncode=0,stdout='## main\n' if args[0][0]=='git' else 'GPU, 4096\n')
    monkeypatch.setattr(project.subprocess,'run',run)
    monkeypatch.setattr(hardware.shutil,'which',lambda _: 'nvidia-smi')
    assert project.git_info(str(tmp_path))['available']
    assert hardware._gpu_devices()[0]['vram_mb']==4096
    assert len(calls)==2 and all(item['creationflags']&0x08000000 for item in calls)


@pytest.mark.asyncio
async def test_approved_test_process_is_hidden_but_returns_real_output(tmp_path,monkeypatch):
    import core.processes as processes
    import tools.registry as registry
    (tmp_path/'tests').mkdir();calls=[]
    monkeypatch.setattr(processes,'sys',SimpleNamespace(platform='win32'))
    monkeypatch.setattr(__import__('subprocess'),'CREATE_NO_WINDOW',0x08000000,raising=False)
    class Process:
        returncode=0
        async def communicate(self):return b'1 passed',b''
    async def launch(*args,**kwargs):calls.append(kwargs);return Process()
    monkeypatch.setattr(registry.asyncio,'create_subprocess_exec',launch)
    with pytest.raises(ValueError):await registry.execute('project_tests',str(tmp_path),False)
    result=await registry.execute('project_tests',str(tmp_path),True)
    assert len(calls)==1 and calls[0]['creationflags']&0x08000000
    assert result['stdout']=='1 passed' and result['exit_code']==0
