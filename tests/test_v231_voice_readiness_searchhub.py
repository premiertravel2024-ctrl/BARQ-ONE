"""Phase 3 readiness and Phase 2 search: deterministic, offline-only fakes."""
import pytest
from voice.readiness import report,self_test
from voice.search_hub import SearchHub, classify_scope
from voice.brain_bridge import BARQVoiceBrain
from voice.command_guard import VoiceCommandGate


@pytest.mark.parametrize('missing',[
    'windows','computer_control','voice_permission','gemini',
    'microphone','local_planner','device_index','windows_mcp'])
def test_each_capability_has_an_exact_local_reason_and_fix(missing):
    probes={k:True for k in ('windows','computer_control','voice_permission','gemini','microphone','local_planner','device_index','windows_mcp')}
    probes[missing]=False
    value=report(probes=probes)
    entry=next(x for x in value['capabilities'] if x['id']==missing)
    assert entry['state']=='blocked' and len(entry['reason'])>15
    assert entry['fix'] and value['status']=='needs_setup'
    assert not value['local_stt_ready']


def test_readiness_all_settings_are_not_real_device_evidence():
    values={k:True for k in ('windows','computer_control','voice_permission','gemini','microphone','local_planner','device_index','windows_mcp')}
    value=report(probes=values)
    assert value['status']=='ready'
    assert 'لا يتحقق' in value['note']


def test_safe_selftest_reports_missing_index_without_fake_success():
    probe=self_test(facts=lambda _:None,search=lambda query,**kw:{'results':[]})
    assert probe['passed']==1
    assert 'device_index_temp' in probe['not_verified']
    assert 'system_facts' in probe['not_verified']


@pytest.mark.asyncio
async def test_searchhub_web_never_receives_private_data():
    web_calls=[]
    async def web(query,scope):web_calls.append(query);return {'status':'ok','results':[]}
    hub=SearchHub()
    value=await hub.search('search my password API_KEY',scope='web',computer_enabled=True,web_dispatch=web)
    assert value['status']=='denied' and not web_calls
    value=await hub.search('دور على أحدث أخبار Python',computer_enabled=False,web_dispatch=web)
    assert value['status']=='ok' and len(web_calls)==1


@pytest.mark.asyncio
async def test_voice_computer_permission_does_not_equal_search_public_permission():
    async def failure(*a):raise AssertionError('Must not run computer tool')
    brain=BARQVoiceBrain(dispatcher=failure)
    gate=VoiceCommandGate();gate.record('افتح المفكرة')
    assert (await brain.ask(gate,computer_enabled=False))['status']=='permission_required'


def test_scope_never_confuses_cpu_temperature_with_outdoor_weather():
    assert classify_scope('حرارة المعالج كام')=='facts'
    assert classify_scope('درجة حرارة الجو في القاهرة')=='weather'
