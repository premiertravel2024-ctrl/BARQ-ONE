"""Local, read-only BARQ source monitor.

No arbitrary project execution, no network calls, and no source code or secret values
in responses. Matches are heuristic review hints, not confirmed vulnerabilities.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from concurrent.futures import ThreadPoolExecutor
from core.adaptive_resources import resources as adaptive_resources

from coding.quality import source_check
from studio.project import tree as project_tree
from workspace.manager import read_text, checked_path

MAX_CONTENT = 180_000
MAX_FILES = 500
SCAN_EXTENSIONS = {'.py', '.js', '.jsx', '.ts', '.tsx', '.html', '.css', '.json', '.yml', '.yaml', '.toml', '.sql'}

# Rule names/messages are static and contain no extracted snippets.
RULES: tuple[tuple[str, str, str, re.Pattern[str], str], ...] = (
    ('JS_EVAL', 'high', 'استخدام eval أو Function لتنفيذ نصوص ديناميكية',
     re.compile(r'\b(?:eval\s*\(|new\s+Function\s*\()'), 'استخدم دوال ثابتة وتحليل بيانات بدل تنفيذ نصوص.'),
    ('JS_HTML', 'medium', 'حقن محتوى HTML يحتاج مراجعة',
     re.compile(r'\b(?:innerHTML\s*=|dangerouslySetInnerHTML\s*=|document\.write\s*\()'), 'لا تُدخل محتوى المستخدم كـ HTML مباشرة؛ استخدم textContent أو تنقية موثوقة.'),
    ('NODE_EXEC', 'high', 'تشغيل أمر نظام من كود JavaScript يحتاج مراجعة',
     re.compile(r'\b(?:child_process\.)?exec(?:Sync)?\s*\('), 'استخدم spawn/execFile بقائمة معاملات ثابتة بعد التحقق.'),
    ('INSECURE_TLS', 'critical', 'تعطيل التحقق من شهادات TLS',
     re.compile(r'\b(?:verify\s*=\s*False|rejectUnauthorized\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*[\'\"]?0)'), 'فعّل التحقق من TLS ولا تقبل شهادات غير موثوقة.'),
    ('SQL_INTERPOLATION', 'high', 'استعلام SQL مبني باستيفاء متغيرات',
     re.compile(r'(?i)(?:execute|query)\s*\(\s*(?:f[\'\"]|[\'\"][^\n]{0,120}(?:SELECT|UPDATE|INSERT|DELETE)[^\n]{0,120}[\'\"]\s*[+.])'), 'استخدم معاملات SQL المربوطة بدل ضم النصوص.'),
    ('WEAK_HASH', 'medium', 'استخدام خوارزمية تجزئة ضعيفة لأغراض حساسة',
     re.compile(r'\b(?:hashlib\.(?:md5|sha1)\s*\(|createHash\s*\(\s*[\'\"](?:md5|sha1)[\'\"])'), 'للحماية استخدم خوارزميات معتمدة؛ لتخزين كلمات المرور استخدم Argon2 أو bcrypt.'),
)
CREDENTIAL_NAME = re.compile(r'(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|private[_-]?key)\b')
SIMPLE_LITERAL = re.compile(r'(?i)(?:password|passwd|secret|api[_-]?key|access[_-]?token|private[_-]?key)\s*[:=]\s*[\'\"]([^\'\"]{8,})[\'\"]')
PLACEHOLDER = re.compile(r'(?i)^(?:replace|your|sample|example|demo|changeme|test|dummy|<|\$\{|\{\{)')
SEVERITIES = ('critical', 'high', 'medium', 'low')


def _finding(path: str, line: int, rule: str, severity: str, title: str, advice: str, category: str = 'security') -> dict[str, Any]:
    return {'id': f'{path}:{line}:{rule}', 'file': path, 'line': line, 'rule': rule,
            'severity': severity, 'category': category, 'title_ar': title, 'advice_ar': advice}


def _summary(findings: list[dict]) -> dict:
    return {key: sum(f['severity'] == key for f in findings) for key in SEVERITIES}


def scan_content(path: str, content: str) -> dict:
    """Scan draft content without writing it to disk or executing it."""
    if len(content.encode('utf-8')) > MAX_CONTENT:
        raise ValueError('Code exceeds local monitor size limit')
    if not path or len(path) > 1000 or '\x00' in path:
        raise ValueError('Invalid display filename')
    suffix = Path(path).suffix.lower()
    if suffix not in SCAN_EXTENSIONS:
        return {'file': path, 'findings': [], 'summary': _summary([]), 'supported': False,
                'note_ar': 'نوع الملف غير مدعوم في الفحص الثابت الحالي'}
    findings: list[dict] = []
    lines = content.splitlines()
    static = source_check(path, content) if suffix in {'.py', '.json', '.toml', '.yaml', '.yml'} else None
    if static:
        for error in static['errors'][:6]:
            # Do not return raw exception details: they may contain the source line.
            findings.append(_finding(path, 1, 'SYNTAX', 'high', 'خطأ في صياغة الملف', 'راجع تركيب الملف باستخدام المحرر أو فاحص اللغة.', 'error'))
    if suffix == '.py':
        try:
            parsed = ast.parse(content, filename=path)
        except (SyntaxError, ValueError):
            parsed = None
        if parsed is not None:
            for node in ast.walk(parsed):
                if not isinstance(node, ast.Call):
                    continue
                line = getattr(node, 'lineno', 1)
                func = node.func
                name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ''
                if name in {'eval', 'exec'}:
                    findings.append(_finding(path,line,'PY_DYNAMIC','high','تنفيذ Python ديناميكي يحتاج مراجعة','تجنب eval/exec واستخدم واجهة بيانات ثابتة.'))
                if name in {'system', 'popen'} and isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == 'os':
                    findings.append(_finding(path,line,'PY_OS_SHELL','high','تنفيذ أمر باستخدام os.system أو os.popen','استخدم subprocess بقائمة معاملات وبدون shell=True.'))
                if any(key.arg == 'shell' and isinstance(key.value, ast.Constant) and key.value.value is True for key in node.keywords):
                    findings.append(_finding(path,line,'PY_SHELL','high','استدعاء subprocess مع shell=True','افصل الأمر عن المعاملات وتحقق من المدخلات.'))
                if name in {'load','loads'} and isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == 'pickle':
                    findings.append(_finding(path,line,'PY_PICKLE','high','تحميل بيانات pickle غير الموثوقة قد ينفّذ كودًا','استخدم JSON للبيانات الخارجية بدل pickle.'))
                if name == 'load' and isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == 'yaml':
                    safe_loader = any(k.arg == 'Loader' and isinstance(k.value, ast.Attribute) and k.value.attr in {'SafeLoader','CSafeLoader'} for k in node.keywords)
                    if not safe_loader:
                        findings.append(_finding(path,line,'PY_YAML','high','استخدام yaml.load دون SafeLoader','استخدم yaml.safe_load للبيانات غير الموثوقة.'))
    for number, text in enumerate(lines[:6000], 1):
        if suffix in {'.js', '.jsx', '.ts', '.tsx', '.html'}:
            applicable = RULES
        else:
            applicable = tuple(rule for rule in RULES if rule[0] in {'INSECURE_TLS', 'SQL_INTERPOLATION','WEAK_HASH'})
        for rule, severity, title, pattern, advice in applicable:
            if pattern.search(text):
                findings.append(_finding(path, number, rule, severity, title, advice))
        match = SIMPLE_LITERAL.search(text)
        if match and CREDENTIAL_NAME.search(text) and not PLACEHOLDER.search(match.group(1).strip()):
            findings.append(_finding(path, number, 'HARDCODED_SECRET', 'critical', 'قيمة سرية محتملة مكتوبة داخل الكود', 'احذف القيمة من السورس واستخدم مدير أسرار أو متغيرات بيئة، وبدّل المفتاح إن كان حقيقيًا.'))
    # Stable IDs, no duplicated rule/line pairs. Never include source snippets.
    unique = {f['id']: f for f in findings}
    sorted_items = sorted(unique.values(), key=lambda f: (SEVERITIES.index(f['severity']), f['file'], f['line'], f['rule']))[:250]
    return {'file': path, 'findings': sorted_items, 'summary': _summary(sorted_items), 'supported': True,
            'note_ar': 'فحص محلي ثابت؛ النتائج مؤشرات تحتاج مراجعة وليست إثباتًا لوجود ثغرة.'}


def scan_project(workspace: str) -> dict:
    """Adaptive, bounded and read-only project scan; no project execution/network.

    Local work runs concurrently only when memory and CPU conditions allow it.
    Source is never stored in a shared scan cache or sent to a provider.
    """
    policy = adaptive_resources.policy()
    effective_limit = min(MAX_FILES, policy['scan_max_files'])
    candidates = [item['path'] for item in project_tree(workspace)['items'] if not item['is_dir']
                  and Path(item['path']).suffix.lower() in SCAN_EXTENSIONS]
    files = candidates[:effective_limit]

    def scan_one(name: str) -> dict | None:
        try:
            checked_path(workspace, name)
            content = read_text(workspace, name)
            return scan_content(name, content)
        except (OSError, ValueError, UnicodeError):
            return None

    results = []
    workers = min(len(files), policy['scan_workers'])
    if workers > 1:
        # Ordered results are important for stable issue IDs and UI presentation.
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='barq-scan') as pool:
            results = list(pool.map(scan_one, files))
    else:
        results = [scan_one(name) for name in files]
    findings: list[dict] = []
    checked = 0
    for result in results:
        if result is None:
            continue
        checked += 1
        if len(findings) <= 1000:
            findings.extend(result['findings'])
    findings = sorted(findings, key=lambda f:(SEVERITIES.index(f['severity']), f['file'], f['line']))[:500]
    return {'checked': checked, 'limit': effective_limit, 'truncated': len(candidates) > effective_limit,
            'findings': findings, 'summary': _summary(findings),
            'adaptive_mode': policy['mode'], 'scan_workers': policy['scan_workers'],
            'note_ar': 'فحص محلي ثابت بحدود متكيّفة مع الجهاز، بلا تنفيذ أكواد أو اتصال خارجي. النتائج مؤشرات تحتاج مراجعة.'}
