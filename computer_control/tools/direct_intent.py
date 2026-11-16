"""Resolve exact user commands without asking a planner to invent arguments."""
from __future__ import annotations

from pathlib import Path, PureWindowsPath
import re

from voice.intent import command_target, command_text, is_multi_step, non_executable, setting_request

_FOLDERS = {
    'سطح المكتب':'desktop', 'ديسكتوب':'desktop', 'الديسكتوب':'desktop', 'desktop':'desktop',
    'documents':'documents', 'my documents':'documents', 'المستندات':'documents',
    'مجلد المستندات':'documents', 'downloads':'downloads', 'التنزيلات':'downloads',
    'التحميلات':'downloads', 'مجلد التنزيلات':'downloads',
}
_LOCATIONS = '|'.join(re.escape(name) for name in sorted(_FOLDERS,key=len,reverse=True))
_CREATE = re.compile(r'(?P<name>.+?)\s+(?:على|علي|في|داخل|جوه|on|in)\s+(?:(?:the|my)\s+)?(?P<root>'+_LOCATIONS+r')',re.I)
_FOLDER = r'(?:مجلد|فولدر|folder|directory)'
_NAMED = r'(?:باسم|بإسم|اسمه|اسمو|named|called)\s+'
_TRANSFER = re.compile(r'"([^"\r\n]+)"\s+(?:الى|إلى|ل|إلي|الي|to)\s+"([^"\r\n]+)"', re.I)
_TRANSFERS = {'انسخ':'copy','copy':'copy','انقل':'move','move':'move','rename':'rename'}
_WINDOW_ACTIONS = {'اقفل':'close_window','قفل':'close_window','close':'close_window',
                   'صغر':'minimize_window','minimize':'minimize_window',
                   'كبر':'maximize_window','maximize':'maximize_window'}

_APP_WINDOWS = {
    'كروم':'Chrome','chrome':'Chrome','جوجل كروم':'Chrome',
    'المفكرة':'Notepad','المفكره':'Notepad','notepad':'Notepad',
    'وورد':'Word','word':'Word','اكسل':'Excel','اكسيل':'Excel','excel':'Excel',
    'الحاسبة':'Calculator','الحاسبه':'Calculator','calculator':'Calculator',
}


def _absolute(path: str) -> bool:
    return Path(path).is_absolute() or PureWindowsPath(path).is_absolute()


def valid_windows_name(name: str) -> bool:
    return (0<len(name)<=120 and not name.startswith(' ') and not name.endswith((' ','.'))
            and not re.search(r'[<>:"/\\|?*\x00-\x1f]',name) and not PureWindowsPath(name).is_reserved())


def direct_action(goal: str) -> tuple[str, dict] | None:
    """Only match supported single actions with a target supplied by the user."""
    if len(goal)>500 or any(c in goal for c in '\r\n\x00') or non_executable(goal):
        return None
    value = command_text(goal)
    if not value or is_multi_step(value):
        return None
    verb, _, rest = value.partition(' ')
    if not rest:
        return None
    setting = setting_request(goal)
    if setting and not setting.get('error') and setting['action'] in ('get','set'):
        action = setting['action']
        return f"{action}_{setting['setting']}", {'percent':setting['percent']} if action=='set' else {}
    target = command_target(goal)
    if verb in ('انشئ','اعمل','create','mkdir'):
        match = re.fullmatch(r'(?:(?:a|an)\s+)?'+_FOLDER+r'\s+(.+)', target, re.I)
        if not match:
            return None
        path = re.sub('^'+_NAMED, '', match[1], flags=re.I).strip()
        if _absolute(path.removeprefix('"').removesuffix('"')) and ('"' not in path or re.fullmatch(r'"[^"]+"',path)):
            return 'create_dir', {'path':path.removeprefix('"').removesuffix('"')}
        match = _CREATE.fullmatch(path)
        if not match:
            reverse=re.fullmatch(r'(?:على|علي|في|داخل|جوه|on|in)\s+(?:(?:the|my)\s+)?(?P<root>'+_LOCATIONS+r')\s+'+_NAMED+r'(?P<name>.+)',path,re.I)
            match=reverse
        if match:
            name=match['name'].strip()
            if name.startswith('"') and name.endswith('"'):
                name=name[1:-1]
            return 'create_dir', {'name':name,'known_folder':_FOLDERS[match['root'].casefold()]}
    rename=verb=='rename' or verb=='غير' and rest.startswith('اسم ')
    if rename or verb in _TRANSFERS:
        if verb=='غير':
            target=re.sub(r'^اسم\s+', '', target, flags=re.I)
        target = re.sub(r'^(?:الملف|ملف|file)\s+', '', target, flags=re.I)
        match = _TRANSFER.fullmatch(target)
        if match and _absolute(match[1]):
            src,dst=match.groups()
            if rename and not _absolute(dst):
                path_type=PureWindowsPath if PureWindowsPath(src).is_absolute() else Path
                source=path_type(src)
                if not source.name or not valid_windows_name(dst):
                    return None
                dst=str(source.with_name(dst))
            if _absolute(dst):
                return ('rename' if rename else _TRANSFERS[verb]), {'src':src,'dst':dst}
    if verb in _WINDOW_ACTIONS:
        # Close a uniquely identified window, never terminate an entire process.
        match = re.fullmatch(r'(?:نافذة|نافذه|الشباك|window|برنامج|تطبيق)\s+(?:باسم\s+|اسمها\s+)?(.+)', target, re.I)
        name = match[1].strip('"') if match else ''
        title = _APP_WINDOWS.get(name.casefold() or rest, name)
        if 2<=len(title)<=120:
            return _WINDOW_ACTIONS[verb], {'title':title}
    return None
