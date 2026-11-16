"""Read-only repository health report, without running repository instructions.

Provides a cheap deterministic first pass before an expensive LLM interaction.
Manifest scripts are reported as data, never executed.
"""
import json
from pathlib import Path
from coding.context import _files, project_map
from coding.quality import source_check
from workspace.manager import read_text, root_of


def diagnose(workspace):
    root = root_of(workspace)
    mapped = project_map(workspace)
    files = list(_files(workspace))
    names = {relative for relative,_ in files}
    python = [name for name,_ in files if name.endswith('.py')]
    py_tests = sorted(n for n in python if Path(n).name.startswith('test_') or n.endswith('_test.py'))
    js_tests = sorted(n for n in names if n.endswith(('.test.js','.spec.js','.test.ts','.spec.ts','.test.tsx','.spec.tsx')))
    issues = []
    warnings = []
    reviewed = 0
    for name in python[:90]:
        try:
            report = source_check(name,read_text(workspace,name))
        except (OSError,ValueError,UnicodeError):
            continue
        reviewed += 1
        if report['errors']:
            issues.append({'file':name,'errors':report['errors'][:2],'line':report.get('line')})
        if len(issues)>=12:
            break
    scripts = {}
    if 'package.json' in names:
        try:
            package=json.loads(read_text(workspace,'package.json'))
            scripts={str(k)[:70]:str(v)[:180] for k,v in package.get('scripts',{}).items() if isinstance(v,str)}
        except (ValueError,TypeError,AttributeError):
            warnings.append('package.json is not valid JSON')
    if not py_tests and not js_tests:
        warnings.append('No conventional Python or JS test files detected (custom tests may still exist)')
    if py_tests:
        warnings.append('Running Python tests executes repository code; user confirmation required')
    if not any(x in names for x in ('README.md','README.rst','README.txt')):
        warnings.append('No root README found')
    suggested = []
    if py_tests:
        suggested.append('Python: python -m pytest -q (approval required)')
    for key in ('test','lint','typecheck','build'):
        if key in scripts:
            suggested.append(f'package.json script: {key} (inspect before running)')
    return {'workspace':str(root), 'project':mapped, 'test_files':(py_tests+js_tests)[:45],
            'python_files_checked':reviewed, 'syntax_errors':issues,
            'package_scripts':scripts, 'suggested_checks':suggested,
            'warnings':warnings, 'scanning_limits':{'source_files':450,'python_syntax_checks':90}}
