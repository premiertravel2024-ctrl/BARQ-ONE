"""Inspect project dependencies and optionally verify versions against official registries.

No install/update/execution, no package scripts, no arbitrary network addresses.
Only requirements.txt and package.json in the selected workspace are inspected.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from services.public_hub import lookup


def _inside_project(workspace: str) -> Path:
    root=Path(workspace).expanduser().resolve()
    if not root.is_dir(): raise ValueError('Workspace directory does not exist')
    return root


def scan(workspace: str, verify_latest: bool = False, limit: int = 12) -> dict:
    root=_inside_project(workspace)
    packages=[]
    notes=[]
    req=root/'requirements.txt'
    if req.is_file() and not req.is_symlink():
        if req.stat().st_size > 128_000: notes.append('requirements.txt is unusually large; skipped')
        else:
            for line in req.read_text(encoding='utf-8-sig',errors='replace').splitlines():
                value=line.split('#',1)[0].strip()
                # Do not resolve recursive requirements, network URLs, editable installs or VCS.
                if not value or value.startswith(('-', '.', '/', 'git+', 'https:')):continue
                m=re.fullmatch(r'([a-zA-Z0-9][a-zA-Z0-9_.-]*)(?:\[[^\]]+\])?\s*([><!=~]{1,2}\s*[^;\s]+)?(?:\s*;.*)?',value)
                if not m:continue
                packages.append({'ecosystem':'pypi','package':m.group(1),'declared':m.group(2) or 'unpinned', 'source':'requirements.txt'})
    pkg=root/'package.json'
    if pkg.is_file() and not pkg.is_symlink():
        if pkg.stat().st_size > 128_000:notes.append('package.json is unusually large; skipped')
        else:
            try:
                data=json.loads(pkg.read_text(encoding='utf-8-sig'))
                for section in ('dependencies','devDependencies'):
                    deps=data.get(section,{}) if isinstance(data,dict) else {}
                    if isinstance(deps,dict):
                        for name,version in deps.items():
                            if (isinstance(name,str) and isinstance(version,str) and
                                len(name)<=120 and len(version)<=100 and
                                re.fullmatch(r'(?:@[a-zA-Z0-9][\w.-]*/)?[a-zA-Z0-9][\w.-]*',name)):
                                packages.append({'ecosystem':'npm','package':name,'declared':version,'source':'package.json'})
            except ValueError:notes.append('package.json could not be parsed')
    packages=packages[:min(max(limit,1),60)]
    if verify_latest:
        # Limit external calls; users opt in, failure is visible rather than fatal.
        for entry in packages[:5]:
            result=lookup(entry['ecosystem'],entry['package'])
            entry['registry_status']=result['status']
            if result.get('status')=='ok':
                entry['latest']=result['data'].get('latest_version')
                if result['data'].get('deprecated'):
                    entry['deprecated']=result['data']['deprecated']
            else:entry['registry_message']=result.get('message')
    return {'project':str(root),'packages':packages,'notes':notes,
            'read_only':True,'online_checks':min(5,len(packages)) if verify_latest else 0}
