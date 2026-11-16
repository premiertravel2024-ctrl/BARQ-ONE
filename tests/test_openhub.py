from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api_routes import openhub


@pytest.fixture
def client(monkeypatch, tmp_path):
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(openhub.router)
    monkeypatch.setattr(openhub, 'state_file', lambda name: tmp_path / name)
    monkeypatch.setattr(openhub, '_inventory', {})
    monkeypatch.setattr(openhub, '_inventory_checked', False)
    return TestClient(app)


def test_catalog_contains_visual_branch_projects_and_exact_packages(client):
    rows = client.get('/v1/openhub/catalog').json()['items']
    indexed = {row['id']: row for row in rows}
    assert len(rows) == len(indexed) >= 100
    assert indexed['cursortouch/windows-mcp']['package'] is None
    assert indexed['blender/blender']['package'] == 'BlenderFoundation.Blender'
    assert all(item['url'].startswith('https://github.com/') for item in rows)


def test_openhub_only_runs_confirmed_exact_packages_and_verifies_install(client, monkeypatch):
    calls = []

    def execute(command, args, timeout):
        calls.append((command, args))
        if args[0] == 'export':
            Path(args[2]).write_text('{"Sources":[{"Packages":[{"PackageIdentifier":"Git.Git","Version":"2.52.0"},{"PackageIdentifier":"Private.Tool","Version":"9"}]}]}')
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(openhub, 'winget', lambda: 'winget.exe')
    monkeypatch.setattr(openhub, 'run_winget', execute)
    monkeypatch.setattr(openhub, 'submit_jobs', lambda jobs: [openhub.run_job(*args) for args in jobs])
    assert client.post('/v1/openhub/jobs', json={'items':['git/git'],'action':'install'}).status_code == 403
    assert client.post('/v1/openhub/jobs', json={'items':['not-an-entry'],'action':'install','confirmed':True}).status_code == 400
    assert calls == []
    payload = {'items':['git/git','git/git'],'action':'install','confirmed':True}
    assert len(client.post('/v1/openhub/jobs', json=payload).json()['queued']) == 1
    assert client.post('/v1/openhub/jobs', json=payload).json()['queued'] == []
    assert [args[0] for _, args in calls] == ['show', 'install', 'export']
    assert calls[1][1][1:6] == ['--id', 'Git.Git', '--exact', '--source', 'winget']
    assert client.get('/v1/openhub/jobs').json()['jobs'][0]['status'] == 'verified'
    assert client.get('/v1/openhub/installed').json()['packages'] == {'git.git':'2.52.0'}


def test_download_checks_the_output_without_launching_an_installer(client, monkeypatch):
    actions = []

    def execute(command, args, timeout):
        actions.append(args[0])
        if args[0] == 'download':
            destination = Path(args[args.index('--download-directory') + 1])
            (destination / 'test.exe').write_bytes(b'mock installer payload')
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(openhub, 'winget', lambda: 'winget.exe')
    monkeypatch.setattr(openhub, 'run_winget', execute)
    monkeypatch.setattr(openhub, 'submit_jobs', lambda jobs: [openhub.run_job(*args) for args in jobs])
    assert client.post('/v1/openhub/jobs', json={'items':['git/git'],'action':'download','confirmed':True}).status_code == 202
    assert actions == ['show','download']
    job = client.get('/v1/openhub/jobs').json()['jobs'][0]
    assert job['status'] == 'verified'
    assert (Path(job['detail']) / 'test.exe').is_file()


def test_source_zip_stays_inside_openhub_without_winget(client, monkeypatch):
    from zipfile import ZipFile

    def source(repository, folder):
        assert repository == 'CursorTouch/Windows-MCP'
        archive = folder / 'source.zip'
        with ZipFile(archive, 'w') as output:
            output.writestr('README.md', 'Sample')
        return archive

    monkeypatch.setattr(openhub, 'winget', lambda: None)
    monkeypatch.setattr(openhub, 'download_source', source)
    monkeypatch.setattr(openhub, 'submit_jobs', lambda jobs: [openhub.run_job(*args) for args in jobs])
    result = client.post('/v1/openhub/jobs', json={'items':['cursortouch/windows-mcp'],'action':'source','confirmed':True})
    job = result.json()['queued'][0]
    downloaded = client.get(f'/v1/openhub/jobs/{job}/file')
    assert downloaded.status_code == 200
    assert downloaded.content.startswith(b'PK')
    assert client.get('/v1/openhub/jobs/not-a-job/file').status_code == 404


def test_tool_command_is_grounded_in_explicit_catalog_request(monkeypatch):
    from api_routes.openhub_tools import CommandRequest, requested_tool, tool_command

    sent = []
    monkeypatch.setattr(openhub, 'enqueue', lambda request: sent.append(request) or {'queued':['test']})
    assert not requested_tool('كيف أثبت Windows-MCP')
    assert not requested_tool('نزل https://example.org/installer.exe')
    assert tool_command(CommandRequest(text='حمّل Windows-MCP'))['status'] == 'queued'
    assert sent[-1].action == 'setup'
    assert tool_command(CommandRequest(text='ثبّت Windows-MCP'))['status'] == 'queued'
    assert sent[-1].action == 'setup'
    assert tool_command(CommandRequest(text='ثبّت FFmpeg'))['status'] == 'queued'
    assert sent[-1].items == ['ffmpeg/ffmpeg']


def test_download_language_installs_without_silent_source_fallback(monkeypatch):
    from api_routes.openhub_tools import CommandRequest, requested_tool, tool_command
    sent = []
    monkeypatch.setattr(openhub, 'enqueue', lambda request: sent.append(request) or {'queued':['test']})
    for phrase in ('نزل LibreHardwareMonitor', 'ممكن تنزل Windows-MCP', 'انا عاوزك تنزل FFmpeg'):
        assert tool_command(CommandRequest(text=phrase))['status'] == 'queued'
        assert sent[-1].action in {'setup', 'install'}
    for phrase in ('متنزلش FFmpeg', 'ازاي انزل FFmpeg', 'نزل FFmpeg وامسح الملفات'):
        assert requested_tool(phrase) is None
    result = tool_command(CommandRequest(text='ثبت LangGraph'))
    assert result['status'] == 'unavailable'
    assert 'وصفة تثبيت' in result['message']


def test_sensor_setup_is_not_source_download(client, monkeypatch):
    from core import hardware_sensors
    statuses = []
    monkeypatch.setattr(openhub, 'job_status', lambda *args: statuses.append(args))
    monkeypatch.setattr(hardware_sensors, 'ensure_sensors_ready', lambda: 'installed')
    openhub.run_job('job', None, 'librehardwaremonitor/librehardwaremonitor', 'setup', None)
    assert statuses[-1][1] == 'verified'
    monkeypatch.setattr(hardware_sensors, 'ensure_sensors_ready', lambda: 'unavailable')
    openhub.run_job('job', None, 'librehardwaremonitor/librehardwaremonitor', 'setup', None)
    assert statuses[-1][1] == 'failed'


def test_sensor_elevation_requires_installed_provider(client, monkeypatch):
    import sys
    from core import hardware_sensors
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(hardware_sensors, '_monitor_executable', lambda: None)
    assert client.post('/v1/openhub/monitor/elevate').status_code == 409


def test_dedicated_setups_appear_in_installed_inventory(client, monkeypatch):
    import sys
    from core import hardware_sensors
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(hardware_sensors, '_monitor_executable', lambda: Path('LibreHardwareMonitor.exe'))
    monkeypatch.setattr(openhub, 'find_tool', lambda name: 'windows-mcp.exe' if name == 'windows-mcp.exe' else None)
    installed = client.get('/v1/openhub/installed').json()
    assert set(installed['setups']) == {'librehardwaremonitor/librehardwaremonitor', 'cursortouch/windows-mcp'}
    assert installed['packages'] == {}


def test_openhub_all_catalog_entries_have_bilingual_explanations():
    from api_routes.openhub import catalog
    entries = catalog()
    assert len(entries) >= 119
    for key, item in entries.items():
        assert item['description_ar'].strip(), key
        assert item['description_en'].strip(), key
        assert len(item['description_ar']) >= 20, key
        assert len(item['description_en']) >= 20, key


def test_openhub_description_api_and_ui_keep_layout_with_rtl():
    from pathlib import Path
    from api_routes.openhub import catalog
    assert catalog()['ollama/ollama']['description_ar'].startswith('تشغيل')
    root = Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'pages'
    tsx = (root / 'BarqOne.tsx').read_text(encoding='utf-8')
    css = (root / 'barqOne.css').read_text(encoding='utf-8')
    assert 'description_ar?:string;description_en?:string' in tsx
    assert 'one-tool-description' in tsx
    assert 'overflow-wrap: anywhere' in css
    assert 'grid-template-columns: repeat(auto-fill,minmax(min(100%,270px),1fr))' in css
