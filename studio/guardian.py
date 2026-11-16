"""BARQ Guardian: opt-in, read-only local project inspection.

No code execution, network, cloud prompts or writes are performed here.
Statuses distinguish PASS / WARNING / UNKNOWN: a missing check is never a pass.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import time
from core.paths import state_file
from workspace.manager import root_of, checked_path
from studio.security_monitor import scan_project

PACKAGES = ('requirements.txt', 'requirements.lock', 'pyproject.toml', 'poetry.lock',
            'Pipfile.lock', 'uv.lock', 'package-lock.json', 'pnpm-lock.yaml', 'yarn.lock', 'Cargo.lock')


def dependency_status(workspace: str) -> dict:
    """Inventory only. Do not falsely claim a vulnerability DB was consulted."""
    root = root_of(workspace)
    found = [name for name in PACKAGES if (root / name).is_file() and not (root / name).is_symlink()]
    lock = [name for name in found if name.endswith('.lock') or name in ('package-lock.json', 'yarn.lock', 'Cargo.lock', 'uv.lock')]
    available = {name: bool(shutil.which(name)) for name in ('pip-audit', 'osv-scanner', 'npm')}
    return {
        'status': 'unknown' if found else 'not_applicable',
        'manifests': found, 'locks': lock, 'tools_installed': available,
        'note_ar': 'تم حصر الاعتماديات محليًا فقط. لم يتم الاتصال بقاعدة ثغرات؛ حالة الأمان غير مؤكدة.' if found
                   else 'لا توجد ملفات اعتماديات معروفة في جذر المشروع.',
        'suggested_checks': (["pip-audit -r requirements.txt"] if 'requirements.txt' in found else []) +
                            (["npm audit --offline"] if 'package-lock.json' in found else []),
    }


def build_readiness(workspace: str) -> dict:
    root = root_of(workspace)
    frontend = (root / 'frontend')
    ts_project = (frontend / 'package.json').is_file()
    is_barq = (root / 'scripts' / 'build_windows.ps1').is_file()
    checks = [
        {'name': 'Windows build host', 'status': 'pass' if os.name == 'nt' else 'unknown'},
        {'name': 'Python', 'status': 'pass' if shutil.which('python') else 'warning'},
        {'name': 'Node.js', 'status': 'pass' if shutil.which('node') else 'unknown'},
        {'name': 'npm', 'status': 'pass' if shutil.which('npm') else 'unknown'},
        {'name': 'React dependencies', 'status': 'pass' if (frontend / 'node_modules').is_dir() else 'unknown'} if ts_project else None,
        {'name': 'Windows installer script', 'status': 'pass' if (root / 'scripts' / 'installer.iss').is_file() else 'unknown'} if is_barq else None,
        {'name': 'Packaged EXE smoke test', 'status': 'unknown'},
        {'name': 'Full test suite', 'status': 'unknown'},
    ]
    checks = [x for x in checks if x]
    return {'status': 'needs_verification', 'checks': checks,
            'note_ar': 'ده فحص جاهزية فقط. لا يعتبر EXE أو الاختبارات ناجحة من غير تشغيل حقيقي وتقرير نجاح.'}


def checkpoints(workspace: str, limit: int = 40) -> dict:
    root = str(root_of(workspace))
    backup = state_file('edit-backups')
    entries = []
    if backup.exists():
        for f in sorted(backup.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:400]:
            try:
                if not f.stem.isalnum() or len(f.stem) != 32 or f.is_symlink() or f.stat().st_size > 1_200_000:
                    continue
                data = json.loads(f.read_text('utf-8'))
                if str(root_of(data.get('workspace', ''))) != root:
                    continue
                checked_path(root, data['path'])
                entries.append({'id': f.stem, 'path': data['path'], 'time': int(f.stat().st_mtime),
                                'kind': 'file_edit', 'restorable': True})
                if len(entries) >= min(max(limit, 1), 100):
                    break
            except (ValueError, OSError, KeyError, TypeError):
                continue
    return {'checkpoints': entries, 'note_ar': 'نقاط استعادة تغييرات الملفات، وليست نسخًا كاملة من المشروع.'}


def project_health(workspace: str) -> dict:
    root = root_of(workspace)
    scan = scan_project(str(root))
    deps = dependency_status(str(root))
    build = build_readiness(str(root))
    backups = checkpoints(str(root), 20)
    summary = scan['summary']
    # NOT a security grade: only a completion/alert indicator for scans that ran.
    security_status = 'warning' if summary.get('critical', 0) or summary.get('high', 0) else 'reviewed'
    categories = [
        {'id': 'code', 'title_ar': 'فحص السورس', 'status': security_status,
         'detail_ar': f"{scan['checked']} ملف اتفحص، {len(scan['findings'])} تنبيه. الفحص محدود بقواعد محلية."},
        {'id': 'dependencies', 'title_ar': 'أمان المكتبات', 'status': deps['status'],
         'detail_ar': deps['note_ar']},
        {'id': 'tests', 'title_ar': 'الاختبارات', 'status': 'unknown',
         'detail_ar': 'لم يتم تشغيل اختبارات تلقائيًا؛ شغّل الاختبارات بموافقتك.'},
        {'id': 'build', 'title_ar': 'جاهزية البناء', 'status': build['status'],
         'detail_ar': build['note_ar']},
        {'id': 'recovery', 'title_ar': 'نقاط الاستعادة', 'status': 'reviewed' if backups['checkpoints'] else 'unknown',
         'detail_ar': f"{len(backups['checkpoints'])} نقطة استعادة محفوظة لتعديلات الملفات."},
        {'id': 'runtime', 'title_ar': 'مراقبة التشغيل', 'status': 'unknown',
         'detail_ar': 'مراقبة عمليات المشروع تتطلب اختيار عملية وتشغيل المراقبة صراحةً.'},
    ]
    return {'workspace_name': root.name, 'timestamp': int(time.time()), 'categories': categories,
            'security': {'checked': scan['checked'], 'summary': summary, 'findings': scan['findings'][:80], 'limit': scan['limit'], 'truncated': scan.get('truncated', False)},
            'dependencies': deps, 'build': build, 'checkpoints': backups['checkpoints'],
            'score': None, 'score_label_ar': 'غير مكتمل: في فحوصات ما اتعملتش',
            'note_ar': 'الحالة المجهولة لا تعني النجاح. الفحص محلي ولا يرسل بيانات للخارج.'}


def debug_guidance(workspace: str, finding_id: str) -> dict:
    if not finding_id or len(finding_id) > 256:
        raise ValueError('Invalid finding identifier')
    report = scan_project(workspace)
    finding = next((f for f in report['findings'] if f['id'] == finding_id), None)
    if finding is None:
        raise ValueError('Finding missing or changed; run a new scan')
    return {'finding_id': finding_id, 'file': finding['file'], 'line': finding['line'],
            'severity': finding['severity'], 'message_ar': finding['title_ar'],
            'steps_ar': ['افتح الملف وراجع السطر المحدد والسياق القريب.',
                         finding['advice_ar'],
                         'اطلب من برق اقتراح Diff فقط، وراجعه قبل أي كتابة.',
                         'بعد موافقتك على التعديل أعد الفحص وشغّل اختبارات المشروع بعد موافقتك.'],
            'requires_approval': True, 'applied': False}
