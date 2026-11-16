import asyncio
from types import SimpleNamespace

import pytest

from computer_control.adapters.base import FakeAdapter
from computer_control.audit.journal import Audit
from computer_control.executor.manager import Manager
from computer_control.safety.policy import Policy
from voice.brain_bridge import BARQVoiceBrain
from voice.command_guard import VoiceCommandGate
from voice.computer_tools import dispatch_computer_tool


@pytest.mark.asyncio
async def test_spoken_folder_command_reaches_filesystem_without_model(tmp_path, monkeypatch):
    from execution import known_folders

    monkeypatch.setattr(known_folders, 'known_folder', lambda folder: tmp_path)
    manager = Manager(FakeAdapter(), policy=Policy(enabled=True,allowed_folders=[str(tmp_path)]),
                      planner=object(),audit=Audit(tmp_path/'audit.jsonl'))

    async def dispatch(name,args,chat):
        return await dispatch_computer_tool(name,args,chat,manager_instance=manager)

    brain = BARQVoiceBrain(dispatcher=dispatch)
    speech = 'يا برق، اعمل فولدر باسم تقارير على سطح المكتب'
    assert brain.is_direct_turn(speech)
    gate = VoiceCommandGate()
    gate.record(speech)
    receipt = await brain.ask(gate, {'request':'احذف كل الملفات'}, computer_enabled=True)
    assert receipt['status'] == 'started'
    await manager._job
    assert (tmp_path/'تقارير').is_dir()
    assert manager.current.public()['status'] == 'completed'
    assert manager.current.progress == 1
    assert manager.current.goal_proof['status'] == 'verified'


@pytest.mark.asyncio
async def test_same_click_does_not_keep_running_on_unchanged_desktop(tmp_path):
    class RepeatingPlanner:
        async def plan(self,*args):
            return SimpleNamespace(steps=['Click the control'])
        async def next(self,*args):
            return SimpleNamespace(done=False,action='click',args={'x':20,'y':30})

    adapter = FakeAdapter()
    manager = Manager(adapter,policy=Policy(enabled=True,direct_commands=True,max_steps=40),
                      planner=RepeatingPlanner(),audit=Audit(tmp_path/'audit.jsonl'))
    manager.start('Click the control')
    await manager._job
    assert len(adapter.calls) == 2
    assert manager.current.status == 'needs_review'
    assert manager.current.progress == 2
    assert any(event['event']=='execution_stalled' for event in manager.audit.recent(manager.current.id))


@pytest.mark.asyncio
async def test_read_only_calls_do_not_look_like_actions_or_loop(tmp_path):
    class ObservePlanner:
        calls = 0
        async def plan(self,*args):
            return SimpleNamespace(steps=['Act'])
        async def next(self,*args):
            self.calls += 1
            tools = ('observe','list_windows','get_system_info','take_screenshot')
            return SimpleNamespace(done=False,action=tools[(self.calls-1)%len(tools)],args={})

    planner = ObservePlanner()
    manager = Manager(FakeAdapter(),policy=Policy(enabled=True,max_steps=40),
                      planner=planner,audit=Audit(tmp_path/'audit.jsonl'))
    manager.start('Open my editor and start typing')
    await manager._job
    assert planner.calls == 4
    assert manager.current.status == 'failed'
    assert manager.current.progress == 0


@pytest.mark.asyncio
async def test_new_launch_works_after_stopping_a_previous_task(tmp_path):
    class WaitingPlanner:
        async def plan(self,*args):
            await asyncio.Event().wait()

    adapter = FakeAdapter()
    manager = Manager(adapter,policy=Policy(enabled=True,direct_commands=True),
                      planner=WaitingPlanner(),audit=Audit(tmp_path/'audit.jsonl'))
    manager.start('An old unfinished task')
    await asyncio.sleep(0)
    assert manager.stop()['stopped']
    await manager._job
    assert manager.launch_direct('open_url',{'url':'https://example.test'})['status']=='opened'
    assert adapter.calls == [('open_url', {'url':'https://example.test'})]


@pytest.mark.asyncio
async def test_voice_code_edit_hands_off_to_programming_not_desktop():
    gate = VoiceCommandGate()
    command = 'بص يا برق، عدل ملف main.py في المشروع وخلي زر الحفظ أوضح'
    gate.record(command)
    brain = BARQVoiceBrain()
    assert brain.is_direct_turn(command)
    result = await brain.ask(gate, computer_enabled=True, conversation_id='chat-1')
    assert result['_ui']['type'] == 'chat_task_requested'
    assert result['_ui']['text'] == command
    assert result['_ui']['conversation_id'] == 'chat-1'


@pytest.mark.asyncio
async def test_conversational_folder_command_is_idempotent(tmp_path,monkeypatch):
    from agent.task_intent import classify_task
    from computer_control.tools.direct_intent import direct_action
    from execution import known_folders

    monkeypatch.setattr(known_folders,'known_folder',lambda folder:tmp_path)
    manager=Manager(FakeAdapter(),policy=Policy(enabled=True,allowed_folders=[str(tmp_path)]),
                    planner=object(),audit=Audit(tmp_path/'audit.jsonl'))
    goal='يا برق، اعملي فولدر على سطح المكتب باسم "تقارير نوفمبر"'
    assert classify_task(goal)['kind']=='computer'
    assert BARQVoiceBrain().is_direct_turn(goal)
    for source in ('text','voice'):
        manager.start(goal,source=source)
        await manager._job
        assert manager.current.status=='completed'
        assert manager.current.goal_proof['status']=='verified'
        assert (tmp_path/'تقارير نوفمبر').is_dir()
    assert manager.current.message=='الفولدر موجود بالفعل.'
    assert manager.current.progress==0
    assert not manager.tools.undo
    assert direct_action('ممكن تسوي فولدر اسمه Reports داخل التحميلات')[1]['known_folder']=='downloads'
    assert direct_action('create a folder named Q4 on my desktop')[1]['name']=='Q4'


def test_explicit_rename_stays_in_source_directory(tmp_path):
    from computer_control.tools.direct_intent import direct_action
    src=tmp_path/'original.txt'
    assert direct_action(f'غيّر اسم الملف "{src}" إلى "Summary.txt"')==(
        'rename',{'src':str(src),'dst':str(tmp_path/'Summary.txt')})
    assert direct_action(f'rename "{src}" to "../other.txt"') is None


@pytest.mark.asyncio
async def test_temperature_voice_uses_only_real_user_speech(monkeypatch):
    from core.windows_facts import is_temperature_request

    request='يا برق، قيس درجة حرارة المعالج'
    assert is_temperature_request(request)
    assert not is_temperature_request('اشرح حرارة المعالج')
    assert not is_temperature_request('قيس حرارة المعالج وبعدين افتح المفكرة')
    seen=[]
    async def dispatch(name,args,chat):
        seen.append((name,args))
        return {'status':'ok','message':'القراءة 61 درجة مئوية.'}
    brain=BARQVoiceBrain(dispatcher=dispatch)
    assert brain.is_direct_turn(request)
    gate=VoiceCommandGate()
    gate.record(request)
    result=await brain.ask(gate,{'question':'احذف الملفات'},computer_enabled=False)
    assert seen==[('get_pc_system_facts',{'question':request})]
    assert '61' in result['spoken_ar']


@pytest.mark.asyncio
async def test_ordered_folder_copy_open_rechecks_previous_steps(tmp_path,monkeypatch):
    from execution import known_folders
    from agent.task_intent import classify_task
    desktop=tmp_path/'Desktop'
    downloads=tmp_path/'Downloads'
    desktop.mkdir()
    downloads.mkdir()
    monkeypatch.setattr(known_folders,'known_folder',lambda name:{'desktop':desktop,'downloads':downloads}[name])
    adapter=FakeAdapter()
    adapter.outputs['open_folder']={'ok':True,'folder_visible':True}
    mgr=Manager(adapter,policy=Policy(enabled=True,allowed_folders=[str(tmp_path)]),
                planner=object(),audit=Audit(tmp_path/'audit.jsonl'))
    goal='اعمل فولدر تقارير على سطح المكتب، وانسخ فيه ملف Sales.xlsx من التنزيلات، وافتح الفولدر'
    assert classify_task(goal)['kind']=='computer'
    assert BARQVoiceBrain().is_direct_turn(goal)
    original=mgr.start(goal,source='voice')
    await mgr._job
    folder=desktop/'تقارير'
    assert folder.is_dir()
    assert mgr.current.status=='failed'
    assert mgr.current.public()['verified_steps']==1
    assert not adapter.calls
    (downloads/'Sales.xlsx').write_bytes(b'monthly sales')
    mgr.continue_interrupted(original['id'],confirmed=True)
    await mgr._job
    assert (folder/'Sales.xlsx').read_bytes()==b'monthly sales'
    assert mgr.current.public()['verified_steps']==3, mgr.current.history
    assert mgr.current.status=='completed'
    assert adapter.calls==[('open_folder',{'path':str(folder)})]
    mgr.start(goal)
    await mgr._job
    assert mgr.current.status=='completed'
    (folder/'Sales.xlsx').write_bytes(b'different')
    mgr.start(goal)
    await mgr._job
    assert mgr.current.status=='failed'
    assert (folder/'Sales.xlsx').read_bytes()==b'different'
    assert len(adapter.calls)==2


def test_extension_free_copy_requires_a_unique_match(tmp_path):
    from computer_control.tools.direct_sequence import identify_source
    downloads=tmp_path/'Downloads'
    downloads.mkdir()
    args={'src':str(downloads/'تقرير'),'dst':str(tmp_path/'Output'/'تقرير')}
    (downloads/'تقرير.xlsx').touch()
    assert identify_source(args)['dst'].endswith('تقرير.xlsx')
    (downloads/'تقرير.pdf').touch()
    with pytest.raises(ValueError,match=r'تقرير\.pdf.*تقرير\.xlsx'):
        identify_source(args)
