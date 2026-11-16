"""Regression guard for organized BARQ settings; does not require npm or Windows."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT / "frontend/src"


def read(path: str) -> str:
    return (FRONT / path).read_text(encoding="utf-8")


def test_settings_navigation_has_all_twelve_sections_in_three_groups():
    src = read("components/layout/SettingsModal.tsx")
    assert "groupedTabs" in src
    assert src.count("{labelAr:'") == 3
    for name in ("general", "appearance", "models", "voice", "workspace", "computer", "launcher", "network", "performance", "shortcuts", "data", "about"):
        assert f"'{name}'" in src
    assert 'aria-current={tab===id?' in src


def test_settings_scrolling_and_small_screen_select():
    modal = read("components/layout/SettingsModal.tsx")
    css = read("styles/global.css")
    assert "mainRef.current.scrollTop=0" in modal
    assert "barq-settings-mobile" in modal and "barq-settings-main" in modal
    assert "@media(max-width:750px)" in css
    assert ".barq-settings-nav{display:none}" in css


def test_settings_modal_scoping_does_not_restyle_other_dialogs():
    settings = read("components/layout/SettingsModal.tsx")
    modal = read("components/ui/Modal.tsx")
    assert 'dialogClassName="barq-settings-dialog"' in settings
    assert 'bodyClassName="barq-settings-body"' in settings
    assert "dialogClassName=''" in modal and "bodyClassName=''" in modal


def test_voice_controls_and_direct_permissions_remain_functional():
    src = read("components/layout/VoiceSettings.tsx")
    for control in ("openConversation", "allowComputerInConversation", "setWakeOption", "start_with_windows", "startup_greeting", "edge_glow", "input_device", "trainWake", "restartWake"):
        assert control in src
    assert "barq-settings-card-feature" in src
    assert "تشخيص الصوت المتقدم وتعليم النداء" in src
    assert "barq-settings-advanced-actions" in src


def test_computer_permissions_are_not_confused_with_current_task():
    src = read("components/workspace/ComputerControl.tsx")
    assert "صلاحية التحكم مفعّلة" in src
    assert "صلاحية التحكم مقفولة" in src
    assert "settingsOnly&&installPaths&&<details" in src
    assert "update({enabled:e.target.checked})" in src


def test_rtl_accessibility_and_no_forced_language_changes():
    src = read("components/layout/SettingsModal.tsx")
    css = read("styles/global.css")
    assert "dir={language==='ar'?'rtl':'ltr'}" in src
    assert "aria-label={language==='ar'?'أقسام الإعدادات'" in src
    assert "border-inline-end" in css
    assert "focus-ring" in src
