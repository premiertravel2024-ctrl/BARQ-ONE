"""Zero-cost deterministic checks for proposed source changes.

Checks do not execute the proposed code, invoke arbitrary hooks, or consume LLM tokens.
"""
import ast
import json
import tomllib
import re
from pathlib import Path
import yaml


def source_check(path, content):
    ext = Path(path).suffix.lower()
    checks = []
    errors = []
    error_line = None
    if '\x00' in content:
        errors.append('NUL bytes are not valid in source text')
    parsed_python = None
    if ext == '.py':
        try:
            parsed_python = ast.parse(content, filename=path)
            checks.append('Python syntax: valid')
        except (SyntaxError, ValueError) as exc:
            error_line = getattr(exc,'lineno',None)
            errors.append(f'Python syntax: {exc}')
    elif ext == '.json':
        try:
            json.loads(content)
            checks.append('JSON syntax: valid')
        except ValueError as exc:
            errors.append(f'JSON syntax: {exc}')
    elif ext == '.toml':
        try:
            tomllib.loads(content)
            checks.append('TOML syntax: valid')
        except (tomllib.TOMLDecodeError, ValueError) as exc:
            errors.append(f'TOML syntax: {exc}')
    elif ext in ('.yaml', '.yml'):
        try:
            yaml.safe_load(content)
            checks.append('YAML syntax: valid')
        except yaml.YAMLError as exc:
            errors.append(f'YAML syntax: {exc}')
    warnings = []
    if parsed_python is not None:
        # Static audit only. These are cautionary warnings, not proof of an exploit.
        for node in ast.walk(parsed_python):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in ('eval','exec'):
                    warnings.append(f'Line {node.lineno}: dynamic Python execution ({node.func.id})')
                if any(arg.arg == 'shell' and isinstance(arg.value, ast.Constant) and arg.value.value is True for arg in node.keywords):
                    warnings.append(f'Line {node.lineno}: shell=True should be reviewed')
            elif isinstance(node, ast.ExceptHandler) and node.type is None:
                warnings.append(f'Line {node.lineno}: bare except catches all exceptions')
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                value = node.value
                if any(isinstance(t, ast.Name) and re.search(r'(?i)(password|secret|api_?key|token)',t.id) for t in targets) \
                    and isinstance(value, ast.Constant) and isinstance(value.value,str) and len(value.value)>=8:
                    warnings.append(f'Line {node.lineno}: possible hardcoded credential')
        warnings = warnings[:24]
    if content and not content.endswith('\n'):
        warnings.append('File does not end with a newline')
    if any(len(line) > 160 for line in content.splitlines()):
        warnings.append('One or more lines exceed 160 characters')
    return {'valid': not errors, 'checks': checks, 'errors': errors, 'warnings': warnings,'line':error_line}
