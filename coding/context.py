"""Bounded, read-only codebase mapping and literal search; no shell or API calls.

The goal is to give a cloud model useful architectural context without dumping a
repository, sending secrets, or accidentally including huge vendor trees.
"""
from collections import Counter
from pathlib import Path
import re
from workspace.manager import root_of, read_text, MAX_READ, BLOCKED, EXTENSIONS

SKIP = set(BLOCKED) | {'.pytest_cache', '.mypy_cache', '.ruff_cache', 'coverage', 'vendor', 'target', '.idea', '.vscode', '.tox', '.cache', '.turbo', 'venv', '.DS_Store'}
PRIVATE = re.compile(r'(^\.env($|\.)|secret|credential|private.?key|id_rsa|\.pem$|\.p12$|\.key$|\.sqlite|\.db$|token)', re.I)
SOURCE = EXTENSIONS | {'.vue', '.svelte', '.php', '.c', '.cpp', '.h', '.hpp', '.cs', '.kt', '.swift', '.rb', '.ipynb'}
MANIFESTS = ('pyproject.toml', 'requirements.txt', 'package.json', 'Cargo.toml', 'go.mod', 'pom.xml', 'README.md', 'AGENTS.md', 'tsconfig.json', 'pytest.ini')
MAX_FILES = 450


def _files(workspace):
    root = root_of(workspace)
    # Avoid following symlinks, vendored directories and known secrets.
    seen = 0
    for folder, dirs, files in __import__('os').walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP and not d.startswith('.env')
                         and not Path(folder, d).is_symlink())
        for name in sorted(files):
            path = Path(folder, name)
            if path.is_symlink() or PRIVATE.search(name) or name in SKIP or name.startswith('.env'):
                continue
            if path.suffix.lower() not in SOURCE and name not in MANIFESTS:
                continue
            try:
                if path.stat().st_size > MAX_READ or not path.resolve().is_relative_to(root):
                    continue
            except OSError:
                continue
            seen += 1
            if seen > MAX_FILES:
                return
            yield path.relative_to(root).as_posix(), path


def project_map(workspace):
    root = root_of(workspace)
    files = list(_files(workspace))
    names = [name for name, _ in files]
    languages = Counter(p.suffix.lower() or '[no extension]' for _, p in files)
    signals = []
    for marker, label in [('pyproject.toml', 'Python project'), ('package.json', 'JavaScript/TypeScript'),
                          ('Cargo.toml', 'Rust'), ('src-tauri/tauri.conf.json', 'Tauri'),
                          ('go.mod', 'Go'), ('requirements.txt', 'Python dependencies'),
                          ('tests', 'Tests directory')]:
        if (root / marker).exists():
            signals.append(label)
    # Keep useful source entry points and test paths near the front.
    def rank(path):
        base = Path(path).name
        return (0 if base in MANIFESTS else 1 if path.startswith(('src/', 'app/', 'tests/', 'test/')) else 2,
                path.count('/'), path)
    return {'workspace': str(root), 'language_files': dict(languages.most_common(12)),
            'signals': signals, 'files': sorted(names, key=rank)[:160],
            'files_scanned': len(files), 'truncated': len(files) >= MAX_FILES}


def search_code(workspace, phrase, max_hits=25):
    if not isinstance(phrase, str) or not 2 <= len(phrase) <= 150:
        raise ValueError('Search must be a literal phrase between 2 and 150 characters')
    if not isinstance(max_hits, int) or not 1 <= max_hits <= 80:
        raise ValueError('max_hits must be 1..80')
    hits = []
    for filename, _ in _files(workspace):
        # Respect the existing allowlist/path boundary on every read.
        try:
            body = read_text(workspace, filename)
        except (ValueError, OSError, UnicodeDecodeError):
            continue
        for num, line in enumerate(body.splitlines(), 1):
            if phrase.lower() in line.lower():
                # Skip credential-bearing lines as an extra defence in depth.
                if re.search(r'(?i)(api[_-]?key|password|secret|token)\s*[:=]\s*[\'\"]?[^\s$]{6,}', line):
                    continue
                hits.append({'file': filename, 'line': num, 'text': line[:300]})
                if len(hits) >= max_hits:
                    return {'hits': hits, 'truncated': True}
    return {'hits': hits, 'truncated': False}
