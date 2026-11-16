"""Regression tests for curated developer APIs, weather and Gemini Live isolation."""
import json
import pytest
from services import public_hub as h
from voice import public_tools
from coding import dependency_intelligence as dev

@pytest.fixture(autouse=True)
def clean_cache():
    h._cache.clear()
    yield
    h._cache.clear()


def test_pypi_package_metadata(monkeypatch):
    called=[]
    def fetch(host,path,params=None,accept='application/json'):
        called.append((host,path))
        return {'info':{'name':'fastapi','version':'0.117.0','summary':'API framework','requires_python':'>=3.10'}}
    monkeypatch.setattr(h,'_request',fetch)
    result=h.lookup('pypi','fastapi')
    assert result['data']['latest_version']=='0.117.0'
    assert called==[('pypi.org','/pypi/fastapi/json')]
    h.lookup('pypi','fastapi')
    assert len(called)==1  # avoids poll spam and rate limits


def test_npm_package_no_full_history(monkeypatch):
    def fetch(host,path,params=None,accept='application/json'):
        assert host=='registry.npmjs.org' and path=='/%40scope%2Fname/latest'
        return {'name':'@scope/name','version':'2.1.0','license':'MIT','deprecated':'not maintained'}
    monkeypatch.setattr(h,'_request',fetch)
    result=h.lookup('npm','@scope/name')
    assert result['data']['deprecated']=='not maintained'
    assert 'تنبيه' in h.describe(result)


def test_github_repo_public_metadata(monkeypatch):
    monkeypatch.setattr(h,'_request', lambda host,path,params=None,accept='application/json':
                        {'description':'Tools','default_branch':'main','language':'Python',
                         'stargazers_count':120,'open_issues_count':3,'archived':False})
    assert h.lookup('github','public-apis/public-apis')['data']['stars']==120
    assert h.lookup('github','public-apis/public-apis')['data']['url'].startswith('https://github.com/')


def test_no_ssrf_or_install_commands(monkeypatch):
    monkeypatch.setattr(h,'_request', lambda *a,**k:pytest.fail('network must not happen'))
    for provider,target in [('github','localhost:8888'),('github','../foo'),('pypi','http://127.0.0.1'),
                            ('npm','foo; rm -rf /'),('weather','https://example.com'),('random','foo')]:
        assert h.lookup(provider,target)['status']!='ok'


def test_weather_requires_city_no_geolocation(monkeypatch):
    calls=[]
    def fetch(host,path,params=None,accept='application/json'):
        calls.append((host,params))
        if host=='geocoding-api.open-meteo.com':
            return {'results':[{'name':'الرياض','country':'Saudi Arabia','latitude':24.7,'longitude':46.6}]}
        return {'current':{'temperature_2m':27.5,'relative_humidity_2m':45,'wind_speed_10m':11,'time':'2026-10-31T15:00'}}
    monkeypatch.setattr(h,'_request',fetch)
    r=h.lookup('weather','Riyadh')
    assert r['data']['temperature_c']==27.5
    assert 'non-commercial' in r['data']['notice']
    assert all('target' not in (params or {}) for _,params in calls)
    assert 'جهاز' not in h.describe(r)


@pytest.mark.asyncio
async def test_voice_public_tool_no_desktop_permission(monkeypatch):
    monkeypatch.setattr(public_tools,'lookup',lambda provider,target:
                        {'status':'ok','data':{'provider':'PyPI','name':target,'latest_version':'2.3.4','summary':'ok','python_requires':'>=3.10'}})
    response=await public_tools.dispatch_public_tool('lookup_public_information',{'provider':'pypi','target':'requests'})
    assert response['status']=='ok' and '2.3.4' in response['message']
    names={tool['name'] for tool in public_tools.LIVE_PUBLIC_TOOLS[0]['function_declarations']}
    assert names=={'lookup_public_information','search_google','search_public_web'}
    assert 'start_computer_task' not in names


def test_public_tools_in_live_without_computer():
    from voice.live import live_system_instruction, LIVE_PUBLIC_TOOLS, LIVE_COMPUTER_TOOLS
    assert 'lookup_public_information' in str(LIVE_PUBLIC_TOOLS)
    assert 'public read-only' in live_system_instruction(False)
    assert 'start_computer_task' not in live_system_instruction(False)
    assert LIVE_COMPUTER_TOOLS


def test_dependency_scan_read_only_offline(tmp_path, monkeypatch):
    (tmp_path/'requirements.txt').write_text('requests==2.32.3\n-e git+https://bad.example/repo\nfastapi>=0.115\n-r nested.txt\n',encoding='utf8')
    (tmp_path/'package.json').write_text(json.dumps({'dependencies':{'react':'^18','@types/react':'^18','bad;run':'1'}}))
    monkeypatch.setattr(dev,'lookup',lambda *a:pytest.fail('offline scan must not fetch'))
    result=dev.scan(str(tmp_path))
    assert [x['package'] for x in result['packages']]==['requests','fastapi','react','@types/react']
    assert result['read_only'] and result['online_checks']==0


def test_dependency_scan_online_explicit_max_five(tmp_path, monkeypatch):
    (tmp_path/'package.json').write_text(json.dumps({'dependencies':{f'lib{i}':'^1.0' for i in range(8)}}))
    called=[]
    def fake(p,n):
        called.append((p,n))
        return {'status':'ok','data':{'latest_version':'1.2.3'}}
    monkeypatch.setattr(dev,'lookup',fake)
    result=dev.scan(str(tmp_path),verify_latest=True)
    assert len(called)==5 and result['packages'][0]['latest']=='1.2.3'
    assert 'latest' not in result['packages'][-1]


def test_natural_language_metadata_only():
    assert h.match_explicit_programming_question('ما هو آخر إصدار python requests?') == ('pypi','requests')
    assert h.match_explicit_programming_question('معلومات GitHub public-apis/public-apis') == ('github','public-apis/public-apis')
    assert h.match_explicit_programming_question('اصنعلي تطبيق Python باستخدام requests') is None
    assert h.match_explicit_programming_question('حرارة المعالج كام') is None


def test_http_endpoints_are_readonly_and_available(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import api
    monkeypatch.setattr(h,'_request', lambda host,path,params=None,accept='application/json':
                        {'info':{'name':'pytest','version':'9.0.0','summary':'Testing','requires_python':'>=3.10'}})
    (tmp_path/'requirements.txt').write_text('pytest>=8',encoding='utf8')
    with TestClient(api.app) as client:
        catalog=client.get('/v1/developer/public-api/catalog')
        assert catalog.status_code==200 and len(catalog.json()['providers'])==4
        result=client.get('/v1/developer/public-api/lookup',params={'provider':'pypi','target':'pytest'})
        assert result.status_code==200 and result.json()['data']['latest_version']=='9.0.0'
        deps=client.get('/v1/coding/dependencies',params={'workspace':str(tmp_path)})
        assert deps.status_code==200 and deps.json()['packages'][0]['package']=='pytest'
    # No code or installation happens simply from querying dependency metadata.
    assert not (tmp_path/'.venv').exists()
