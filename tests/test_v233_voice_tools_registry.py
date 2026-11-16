"""BARQ voice free public-tool and safety regressions."""
import asyncio
import ast
from pathlib import Path
from voice.utility_tools import calculate,convert
from voice.public_tools import LIVE_PUBLIC_TOOLS,dispatch_public_tool
from services import public_hub


def test_arithmetic_no_dynamic_code():
    assert calculate('(12+18)/3')['result']==10
    assert calculate('12%5')['result']==2
    for code in ('__import__("os").system("echo bad")','2**10000000','1/0','1000000000000000000','(1+2)*'*60):
        assert calculate(code)['status']!='ok'


def test_fixed_unit_conversion():
    assert convert(1,'km','m')['result']==1000
    assert convert(0,'c','f')['result']==32
    assert convert(32,'f','c')['result']==0
    assert convert(1,'kg','m')['status']=='denied'
    assert convert(float('inf'),'kg','g')['status']=='denied'


def test_public_tool_declarations_and_dispatch():
    names={f['name'] for group in LIVE_PUBLIC_TOOLS for f in group['function_declarations']}
    assert {'get_weather_forecast','quick_calculate','convert_units','get_local_datetime','list_voice_capabilities','search_public_web','lookup_public_information'}<=names
    assert asyncio.run(dispatch_public_tool('quick_calculate',{'expression':'100/4'}))['result']==25
    assert asyncio.run(dispatch_public_tool('convert_units',{'value':1,'from_unit':'mi','to_unit':'m'}))['result']==1609.344
    assert asyncio.run(dispatch_public_tool('get_weather_forecast',{'city':r'C:\Users\Secret'}))['status']!='ok'
    assert 'iso_local' in asyncio.run(dispatch_public_tool('get_local_datetime',{}))
    assert 'tools' in asyncio.run(dispatch_public_tool('list_voice_capabilities',{}))['data']


def test_weather_uses_city_not_geolocation_and_has_forecast(monkeypatch):
    calls=[]
    def fake(host,path,params=None,accept='application/json'):
        calls.append((host,path,params))
        if host.startswith('geocoding'):
            return {'results':[{'name':'Riyadh','country':'Saudi Arabia','latitude':24.7,'longitude':46.7}]}
        return {'current':{'temperature_2m':25,'relative_humidity_2m':35,'wind_speed_10m':10,'time':'2026-11-02T10:00'},
          'daily':{'time':['2026-11-02','2026-11-03','2026-11-04'],
                   'temperature_2m_max':[31,32,30], 'temperature_2m_min':[20,21,19],
                   'precipitation_probability_max':[0,10,20],'weather_code':[0,1,3]}}
    monkeypatch.setattr(public_hub,'_request',fake)
    data=public_hub._lookup('weather_forecast','الرياض')
    assert len(data['forecast'])==3
    assert data['forecast'][0]['high_c']==31
    assert calls[1][2]['forecast_days']==3
    assert '31' in public_hub.describe({'status':'ok','data':data})


def test_new_settings_are_distinct_and_voice_model_unchanged():
    base=Path(__file__).resolve().parents[1]
    settings=(base/'frontend/src/components/layout/SettingsModal.tsx').read_text(encoding='utf8')
    voice=(base/'frontend/src/components/layout/VoiceSettings.tsx').read_text(encoding='utf8')
    live=(base/'voice/live.py').read_text(encoding='utf8')
    # The assistant tab now receives navigation so readiness fixes can open the
    # exact control/models settings panel. It is still distinct from calls.
    assert "tab==='assistant'&&<VoiceSettings mode=\"assistant\" onNavigate={setTab}/>" in settings
    assert "tab==='voice'&&<VoiceSettings mode=\"conversation\"/>" in settings
    assert "mode==='assistant'" in voice and 'v1/voice/tools' in voice
    assert "get_weather_forecast" in live
    assert 'gemini-3.8-live' in live
