"""Project-scoped IDE metadata, file tree, read-only git state and audit log.

Local endpoints never shell-execute AI content. User edits still go through the
existing work.propose/apply/undo approval + conflict-detection pipeline.
"""
from __future__ import annotations
import fnmatch
import json
import os
import re
import subprocess
import time
from pathlib import Path
from workspace.manager import root_of, BLOCKED

PRIVATE = re.compile(r'(?i)(^\.env($|\.)|id_rsa|private.?key|secret|credential|token|\.pem$|\.key$|\.p12$)')
MAX_TREE = 1800
MAX_STATE = 24_000


def _base(workspace: str) -> Path:
    return root_of(workspace)


def _meta(workspace: str) -> Path:
    root = _base(workspace)
    folder = root / '.barq'
    if folder.is_symlink() or not folder.resolve().is_relative_to(root):
        raise ValueError('Invalid BARQ metadata directory')
    folder.mkdir(exist_ok=True)
    return folder


def _patterns(root: Path) -> list[str]:
    patterns = []
    for file in ('.gitignore', '.barqignore'):
        try:
            data = (root / file).read_text(encoding='utf-8')[:32_000]
        except (OSError, UnicodeError):
            continue
        patterns += [line.strip() for line in data.splitlines() if line.strip() and not line.lstrip().startswith(('#', '!'))]
    return patterns


def _ignored(name: str, relative: str, is_dir: bool, patterns: list[str]) -> bool:
    if name in BLOCKED or name in {'.barq', '.git', '.pytest_cache', '.mypy_cache', 'coverage', 'vendor', '.idea', '.tox', '.cache'}:
        return True
    if PRIVATE.search(name) or name.startswith('.env'):
        return True
    return any(fnmatch.fnmatch(relative, p.lstrip('/')) or
               fnmatch.fnmatch(name, p.rstrip('/')) or
               (p.endswith('/') and (relative == p.rstrip('/') or relative.startswith(p)))
               for p in patterns)


def tree(workspace: str) -> dict:
    root = _base(workspace)
    patterns = _patterns(root)
    items: list[dict] = []
    # os.walk never follows symlinks; filter while descending to exclude secrets.
    for folder, dirs, files in os.walk(root, followlinks=False):
        parent = Path(folder)
        def acceptable(name: str, is_dir: bool) -> bool:
            candidate = parent / name
            if candidate.is_symlink():
                return False
            rel = candidate.relative_to(root).as_posix()
            return not _ignored(name, rel, is_dir, patterns)
        dirs[:] = sorted((x for x in dirs if acceptable(x, True)), key=str.casefold)
        for name, is_dir in [(x, True) for x in dirs] + [(x, False) for x in sorted(files, key=str.casefold) if acceptable(x, False)]:
            candidate = parent / name
            if len(items) >= MAX_TREE:
                break
            try:
                size = candidate.stat().st_size if not is_dir else None
            except OSError:
                continue
            rel = candidate.relative_to(root).as_posix()
            items.append({'name': name, 'path': rel, 'is_dir': is_dir, 'size': size})
        if len(items) >= MAX_TREE:
            break
    markers = {'package.json': 'JavaScript / TypeScript', 'pyproject.toml': 'Python',
               'requirements.txt': 'Python', 'Cargo.toml': 'Rust', 'go.mod': 'Go'}
    stacks = [label for name, label in markers.items() if (root / name).is_file()]
    return {'root': str(root), 'items': items, 'truncated': len(items) >= MAX_TREE, 'stack': list(dict.fromkeys(stacks))}


def get_state(workspace: str) -> dict:
    file = _meta(workspace) / 'workspace.json'
    if not file.is_file():
        return {'layout': {}, 'tabs': [], 'activeFile': '', 'activity': 'explorer'}
    if file.stat().st_size > MAX_STATE:
        raise ValueError('Workspace preferences too large')
    try:
        data = json.loads(file.read_text(encoding='utf-8'))
    except (ValueError, OSError):
        return {'layout': {}, 'tabs': [], 'activeFile': '', 'activity': 'explorer'}
    return data if isinstance(data, dict) else {}


def save_state(workspace: str, state: dict) -> dict:
    if not isinstance(state, dict):
        raise ValueError('Invalid workspace preferences')
    # Persist UI geometry and paths only, never source text or credentials.
    allowed = {key: state[key] for key in ('layout', 'tabs', 'activeFile', 'activity', 'bottomTab') if key in state}
    raw = json.dumps(allowed, ensure_ascii=False)
    if len(raw.encode('utf-8')) > MAX_STATE:
        raise ValueError('Workspace preferences too large')
    folder = _meta(workspace)
    file = folder / 'workspace.json'
    pending = folder / 'workspace.json.tmp'
    pending.write_text(raw, encoding='utf-8')
    os.replace(pending, file)
    return {'saved': True}


def git_info(workspace: str) -> dict:
    root = _base(workspace)
    try:
        r = subprocess.run(['git', '-C', str(root), 'status', '--porcelain=v1', '-b', '--untracked-files=normal'],
                           capture_output=True, text=True, timeout=4, check=False,
                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if r.returncode:
            return {'available': False, 'branch': '', 'changes': []}
        lines = r.stdout.splitlines()
        branch = lines[0].removeprefix('## ') if lines else ''
        return {'available': True, 'branch': branch[:120], 'changes': [line[:500] for line in lines[1:301]]}
    except (OSError, subprocess.TimeoutExpired):
        return {'available': False, 'branch': '', 'changes': []}


def record(workspace: str, actor: str, kind: str, details: str, status: str='ok') -> None:
    try:
        file = _meta(workspace) / 'operations.jsonl'
        event = {'time': int(time.time()), 'actor': actor, 'type': kind,
                 'details': details[:600], 'status': status}
        with file.open('a', encoding='utf-8') as out:
            out.write(json.dumps(event, ensure_ascii=False) + '\n')
        if file.stat().st_size > 2_000_000:
            lines = file.read_text(encoding='utf-8').splitlines()[-600:]
            file.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    except (OSError, ValueError):
        pass  # Logging failure must never hide an already committed source edit.


def operations(workspace: str, limit: int=120) -> dict:
    file = _meta(workspace) / 'operations.jsonl'
    if not file.exists():
        return {'events': []}
    if file.stat().st_size > 2_100_000:
        raise ValueError('Operations log too large')
    records = []
    for line in file.read_text(encoding='utf-8').splitlines()[-min(max(limit,1),250):]:
        try:
            data = json.loads(line)
            if isinstance(data, dict): records.append(data)
        except ValueError:
            pass
    return {'events': records[::-1]}


def pick_folder() -> dict:
    # Backend native folder dialog is useful on Windows desktop but intentionally
    # unavailable on a headless server. No user-controlled command is executed.
    if os.name != 'nt':
        raise ValueError('Native folder picker requires Windows desktop')
    import tkinter
    from tkinter import filedialog
    app = tkinter.Tk(); app.withdraw(); app.attributes('-topmost', True)
    try:
        selected = filedialog.askdirectory(title='اختار مجلد المشروع')
    finally:
        app.destroy()
    return {'path': str(_base(selected)) if selected else ''}
