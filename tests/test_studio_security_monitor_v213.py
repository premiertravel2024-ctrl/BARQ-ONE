"""BARQ v2.13 local safety monitor: deterministic and private."""
import os
from pathlib import Path

import pytest

from studio.security_monitor import scan_content, scan_project


def test_python_syntax_report_without_leaking_code():
    report = scan_content('broken.py', 'def nope(:\n  pass')
    assert any(f['category'] == 'error' for f in report['findings'])
    assert 'def nope' not in repr(report)


def test_python_risks_detected_precisely():
    report = scan_content('app.py', 'import subprocess\neval(user_data)\nsubprocess.run(command, shell=True)\n')
    ids = {f['rule'] for f in report['findings']}
    assert 'PY_DYNAMIC' in ids and 'PY_SHELL' in ids
    assert report['summary']['high'] >= 2


def test_secret_is_not_exposed_by_report():
    secret = 'never_print_private_key_value_1234567'
    report = scan_content('auth.ts', f'const api_key = "{secret}";\n')
    assert report['summary']['critical'] == 1
    assert secret not in repr(report)
    assert report['findings'][0]['line'] == 1


def test_html_injection_and_tls_alerts():
    report = scan_content('index.html', 'element.innerHTML = value;\nconst opts = {rejectUnauthorized: false};\n')
    assert {'JS_HTML','INSECURE_TLS'} <= {item['rule'] for item in report['findings']}


def test_safe_code_has_no_alerts():
    report = scan_content('main.py', 'def add(x, y):\n    return x+y\n')
    assert report['findings'] == []


def test_large_input_rejected():
    with pytest.raises(ValueError):
        scan_content('main.ts', 'a' * 180001)


def test_project_scans_locally_and_skips_private_and_symlink(tmp_path):
    (tmp_path/'src').mkdir()
    (tmp_path/'src'/'main.py').write_text('eval(user_input)\n', encoding='utf-8')
    (tmp_path/'secret.env').write_text('password = "never_show_me_secret"\n',encoding='utf-8')
    (tmp_path/'.gitignore').write_text('secret.env\n',encoding='utf-8')
    outside = tmp_path.parent / f'{tmp_path.name}-outside'
    outside.mkdir(exist_ok=True)
    (outside/'hidden.ts').write_text('eval(x)\n',encoding='utf-8')
    try:
        (tmp_path/'shortcut').symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pass
    report = scan_project(str(tmp_path))
    assert any(f['rule'] == 'PY_DYNAMIC' for f in report['findings'])
    assert all('secret.env' not in f['file'] and 'shortcut' not in f['file'] for f in report['findings'])
    assert 'never_show_me_secret' not in repr(report)


def test_scan_never_runs_scanned_code(tmp_path):
    marker=tmp_path/'would-have-executed.txt'
    source=f'from pathlib import Path\nPath({str(marker)!r}).write_text("executed")\n'
    (tmp_path/'do_not_run.py').write_text(source,encoding='utf-8')
    report=scan_project(str(tmp_path))
    assert report['checked']==1
    assert not marker.exists()


def test_security_report_has_rule_and_line_but_no_source_snippet():
    report=scan_content('frontend/login.tsx','element.innerHTML = userContent;\n')
    finding=report['findings'][0]
    assert finding['file']=='frontend/login.tsx'
    assert finding['line']==1
    assert finding['rule']=='JS_HTML'
    assert 'userContent' not in repr(finding)


def test_dangerous_loader_is_flagged():
    report=scan_content('settings.py','import pickle\nx=pickle.loads(data)\n')
    assert 'PY_PICKLE' in {item['rule'] for item in report['findings']}
