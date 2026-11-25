"""Regression contracts for the 2.2 React UI source.
These are static guards, not a substitute for npm build or real Windows tests.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT/'frontend'/'src'


def code(relative):
    return (SRC/relative).read_text(encoding='utf-8')


def test_barq_one_navigation_keeps_execution_services():
    app = code('App.tsx')
    assert '<WorkspaceStudio' not in app
    assert '<Composer ' in app and '<ApprovalDialog ' in app
    sidebar=code('components/layout/OperationsFrame.tsx')
    assert '<OperationsRail ' in app
    groups = sidebar.split('const navigationGroups = [', 1)[1].split('] as const', 1)[0]
    destinations = [key for group in re.findall(r"pages:\[([^\]]+)\]", groups)
                    for key in re.findall(r"'([a-z]+)'", group)]
    sections = re.findall(r"^ \['([a-z]+)',", code('pages/BarqOne.tsx'), re.M)
    top_source = re.search(r"topPages: readonly OnePage\[\]=\[([^\]]+)\]", sidebar)[1]
    top = re.findall(r"'([a-z]+)'", top_source)
    assert sorted(set(destinations + top)) == sorted(sections)
    assert 'chat' in top and 'chat' not in destinations
    assert 'className="ops-top-navigation"' in sidebar
    assert "onePage!=='chat'&&<OperationsRail" in app
    assert 'Conversation history' in sidebar
    assert 'className="ops-chat-history"' not in sidebar
    workspace = code('components/workspace/WorkspaceStudio.tsx')
    assert '<WorkspaceTools open inside' in workspace
    workspace += code('components/workspace/WorkspaceTools.tsx')
    for action in ('/v1/coding/map','/v1/agent/plan','/v1/build/preview',
                   '/v1/mcp/servers','/v1/github/preview'):
        assert action in workspace


def test_all_model_options_remain_visible_and_keyboard_accessible():
    text=code('components/chat/ModelSelector.tsx')
    for fragment in ('role="listbox"','role="option"','ArrowDown','ArrowUp','Escape',
                     'setQuery','m.provider','available','No matching models'):
        assert fragment in text
    # not-hidden is important so keys can be added in settings later
    assert 'items={available.filter(m=>m.id===\'auto\'||!localOnly||m.local)' not in text


def test_provider_status_is_not_a_fake_cloud_health_claim():
    status=code('components/layout/ConnectionStatus.tsx')
    assert 'Cloud · ${verifiedCloud.length} verified' in status
    assert 'Cloud · ${cloudKeys.length} configured (unchecked)' in status
    assert 'p.ready' in status
    assert 'suspected_offline' in status
    assert 'Ollama ready' in status


def test_editor_requires_preview_and_consent():
    s=code('components/chat/CodeBlock.tsx')
    assert '/v1/workspace/edit/preview' in s
    assert '/v1/workspace/edit/apply' in s
    assert '/v1/workspace/edit/undo' in s
    assert "approval_id:preview.approval_id,confirmed:true" in s
    assert "tool_id:'project_tests',workspace,confirmed:true" in s
    assert 'Tests execute code' in s
    assert 'Download code as file' in s


def test_voice_readiness_and_local_offline_limitations_are_visible():
    v=code('components/layout/VoiceSettings.tsx')
    c=code('components/chat/Composer.tsx')
    assert '/v1/voice/settings' in v and '/v1/voice/speak' in v
    assert 'BARQ_LOCAL_STT_MODEL_PATH' in v and 'Gemini' in v
    assert 'MicOff' not in c and '<Mic ' not in c
    assert '/v1/voice/readiness' in code('lib/localVoice.ts')
    assert '<HandsFreeVoice/>' in code('App.tsx')
    assert 'Shift+Enter' in c and 'dir="ltr"' in c


def test_theme_branding_and_buttons():
    tokens=code('styles/tokens.css')
    styles=code('styles/global.css')
    assert '#ae2143' in tokens and '#ff728c' in tokens
    assert "font-family:'GE SS Two'" in styles
    assert 'prefers-reduced-motion' in styles
    buttons=code('components/ui/Button.tsx')
    for word in ('whileTap','whileHover','useReducedMotion','success','error','loading','magnetic'):
        assert word in buttons


def test_settings_tabs_cover_all_ten_requested_areas():
    s=code('components/layout/SettingsModal.tsx')
    for tab in ("'general'", "'appearance'", "'models'", "'voice'", "'workspace'", "'performance'", "'shortcuts'", "'data'"):
        assert tab in s
    assert 'VoiceSettings' in s and 'ModelControls' in s and 'PerformanceSettings' in s


def test_arabic_first_and_no_ui_emojis():
    state=code('store/index.ts')
    assert "language:'ar'" in state
    workspace=code('components/workspace/WorkspaceStudio.tsx')
    assert 'مساعد البرمجة' in workspace and 'معاينة' in workspace
    # Emoji pictographs should be represented by lucide-react icons instead.
    for f in SRC.rglob('*'):
        if f.suffix not in {'.tsx','.ts'}:continue
        txt=f.read_text(encoding='utf-8')
        assert not re.search('[\U0001f300-\U0001f9ff]',txt), f.name


def test_windows_pipeline_preserves_real_self_test_and_user_font():
    script=(ROOT/'scripts/build_windows.ps1').read_text(encoding='utf-8')
    assert 'npm run build' in script
    assert 'run_python_build_tests.py' in script
    runner=(ROOT/'scripts/run_python_build_tests.py').read_text(encoding='utf-8')
    assert "'-m', 'pytest'" in runner and "'--junitxml=release/python-tests.xml'" in runner
    assert 'Start-Process -FilePath $exe' in script
    assert 'self-test.json' in script and 'smokeProcess.ExitCode' in script
    assert 'find_inno.ps1' in script
    assert 'web\\fonts\\ge-ss-two-medium.otf' in script
