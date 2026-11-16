"""Verify that the Windows installer cannot run before frontend and Windows gates.

Uses Python standard library only so this check can run BEFORE npm/venv setup.
Supported GitHub Actions ``needs`` syntaxes: scalar, inline list, block list.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def workflow_job_dependencies(workflow: str, job_name: str) -> set[str]:
    """Read the GitHub Actions 'needs' of exactly one job.

    GitHub Actions accepts either a scalar, an inline list or a block list.
    Release checks must validate *dependencies*, not exact YAML formatting.
    This minimal parser intentionally accepts those three supported forms
    without requiring an additional Python build-time dependency.
    """
    start = re.search(rf'(?m)^  {re.escape(job_name)}:[ \t]*(?:#.*)?$', workflow)
    if start is None:
        return set()
    # Job definitions are indented by two spaces in this checked-in workflow.
    following = workflow[start.end():]
    next_job = re.search(r'(?m)^  [A-Za-z_][\w-]*:[ \t]*(?:#.*)?$', following)
    body = following[:next_job.start()] if next_job else following
    dependency = re.search(r'(?m)^    needs:[ \t]*([^\r\n]*)', body)
    if dependency is None:
        return set()
    value = dependency.group(1).split('#', 1)[0].strip()
    if value.startswith('['):
        value += body[dependency.end():].split(']', 1)[0] if ']' not in value else ''
        return {entry.strip().strip("'\"") for entry in value.strip('[]').split(',') if entry.strip()}
    if value:
        return {value.strip("'\"")}
    # Multi-line mapping: needs: followed by indented '-' list items.
    rest = body[dependency.end():]
    items = []
    for line in rest.splitlines():
        if not line.strip():
            continue
        if not line.startswith('      - '):
            break
        items.append(line.strip()[2:].strip().strip("'\""))
    return set(items)


def verify(workflow: str) -> list[str]:
    errors: list[str] = []
    required = {'frontend-validation', 'windows-early-regressions'}
    for job in required | {'windows-x64'}:
        if re.search(rf'(?m)^  {re.escape(job)}:[ \t]*(?:#.*)?$', workflow) is None:
            errors.append(f'Missing GitHub Actions job: {job}')
    needs = workflow_job_dependencies(workflow, 'windows-x64')
    for dependency in sorted(required - needs):
        errors.append(f'windows-x64 does not require successful job: {dependency}')
    return errors


if __name__ == '__main__':
    import sys
    target = ROOT / '.github/workflows/windows-build.yml'
    problems = verify(target.read_text(encoding='utf-8')) if target.is_file() else [f'Missing {target}']
    if problems:
        for problem in problems:
            print(f'[ERROR] {problem}', file=sys.stderr)
        sys.exit(1)
    print('[PASS] GitHub Actions installer depends on frontend and Windows early gates.')
