from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


def test_closing_only_hides_not_ends_session():
    source = (BASE / 'voice/background_window.py').read_text(encoding='utf-8')
    block = source.split('    def on_closing(self) -> bool:', 1)[1].split('    def open(', 1)[0]
    assert 'self.window.hide()' in block
    assert 'return False' in block
    assert 'barq-handsfree-stop' not in block
    assert 'stop_listener' not in block


def test_hardware_setup_checked_by_default_in_both_installers():
    for name in ('installer.iss', 'installer_update.iss'):
        src = (BASE / 'scripts' / name).read_text(encoding='utf-8')
        task = next(line for line in src.splitlines() if line.startswith('Name: hardwaresensors;'))
        assert 'unchecked' not in task
        assert 'install_hardware_monitor.ps1' in src
