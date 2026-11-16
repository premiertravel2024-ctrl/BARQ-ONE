"""End-to-end intent with faked Windows/Node/VSCode, no real system actions."""
from pathlib import Path
from types import SimpleNamespace
import json
from execution.grants import GrantStore
from execution.react_mission import ReactMission, is_react_desktop_goal
from computer_control.safety.policy import Mode


def test_egyptian_command_recognized_but_not_conversation():
    assert is_react_desktop_goal('يا برق، افتح VS Code، اعمل مشروع React على الديسكتوب، ثبّت المكتبات وشغّله')
    assert is_react_desktop_goal('انشئ مشروع React على سطح المكتب')
    assert not is_react_desktop_goal('اشرحلي React')
    assert not is_react_desktop_goal('شغل VS Code')


def test_composed_react_mission_requires_grant_before_side_effects(tmp_path,monkeypatch):
    import execution.react_mission as module
    monkeypatch.setattr(module,'sys',SimpleNamespace(platform='win32'))
    monkeypatch.setattr(module,'known_folder',lambda _:tmp_path)
    store=GrantStore(tmp_path.parent/'empty_grants.json')
    monkeypatch.setattr(module,'GrantStore',lambda:store)
    result=ReactMission().start('اعمل مشروع React على الديسكتوب','voice',True,Mode.SMART)
    assert result['status']=='needs_project_grant'
    assert result['executed'] is False
    assert not list(tmp_path.glob('barq-react-*'))


def test_composed_react_mission_fake_build_and_real_scaffold(tmp_path,monkeypatch):
    import execution.react_mission as module
    monkeypatch.setattr(module,'sys',SimpleNamespace(platform='win32'))
    monkeypatch.setattr(module,'known_folder',lambda _:tmp_path)
    store=GrantStore(tmp_path.parent/'grants.json')
    store.grant(str(tmp_path),['read','write','create','install_dependencies','build','run_dev_server'])
    monkeypatch.setattr(module,'GrantStore',lambda:store)
    monkeypatch.setattr(module,'TaskStateStore',lambda:__import__('computer_control.state_store',fromlist=['TaskStateStore']).TaskStateStore(tmp_path.parent/'ledger.sqlite3'))
    def pretend_install(project,grants,runner,*,cancel):
        (project/'node_modules').mkdir()
        (project/'dist').mkdir()
        (project/'dist'/'index.html').write_text('<html>ok</html>')
        return {'status':'verified','build_file':str(project/'dist'/'index.html')}
    def pretend_start(project,grants,services,*,cancel):
        return {'http_status':200,'url':'http://127.0.0.1:5173/','port':5173}
    monkeypatch.setattr(module,'install_and_build',pretend_install)
    monkeypatch.setattr(module,'start_react',pretend_start)
    monkeypatch.setattr(module,'Runner',lambda:SimpleNamespace(validate=lambda _:('code',['code',str(tmp_path)],None)))
    import subprocess,webbrowser
    monkeypatch.setattr(webbrowser,'open',lambda url:True)
    monkeypatch.setattr(subprocess,'Popen',lambda *a,**k:SimpleNamespace(pid=12345))
    # This is a fake Windows/Node/VS Code test. Never enumerate the real
    # desktop during a unit test (UIA may hang or find an unrelated window).
    mission=ReactMission(window_probe=lambda project: False,window_probe_timeout=0.1)
    result=mission.start('اعمل مشروع React على الديسكتوب وشغله','chat',True,Mode.SMART)
    assert result['status']=='running'
    mission._worker.join(timeout=10)
    assert not mission._worker.is_alive(), mission.public()
    final=mission.public()
    assert final['status']=='needs_review', final['message']
    assert [x['status'] for x in final['history']]==['committed','committed','needs_review','committed']
    assert final['goal_proof']['status']=='unverified'  # VS Code window not observed
    project=next(tmp_path.glob('barq-react-*'))
    assert (project/'package.json').is_file()
    assert (project/'dist'/'index.html').is_file()


def test_vscode_window_probe_is_bounded_and_cannot_fake_success(tmp_path,monkeypatch):
    """A stuck Windows UIA probe must not deadlock a React mission."""
    import threading
    import execution.react_mission as module
    monkeypatch.setattr(module,'sys',SimpleNamespace(platform='win32'))
    monkeypatch.setattr(module,'known_folder',lambda _:tmp_path)
    store=GrantStore(tmp_path.parent/'slow_grants.json')
    store.grant(str(tmp_path),['read','write','create','install_dependencies','build','run_dev_server'])
    monkeypatch.setattr(module,'GrantStore',lambda:store)
    monkeypatch.setattr(module,'TaskStateStore',lambda:__import__('computer_control.state_store',fromlist=['TaskStateStore']).TaskStateStore(tmp_path.parent/'slow_ledger.sqlite3'))
    def pretend_install(project,grants,runner,*,cancel):
        (project/'node_modules').mkdir()
        (project/'dist').mkdir()
        (project/'dist'/'index.html').write_text('ok')
        return {'status':'verified'}
    monkeypatch.setattr(module,'install_and_build',pretend_install)
    monkeypatch.setattr(module,'start_react',lambda *a,**kw:{'http_status':200,'url':'http://127.0.0.1:5173/','port':5173})
    monkeypatch.setattr(module,'Runner',lambda:SimpleNamespace(validate=lambda _:('code',['code',str(tmp_path)],None)))
    import subprocess,webbrowser
    monkeypatch.setattr(subprocess,'Popen',lambda *a,**kw:SimpleNamespace(pid=12345))
    monkeypatch.setattr(webbrowser,'open',lambda url:True)
    never_finishes=threading.Event()
    mission=ReactMission(window_probe=lambda project:never_finishes.wait(20),window_probe_timeout=0.1)
    assert mission.start('اعمل مشروع React على الديسكتوب','chat',True,Mode.SMART)['status']=='running'
    mission._worker.join(timeout=7)
    assert not mission._worker.is_alive(),mission.public()
    result=mission.public()
    assert result['status']=='needs_review'
    assert result['history'][2]['status']=='needs_review'
    assert result['history'][3]['status']=='committed'
