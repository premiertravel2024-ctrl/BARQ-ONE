"""Deterministic, fail-closed policy for user-owned machine automation.

Never let model-supplied risk labels or prompt text override these rules.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
import os, re, shlex, time

class Risk(str,Enum):
    LOW='low'; MEDIUM='medium'; HIGH='high'; BLOCKED='blocked'
class Mode(str,Enum):
    OBSERVE='observe'; ASK='ask-always'; SMART='smart'; TRUSTED='trusted'
class Decision(str,Enum):
    ALLOW='auto'; ASK='ask'; BLOCK='blocked'

READ={'read_screen','observe','list_windows','list_processes','list_dir','read_file','search_files','get_system_info','take_screenshot','clipboard_get','wait_for','get_volume','get_brightness','list_apps','find_ui_elements'}
LOW={'office_document','open_app','open_file','open_folder','focus_window','minimize_window','maximize_window','switch_window','scroll','hover','open_windows_settings'}
MED={'click','double_click','drag','type_text','paste','press_key','hotkey','create_dir','write_file','append_file','copy','rename','open_url','set_volume','set_brightness'}
HIGH={'move','delete','run_command','close_window','close_app','open_with','clipboard_set','browser_fill','browser_submit','download_file','notify','invoke_ui','set_ui_text'}
SUPPORTED=READ|LOW|MED|HIGH
SENSITIVE_DIRS=('appdata','windows','system32','program files','.ssh','.aws','.gnupg','.config/google-chrome',
                'user data','cookies','login data','keychain','wallet','credentials','credential','password','secrets',
                '.env','id_rsa','id_ed25519','tokens','credential manager','browser profile')
# Defense-in-depth. A regex blocklist cannot understand every obfuscation; command
# execution therefore ALWAYS requires user approval, with an exact command preview.
BLOCKED_COMMAND_PATTERNS=(
    r'(?i)\b(format|diskpart|mkfs|fdisk|parted|bcdedit|bootrec)\b',
    r'(?i)\b(reg\s+(add|delete)|set-mppreference|remove-mppreference|netsh\s+advfirewall|disable-windowsdefender)\b',
    r'(?i)\b(wevtutil|vssadmin\s+delete|wbadmin\s+delete|cipher\s+/w)\b',
    r'(?i)(encodedcommand|frombase64string|invoke-expression|\biex\s*\(|\biex\s+|\|\s*iex\b)',
    r'(?i)\b(rm\s+-[rf]{1,2}\b|remove-item\b.*-recurse.*-force|del\s+/[sq])',
    r'(?i)(schtasks\s+/(create|change)|new-scheduledtask|currentversion\\run\\|startup\\)',
    r'(?i)\b(bitlocker|manage-bde|icacls\s+.*\s+/grant\s+everyone)\b',
    r'(?i)(\\windows\\system32|/etc/shadow|\.ssh[/\\]|\.aws[/\\])',
    r'(?i)(curl|wget|invoke-webrequest).*(\|\s*(sh|bash|powershell|pwsh)|\|\s*iex)',
)
SUSPICIOUS_INJECTION=re.compile(r'(?i)(ignore\s+(all\s+)?previous\s+instructions|<\s*/?system\s*>|\bsend\s+(all\s+)?files?\s+to\b|developer\s+message\s*:|تجاهل\s+التعليمات|ارسل\s+الملفات\s+الى)')
SECRET=re.compile(r'(?i)(sk-[a-z0-9_\-]{16,}|AIza[0-9A-Za-z_\-]{20,}|gh[opsu]_[0-9a-zA-Z]{20,}|(?:(?:api[_-]?key|password|token|secret)\s*[:=]\s*)[^\s,;}]{5,})')

def redact(text:str)->str:
    return SECRET.sub('[REDACTED]', text or '')

def resolve_path(path:str)->Path:
    if not path or '\x00' in path:raise ValueError('Invalid path')
    return Path(os.path.expandvars(path)).expanduser().resolve(strict=False)

def contained(path:str, roots:list[str])->bool:
    p=resolve_path(path)
    for folder in roots:
        try:p.relative_to(resolve_path(folder));return True
        except ValueError:pass
    return False

def sensitive(path:str)->bool:
    p=resolve_path(path)
    text=str(p).replace('\\','/').lower()
    # Check exact path *components* for protected OS folders. A broad substring
    # match for "appdata" incorrectly blocked pytest's Windows temp workspace
    # (%LOCALAPPDATA%\\Temp) even if it was explicitly allowlisted.
    # This is NOT a general AppData exemption: everything except the temporary
    # subtree stays blocked, including Windows credential and browser stores.
    parts=tuple(part for part in text.split('/') if part)
    if any(part in {'windows','system32','program files','program files (x86)'} for part in parts):
        return True
    for idx,part in enumerate(parts):
        if part=='appdata' and parts[idx+1:idx+3]!=('local','temp'):
            return True
    # Deny known credential locations/files even under an allowlisted folder,
    # including a sensitive path placed underneath the temporary directory.
    markers=tuple(marker for marker in SENSITIVE_DIRS if marker not in {
        'appdata','windows','system32','program files'})
    return any(marker in text for marker in markers)

@dataclass
class Policy:
    enabled:bool=False  # Fail-closed until user explicitly opts in via Settings.
    mode:Mode=Mode.SMART
    allowed_folders:list[str]=field(default_factory=lambda:[str(Path.home()/'AgentWorkspace')])
    direct_commands:bool=False
    local_only_vision:bool=True
    max_steps:int=40
    max_seconds:int=600
    max_failures:int=3
    max_files:int=20
    actions_per_second:float=4.0
    approval_seconds:int=60
    screenshot_retention:bool=False
    sandbox:bool=False
    # External file upload is never implicit even in trusted mode.
    def evaluate(self,tool:str,args:dict[str,Any])->tuple[Risk,Decision,str]:
        if tool not in SUPPORTED:return Risk.BLOCKED,Decision.BLOCK,'Unsupported tool'
        if tool in READ:risk=Risk.LOW
        elif tool in LOW:risk=Risk.LOW
        elif tool in MED:risk=Risk.MEDIUM
        else:risk=Risk.HIGH
        if tool=='office_document':
            from computer_control.tools.office import validate_request
            try:validate_request(args)
            except (ValueError,TypeError):return Risk.BLOCKED,Decision.BLOCK,'Invalid Office request'
        if tool in {'set_volume','set_brightness'}:
            level=args.get('percent')
            if type(level) is not int or not 0<=level<=100:
                return Risk.BLOCKED,Decision.BLOCK,'Level must be an integer from 0 to 100'
        if tool=='open_windows_settings' and args.get('page') not in {
            'display','sound','bluetooth','network','apps','microphone','windowsupdate',
        }:
            return Risk.BLOCKED,Decision.BLOCK,'Unknown Windows Settings page'
        # sensitive paths blocked on both reads and writes
        for key in ('path','src','dst','cwd','app'):
            value=args.get(key)
            if isinstance(value,str) and value and (key!='app' or '/' in value or '\\' in value):
                if sensitive(value):return Risk.BLOCKED,Decision.BLOCK,'Sensitive/system/credential path'
        # no recursive directory deletion; all deletions are to Trash
        if tool in ('write_file','append_file') and args.get('path') and resolve_path(str(args['path'])).exists():
            risk=Risk.HIGH
            try:
                from execution.grants import GrantStore
                if GrantStore().permits(str(args['path']),'write'):
                    risk=Risk.MEDIUM
            except (OSError,ValueError):
                pass
        if tool=='delete' and args.get('permanent'):
            return Risk.BLOCKED,Decision.BLOCK,'Permanent deletion forbidden'
        if tool=='open_app' and args.get('appid') and not re.fullmatch(r'[A-Za-z0-9_.!\-]{1,250}',str(args['appid'])):
            return Risk.BLOCKED,Decision.BLOCK,'Invalid AppUserModelId'
        if tool=='open_app' and (any(word in str(args).lower() for word in ('powershell','cmd.exe','wscript','cscript','regedit','mshta','rundll32')) or str(args.get('name') or args.get('path') or '').lower().endswith(('.exe','.bat','.cmd','.ps1','.vbs'))):
            risk=Risk.HIGH
        # A voice command cannot imply consent to run an executable or script.
        dangerous=('.exe','.bat','.cmd','.ps1','.vbs','.msi','.msp','.js','.jse','.vbe','.wsf','.wsh','.hta','.scr','.com','.pif','.lnk','.jar','.reg','.dll','.cpl','.appx','.msix','.appinstaller','.py')
        if tool in ('open_file','open_folder','open_app','open_with'):
            dest=str(args.get('path') or args.get('name') or '')
            if dest.lower().endswith(dangerous):risk=Risk.HIGH
            if dest.startswith('\\\\') or dest.startswith('//'):risk=Risk.HIGH
            # Opening a normal local file or folder is a read-style action.
            # Script, executable, UNC and removable drive checks above/below
            # still require approval; restricted paths remain blocked.
            if tool in ('open_file','open_folder') and dest and os.name=='nt':
                try:
                    import ctypes
                    anchor=Path(dest).anchor
                    if anchor and ctypes.windll.kernel32.GetDriveTypeW(anchor)==2:risk=Risk.HIGH
                except (OSError,ValueError,AttributeError):risk=Risk.HIGH

        if tool=='run_command':
            command=args.get('cmd','')
            if not isinstance(command,str) or not command.strip():return Risk.BLOCKED,Decision.BLOCK,'Empty command'
            if len(command)>1200:return Risk.BLOCKED,Decision.BLOCK,'Command too long to review'
            if any(re.search(p,command) for p in BLOCKED_COMMAND_PATTERNS):return Risk.BLOCKED,Decision.BLOCK,'Blocked destructive or obfuscated command'
        if tool in {'open_url','download_file'}:
            url=str(args.get('url',''))
            if url and not url.startswith(('https://','http://')):return Risk.BLOCKED,Decision.BLOCK,'Unsafe URL scheme'
        if tool in {'read_file','list_dir','search_files','write_file','append_file','create_dir','copy','move','rename','delete'}:
            targets=[str(args[k]) for k in ('path','dst','src') if args.get(k)]
            if not targets:return Risk.BLOCKED,Decision.BLOCK,'No target path'
            # A user-enabled assistant may read non-sensitive files in other
            # folders. Writes remain scoped to explicitly approved workspaces.
            # The credential/system-path gate still applies to EVERY action.
            if tool not in {'read_file','list_dir','search_files'}:
                if any(not contained(t,self.allowed_folders) for t in targets):
                    from execution.grants import GrantStore
                    scope={'write_file':'write','append_file':'write',
                           'create_dir':'create','copy':'create',
                           'move':'write','rename':'write','delete':'write'}.get(tool,'write')
                    store=GrantStore()
                    if not all(store.permits(t,scope) for t in targets):risk=Risk.HIGH
        if tool in {'click','double_click'} and (not args.get('element_id') or not args.get('signature')):
            risk=Risk.HIGH # unanchored/stale targets may hit dangerous UI controls
        if tool in {'click','double_click','invoke_ui','set_ui_text'} and re.search(
            r'(?i)(send|submit|publish|delete|pay|purchase|confirm|login|ارسال|ارسل|حذف|شراء|دفع|تأكيد)',
            str(args.get('_ui_target_label') or args.get('target_name') or '')):
            risk=Risk.HIGH
        if tool in {'click','double_click','hotkey','type_text','paste'} and any(word in str(args).lower() for word in ('send','submit','purchase','payment','pay','login','password','buy','شراء','دفع','ارسال')):
            risk=Risk.HIGH
        if tool in {'browser_submit','download_file','browser_fill','clipboard_get'}:
            # No automatic remote transmissions from agent-generated instructions
            risk=Risk.HIGH
        if self.mode==Mode.OBSERVE and tool not in READ:return risk,Decision.BLOCK,'Observe mode is read-only'
        if risk==Risk.BLOCKED:return risk,Decision.BLOCK,'Blocked'
        if self.direct_commands:return risk,Decision.ALLOW,'User-enabled direct execution'
        if self.mode==Mode.ASK:return risk,Decision.ASK,'Ask-always mode'
        if self.mode==Mode.TRUSTED:
            if tool in {'open_file','open_app','open_folder'} and risk==Risk.HIGH:
                return risk,Decision.ASK,'Launch requires on-screen approval'
            if tool in {'run_command','browser_submit','download_file','invoke_ui','set_ui_text',
                        'delete','close_app','clipboard_set'} or (risk==Risk.HIGH and tool in {'click','double_click','type_text','paste','hotkey'}):
                return risk,Decision.ASK,'Sensitive interaction requires explicit on-screen approval'
            return risk,Decision.ALLOW,'Trusted mode: sandbox recommended'
        if risk==Risk.HIGH:return risk,Decision.ASK,'High-risk action'
        return risk,Decision.ALLOW,'Workspace-safe action'

@dataclass
class Approval:
    id:str; task_id:str; tool:str; args:dict; reason:str; expires_at:float; approved:bool|None=None
    def valid(self, now:float|None=None)->bool:
        return self.approved is None and (time.time() if now is None else now)<self.expires_at

def untrusted_block(s:str)->str:
    """Tag untrusted observations. Tagging complements, not replaces, the safety gate."""
    s=redact(s[:12000]).replace('</untrusted>','&lt;/untrusted&gt;')
    return '<untrusted>\n'+s+'\n</untrusted>'
