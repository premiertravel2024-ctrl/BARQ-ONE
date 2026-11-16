"""Main-chat executor regression: Egyptian build commands must not become tutorials."""
from pathlib import Path
from agent.task_intent import classify_task, asks_to_build_application

ROOT = Path(__file__).resolve().parents[1]


def test_egyptian_direct_app_requests_route_to_approved_workflow():
    for request in (
        'عاوزك تبنيلي تطبيق موسيقى بواجهة أزرار وتخرجهولي exe',
        'عاوزك تعملي برنامج محاسبة',
        'اعمللي برنامج إدارة فنادق',
        'ابنيلي تطبيق سطح مكتب',
        'تبنيلي موقع جديد',
    ):
        decision = classify_task(request)
        assert decision is not None, request
        assert decision['kind'] == 'coding' and decision['new_project']
        assert decision['requires_approval'] is True


def test_explanatory_questions_do_not_trigger_file_changes():
    for request in (
        'اشرحلي ازاي اعمل برنامج',
        'تقدر تبنيلي برنامج؟',
        'اكتبلي كود بايثون',
    ):
        assert classify_task(request) is None
    assert not asks_to_build_application('اعمل مقارنة بين برامج الموسيقى')


def test_one_main_chat_controls_workspace_and_project_actions():
    source = (ROOT / 'frontend/src/lib/chat.ts').read_text(encoding='utf-8')
    app = (ROOT / 'frontend/src/App.tsx').read_text(encoding='utf-8')
    studio = (ROOT / 'frontend/src/components/workspace/WorkspaceStudio.tsx').read_text(encoding='utf-8')
    from tests.test_chat_smoke_launcher_regression import run_smoke
    result=run_smoke()
    assert result.returncode==0, result.stdout+'\n'+result.stderr
    assert "'/v1/agent/prepare'" in source
    assert "'/v1/studio/pick-folder'" in source
    assert "window.addEventListener('barq-open-workspace',show)" in app
    assert "window.addEventListener('barq-chat-prefill',route)" in app
    assert "data-chat-mode=\"unified\"" in studio
    assert 'barq-chat-prefill' in studio
    assert '<form className="shrink-0 space-y-2 border-t border-stroke p-3"' not in studio
    assert 'textarea value={ask}' not in studio
    assert 'راجع' in studio and 'موافقة' in studio


def test_execution_never_pretends_scaffold_is_finished_product():
    source = (ROOT / 'agent/orchestrator.py').read_text(encoding='utf-8')
    assert 'Do not stop after the starter template' in source
    assert "'blocked':True" in source
    assert 'قولي «كمل»' not in source
