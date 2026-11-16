"""Fast literal filename/folder lookup. Metadata only; no LLM or file contents."""
from __future__ import annotations
from contextlib import closing
from pathlib import Path
import re
import sqlite3
import sys
from launcher.nlu import clean
from computer_control.safety.policy import sensitive


def enable_for_request(policy):
    """A direct user request to search the device authorizes name indexing."""
    if sys.platform!='win32' or not policy.enabled or not getattr(policy,'direct_commands',False):return
    from services import device_index
    cfg=device_index.settings()
    if not cfg['enabled']:
        device_index.configure(enabled=True,all_local_drives=True,content_enabled=False)
    if device_index.status()['status'] in ('idle','failed'):
        device_index.refresh(policy.allowed_folders)


def indexed_names(query:str,kind:str,allowed_roots=())->list[dict]:
    from services import device_index
    from core.paths import state_file
    if not device_index.settings()['enabled']:return []
    path=state_file('device_index.sqlite3')
    if not path.is_file():return []
    try:
        with closing(sqlite3.connect(str(path),timeout=.1)) as db:
            rows=db.execute('SELECT path,name,modified FROM files WHERE kind=? AND name=? COLLATE NOCASE LIMIT 30',(kind,query.strip())).fetchall()
        if not rows:
            with closing(sqlite3.connect(str(path),timeout=.1)) as db:
                needle=query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
                rows=db.execute("SELECT path,name,modified FROM files WHERE kind=? AND name LIKE ? ESCAPE '\\' LIMIT 100",(kind,'%'+needle+'%')).fetchall()
        result=[]
        for raw,name,modified in rows:
            p=Path(raw)
            if sensitive(raw) or clean(query) not in clean(p.name):continue
            if not allowed_roots or not device_index._safe_path_in_roots(p,[Path(root) for root in allowed_roots]):continue
            if (p.is_dir() if kind=='folder' else p.is_file()):
                result.append({'kind':kind,'label':p.name,'path':str(p.resolve(strict=True)),'mtime':modified,'score':1.0 if (clean(p.name)==clean(query) or (kind=='file' and not Path(query).suffix and clean(p.stem)==clean(query))) else .8})
        return result
    except (OSError,sqlite3.DatabaseError,ValueError):return []


def query_from_request(text:str)->tuple[str,str]|None:
    from voice.intent import command_target, command_text, non_executable
    if not isinstance(text,str) or len(text)>500 or non_executable(text):return None
    words=command_text(text).split()
    if not words or words[0] not in ('دور','ابحث','فتش','شوف','هات','فين','find','search'):
        return None
    target=re.sub(r'^(?:على|علي|ع|عن|for)\s+','',command_target(text),flags=re.I)
    kind_match=re.match(r'^(?:ال)?(ملف|فايل|فولدر|مجلد|file|folder)\s+',target,re.I)
    local_suffix=r'\s+(?:(?:على|علي|ع|في|جوا|داخل)\s+(?:ال)?(?:جهاز|كمبيوتر|هارد)\w*|عندي)[.؟]?$'
    if not kind_match and not re.search(local_suffix,target,re.I):return None
    kind='item'
    if kind_match:
        kind='folder' if kind_match[1].casefold() in ('فولدر','مجلد','folder') else 'file'
        target=target[kind_match.end():]
    query=re.sub(r'^(?:باسم|اسمه|اسمو|named|called)\s+','',target,flags=re.I)
    query=re.sub(local_suffix,'',query,flags=re.I).strip(' \"\'')
    return (kind,query) if 1<len(query)<=240 else None


def search_request(text:str,*,source='text')->dict:
    parsed=query_from_request(text)
    if parsed is None:return {'matched':False}
    from computer_control.api import load_policy
    from launcher.api import resolver
    policy=load_policy()
    if not policy.enabled:return {'matched':True,'status':'disabled','message':'فعّل إذن التحكم في الكمبيوتر مرة واحدة للبحث في الأسماء.'}
    enable_for_request(policy)
    kind,query=parsed
    r=resolver();r.policy=policy
    results=[r.resolve('افتح '+('فولدر ' if target=='folder' else 'ملف ')+query,source) for target in (('folder','file') if kind=='item' else (kind,))]
    candidates=[candidate for result in results if result for candidate in result.candidates][:10]
    result=next((result for result in results if result),None)
    lines=['لقيت الأسماء دي في الجهاز:'] if candidates else [result.text_ar if result else 'البحث لم يرجع نتيجة مؤكدة.']
    for number,item in enumerate(candidates,1):lines.append(f"{number}. {item['label']} — {item['path_or_appid']}")
    return {'matched':True,'status':'ok' if candidates else 'not_found','message':'\n'.join(lines),
            'candidates':candidates,'cards':[{'label':item['label'],'kind':item['kind'],'id':item['id'],'description':item['path_or_appid']} for item in candidates]}
