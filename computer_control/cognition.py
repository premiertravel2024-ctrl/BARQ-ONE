"""BARQ's deterministic understanding/intent/verification layer.

These are control-plane checks, NOT a claim of human-like awareness. The LLM
proposes plans; this module decides what was actually observed/verified.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
import hashlib, re, unicodedata


def _norm(s: str) -> str:
    s = unicodedata.normalize('NFKC', s or '').lower()
    s = re.sub(r'[\u064b-\u065f\u0670ـ]', '', s)
    s = s.replace('أ','ا').replace('إ','ا').replace('آ','ا').replace('ى','ي')
    return re.sub(r'\s+', ' ', s).strip()


@dataclass(frozen=True)
class Intent:
    label: str
    compound: bool
    source: str
    confidence: str
    target: str = ''
    expected_tool: str = ''
    def public(self) -> dict[str, Any]: return asdict(self)


VERBS = {
    'open_app': ('افتح ', 'شغل ', 'فتح ', 'open ', 'launch ', 'start '),
    'focus_window': ('روح ل', 'بدل ل', 'ركز علي', 'focus ', 'switch to '),
    'system_setting': ('الصوت', 'volume', 'الاضاءه', 'سطوع', 'brightness', 'settings', 'الاعدادات'),
    'file_operation': ('انشئ ', 'اعمل ملف', 'اعمل مجلد', 'احفظ ', 'انسخ ', 'انقل ', 'احذف ', 'create ', 'copy ', 'move ', 'rename ', 'write ', 'delete '),
    'inspect': ('وريني ', 'اعرض ', 'قولي ايه المفتوح', 'list ', 'show ', 'inspect ', 'what is open'),
}


def interpret_goal(goal: str, source: str = 'text') -> Intent:
    if source not in ('text', 'voice', 'palette'):
        raise ValueError('Unsupported command source')
    norm = _norm(goal)
    if not norm or len(goal) > 3000:
        raise ValueError('Goal missing or too long')
    # Explicit compound or multi-step utterances do NOT inherit a single-step
    # success condition; screen changes alone never prove the whole goal.
    compound = bool(re.search(r'\b(?:وبعدين|ثم|بعدها|بعد كده|and then|then|after that)\b', norm))
    # Conjunction on commands rather than Arabic characters inside words.
    compound |= bool(re.search(r'(?:\s+و(?:افتح|شغل|احفظ|اكتب|اعمل|انشئ|انسخ|اقفل)\b|\s+and\s+(?:open|save|write|create|close)\b)', norm))
    if len(re.findall(r'\b(?:افتح|شغل|احفظ|اكتب|انشئ|انسخ|احذف|open|save|create|write|delete)\b',norm))>1:
        compound = True
    label='multi_step'
    for key in ('file_operation','focus_window','inspect','open_app'):
        if any(norm.startswith(_norm(v)) for v in VERBS[key]):
            label=key;break
    if label=='multi_step' and any(v in norm for v in VERBS['system_setting']):label='system_setting'
    if compound: label='multi_step'
    # Target used only for status display, NEVER for execution or path security.
    target=norm.split(' ',1)[1][:120] if ' ' in norm else ''
    expected=''
    if label=='file_operation':
        matches=(('create_dir',('مجلد','folder','directory')),
                 ('delete',('احذف','امسح','delete','remove')),
                 ('copy',('انسخ','copy')),('move',('انقل','move')),
                 ('rename',('غير اسم','rename')),('write_file',('ملف','file','save','احفظ')))
        expected=next((tool for tool,words in matches if any(w in norm for w in words)),'')
    return Intent(label,compound,source,'rule_match' if label!='multi_step' else 'needs_planner',target,expected)


@dataclass(frozen=True)
class Evidence:
    status: str  # verified | observed_change | unverified | contradicted
    reason: str
    proof: str = ''
    def public(self) -> dict[str,str]: return asdict(self)


def _sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(65536),b''):h.update(block)
    return h.hexdigest()


def verify_action(tool: str, args: dict, result: dict, before: dict | None = None, after: dict | None = None) -> Evidence:
    """Evidence must be checked independently of the model's expected field.

    A GUI's visual change is only observed_change, not verified goal success.
    No full file contents, private texts, or screenshots are persisted in proof.
    """
    try:
        if tool in {'create_dir','write_file','append_file','copy','move','rename','delete'}:
            dest=Path(args.get('dst') or args.get('path') or '')
            if tool=='create_dir':ok=dest.is_dir()
            elif tool in ('write_file','append_file'):ok=dest.is_file() and (not args.get('text') or (dest.stat().st_size>0))
            elif tool=='copy':
                src=Path(args['src']);ok=src.is_file() and dest.is_file() and _sha(src)==_sha(dest)
            elif tool in ('move','rename'):ok=dest.exists() and not Path(args['src']).exists()
            else:ok=not dest.exists()
            return Evidence('verified' if ok else 'contradicted','Filesystem state checked independently','exists/matches' if ok else 'missing/mismatch')
        if tool in ('get_volume','get_brightness'):
            actual=result.get('percent')
            valid=type(actual) in (int,float) and 0<=actual<=100
            return Evidence('verified' if valid else 'unverified','OS setting level read',str(actual) if valid else '')
        if tool in ('set_volume','set_brightness'):
            actual=result.get('percent')
            ok=type(actual) in (int,float) and abs(actual-args.get('percent',-100))<=1
            return Evidence('verified' if ok else 'unverified','OS setting readback after change',str(actual) if actual is not None else '')
        if tool in ('close_window','minimize_window','maximize_window'):
            verified=result.get('window_closed' if tool=='close_window' else 'window_state') is True
            return Evidence('verified' if verified else 'unverified','Native window state checked after action')
        if tool=='wait_for' and result.get('found') is not True:
            return Evidence('unverified','Requested UI element did not appear')
        if tool=='focus_window' and after is not None:
            ok=after.get('window','').casefold()==str(args.get('title','')).casefold()
            return Evidence('verified' if ok else 'unverified','Active window title checked')
        if tool=='open_folder' and result.get('folder_visible') is True:
            return Evidence('verified','Explorer reported the requested folder path')
        if tool=='open_app' and after is not None:
            from computer_control.tools.app_index import normalized_app
            requested=normalized_app(str(args.get('name') or args.get('path') or '')).casefold().removesuffix('.exe')
            names=[str(n).casefold() for n in after.get('windows',[])]
            if requested and any(requested in name for name in names):
                return Evidence('verified','Requested application window was visible')
        if tool in ('list_windows','list_apps','list_processes','get_system_info','list_dir','search_files','observe','take_screenshot','read_file','wait_for','find_ui_elements'):
            return Evidence('verified','A read-only result was returned')
        if before is not None and after is not None:
            changed=before.get('screenshot_hash')!=after.get('screenshot_hash') or before.get('window')!=after.get('window') or before.get('elements')!=after.get('elements')
            if changed:return Evidence('observed_change','Desktop changed; requested end state is not established')
        return Evidence('unverified','Execution returned, but no independent proof of goal completion')
    except (KeyError,ValueError,OSError,TypeError) as exc:
        return Evidence('unverified','Verifier could not inspect the outcome',type(exc).__name__)


def verify_goal(intent: Intent, history: list[dict]) -> Evidence:
    """Never translate LLM `done` directly into success."""
    actions=[h for h in history if h.get('status')=='ok']
    if not actions:return Evidence('unverified','No successful actions to validate')
    if any(h.get('status') in ('error','blocked','invalid') for h in history):
        return Evidence('unverified','A previous action failed or was blocked')
    # For compound goals, isolated verified actions cannot prove the whole task.
    if intent.compound or intent.label=='multi_step':
        return Evidence('unverified','Multi-step goal needs an explicit end-state check')
    covered={
        'open_app': {'open_app'},'focus_window':{'focus_window'},
        'system_setting':{'set_volume','set_brightness','open_windows_settings'},
        'file_operation':{'create_dir','write_file','append_file','copy','move','rename','delete'},
        'inspect': {'list_windows','list_apps','list_processes','get_system_info','list_dir','search_files','observe'},
    }.get(intent.label,set())
    if intent.expected_tool:
        covered={intent.expected_tool}
    success=[h for h in actions if h.get('tool') in covered and h.get('verification')=='verified']
    if success:
        return Evidence('verified','A matching requested end-state was independently checked')
    return Evidence('unverified','A command ran, but the requested outcome could not be independently verified')
