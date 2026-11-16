"""Resolve local, explicit folder/copy/open workflows without a planning model."""
from __future__ import annotations

import re
from pathlib import Path

from computer_control.tools.direct_intent import (
    _FOLDERS, _LOCATIONS, direct_action, valid_windows_name,
)
from voice.intent import command_text, non_executable

_BOUNDARY = re.compile(
    r'(?:\s*[,،;؛]\s*|\s+(?:وبعدين|ثم|بعد كده|and then|then)\s+|\s+و\s*)'
    r'(?=(?:و\s*)?(?:افتح|انسخ|open|copy)\b)', re.I)
_FOLDER_REFERENCE = r'(?:الفولدر|المجلد)(?:\s+(?:اللي عملناه|اللي عملته|الجديد))?'
_DESTINATION = r'(?:فيه|في\s+'+_FOLDER_REFERENCE+r'|into it|to it)'
_SOURCE = re.compile(
    r'(?:انسخ|copy)\s+(?:ملف\s+|الملف\s+|file\s+)?(?P<name>.+?)\s+'
    r'(?:من|from)\s+(?P<root>'+_LOCATIONS+r')\s+'+_DESTINATION,
    re.I)
_COPY_FIRST = re.compile(r'انسخ\s+'+_DESTINATION+r'\s+(.+)', re.I)
_OPEN = re.compile(r'(?:افتح\s+'+_FOLDER_REFERENCE+r'|open (?:it|the folder))',re.I)


def direct_sequence(goal: str) -> list[tuple[str,dict]] | None:
    if len(goal)>800 or any(c in goal for c in '\r\n\x00') or non_executable(goal):
        return None
    # Quoted paths and filenames can contain command-like words.
    if goal.count('"')%2:
        return None
    parts=[]
    start=0
    for boundary in _BOUNDARY.finditer(goal):
        if goal.count('"',0,boundary.start())%2==0:
            parts.append(goal[start:boundary.start()])
            start=boundary.end()
    parts.append(goal[start:])
    if not 2<=len(parts)<=3:
        return None
    create=direct_action(parts[0].rstrip(' ،,'))
    if not create or create[0]!='create_dir':
        return None
    actions=[create]
    for index,part in enumerate(parts[1:],1):
        raw=part.strip().rstrip('؟?!')
        raw=re.sub(r'^و\s*(?=افتح|انسخ)','',raw)
        if _OPEN.fullmatch(command_text(raw)) and index==len(parts)-1:
            actions.append(('open_folder',{}))
            continue
        if index!=1:
            return None
        reordered=_COPY_FIRST.fullmatch(raw)
        if reordered:
            raw='انسخ '+reordered[1]+' فيه'
        source=_SOURCE.fullmatch(raw)
        if not source:
            return None
        name=source['name'].strip()
        if name.startswith('"') and name.endswith('"'):
            name=name[1:-1]
        if not valid_windows_name(name):
            return None
        actions.append(('copy',{'name':name,'source_folder':_FOLDERS[source['root'].casefold()]}))
    return actions


def resolve_sequence(actions: list[tuple[str,dict]], resolve_create) -> list[tuple[str,dict]]:
    from execution.known_folders import known_folder

    create=resolve_create(actions[0])
    folder=Path(create[1]['path'])
    resolved=[create]
    for tool,args in actions[1:]:
        if tool=='copy':
            src=known_folder(args['source_folder'])/args['name']
            resolved.append((tool,{'src':str(src),'dst':str(folder/src.name)}))
        else:
            resolved.append((tool,{'path':str(folder)}))
    return resolved


def identify_source(args: dict) -> dict:
    """Resolve an extension-free exact name only when a single local file matches."""
    from computer_control.safety.policy import sensitive
    import os

    requested=Path(args['src'])
    if requested.suffix or requested.exists() or sensitive(str(requested)):
        return args
    matches=[]
    with os.scandir(requested.parent) as entries:
        for index,entry in enumerate(entries):
            if index>=4096:
                raise ValueError('المجلد فيه ملفات كتير. اكتب اسم الملف بالامتداد عشان أحدده.')
            if Path(entry.name).stem.casefold()!=requested.name.casefold():
                continue
            if entry.is_file(follow_symlinks=False) and not sensitive(entry.path):
                matches.append(entry.name)
                if len(matches)==5:
                    break
    if len(matches)>1:
        names='، '.join(sorted(matches,key=str.casefold))
        raise ValueError('لقيت أكتر من ملف بنفس الاسم. حدّد واحد بالامتداد: '+names)
    if not matches:
        return args
    return {'src':str(requested.with_name(matches[0])),
            'dst':str(Path(args['dst']).with_name(matches[0]))}
