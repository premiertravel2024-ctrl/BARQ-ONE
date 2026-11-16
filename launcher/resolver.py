"""Purely local matching, policy preview and ephemeral candidate storage. Never executes."""
from __future__ import annotations
from dataclasses import asdict,dataclass,field
from pathlib import Path
from urllib.parse import urlsplit
import re,time,uuid
from computer_control.safety.policy import Policy,Decision,sensitive
from .nlu import parse,clean,LaunchIntent
from .aliases import catalog,alias_target
from .indexes import Index,known_folder

@dataclass
class Candidate:
    id:str
    kind:str
    label:str
    path_or_appid:str
    score:float
    risk:str='low'
    tool:str=''
    args:dict=field(default_factory=dict)
    realpath:str|None=None
    source:str='text'
    created:float=field(default_factory=time.monotonic)

@dataclass
class LaunchResult:
    decision:str
    candidates:list[dict]
    spoken_ar:str
    text_ar:str
    intent:dict|None=None

def _app_identity(label: str, mapping: dict[str, list[str]]) -> str:
    """Canonical app label independent of Windows display language.

    For example, Chrome, Google Chrome and جوجل كروم are one app name;
    vendor prefixes such as Microsoft Word also map to the same key.
    Distinct actual executable paths are *never* collapsed by name alone.
    """
    from computer_control.tools.app_index import normalized_app
    display = clean(label)
    for canonical, variants in mapping.items():
        key = clean(canonical)
        names = {key, *(clean(form) for form in variants)}
        if display in names or (
            key and display.endswith(' ' + key)
            and len(display.split()) <= 3
        ):
            return key
    return normalized_app(label)


def _collapse_app_representations(found: list[tuple[Candidate, Decision]],
                                  aliases: dict[str, list[str]] | None = None) -> list[tuple[Candidate, Decision]]:
    """Treat Start Menu shortcuts, registered AppIDs and the unique EXE as one app.

    Only collapse labels representing the same known application. If two
    distinct executable paths exist, preserve the ambiguity for user choice.
    Retain the selected candidate's original policy decision and executable.
    """
    from computer_control.tools.app_index import normalized_app

    grouped: dict[str, list[tuple[Candidate, Decision]]] = {}
    others: list[tuple[Candidate, Decision]] = []
    for item in found:
        candidate, _ = item
        if candidate.kind != 'app':
            others.append(item)
            continue
        grouped.setdefault(_app_identity(candidate.label, aliases or {}), []).append(item)
    for group in grouped.values():
        if len(group) < 2:
            others.extend(group)
            continue
        executables = {
            obj.path_or_appid.casefold(): item
            for item in group
            for obj in (item[0],)
            if obj.path_or_appid.lower().endswith('.exe')
        }
        # Different real executables, even of the same brand, must not be
        # silently treated as interchangeable.
        if len(executables) > 1:
            others.extend(group)
            continue
        appids = {
            obj.path_or_appid.casefold(): item
            for item in group
            for obj in (item[0],)
            if obj.args.get('appid')
        }
        # AppIDs are OS-registered launch identities, unlike raw executable
        # paths which appropriately require an explicit high-risk approval.
        # Prefer a unique AppID when present; never bypass the policy gate.
        if len(appids) > 1:
            others.extend(group)
            continue
        selected = (next(iter(appids.values())) if len(appids) == 1
                    else next(iter(executables.values())) if len(executables) == 1
                    else None)
        if selected is None:
            others.extend(group)
            continue
        selected[0].score = max(item[0].score for item in group)
        others.append(selected)
    return others


class Resolver:
    def __init__(self,index:Index|None=None,policy:Policy|None=None,app_source=None):
        self.index=index or Index();self.policy=policy or Policy();self.app_source=app_source or self.index.apps
        self._pending={};self._last=[]
    def _new(self,kind,label,path,score,tool,args,source):
        risk,decision,_=self.policy.evaluate(tool,args)
        real=None
        if tool in ('open_file','open_folder','open_app') and (args.get('path') or (args.get('name') or '').endswith('.lnk')):
            p=args.get('path') or args.get('name')
            try:real=str(Path(p).resolve(strict=True))
            except (OSError,ValueError):pass
        obj=Candidate(uuid.uuid4().hex,kind,label,path,round(score,3),risk.value,tool,args,real,source)
        return obj,decision
    def _add(self,found,kind,label,path,score,tool,args,source):
        obj,decision=self._new(kind,label,path,score,tool,args,source)
        if decision!=Decision.BLOCK:found.append((obj,decision))
    def resolve(self,text:str,source:str='text',query_only:bool=False) -> LaunchResult|None:
        from .routines import office_request,LABELS
        routine=office_request('افتح '+text if query_only else text)
        if routine:
            label=('شيت ' if routine['app']=='excel' else 'مستند ')+LABELS[routine['app']]+' جديد' if routine['action']=='new' else LABELS[routine['app']]
            obj,decision=self._new('app',label,'office:'+routine['app'],1.0,'office_document',routine,source)
            if decision==Decision.BLOCK:
                return LaunchResult('blocked',[],'الأمر متوقف بإعدادات التحكم.','الأمر متوقف بإعدادات التحكم.')
            self._pending[obj.id]=obj
            output=[{k:v for k,v in asdict(obj).items() if k in ('id','kind','label','path_or_appid','score','risk')}]
            return LaunchResult('ask_approval' if decision==Decision.ASK else 'auto',output,'جاهز للتنفيذ.','جاهز للتنفيذ.')
        intent=parse('افتح '+text if query_only else text)
        if intent is None or intent.verb!='open':return None
        aliases=catalog();target=clean(intent.target_text)
        literal=intent.target_text
        direct=Path(literal) if Path(literal).is_absolute() else None
        found=[]
        if direct is None:
            from voice.intent import is_multi_step
            if is_multi_step(text):return None  # Preserve the whole task for the executor.
        if direct is not None:
            try:
                if direct.exists():
                    kind='folder' if direct.is_dir() else 'file'
                    self._add(found,kind,direct.name,str(direct),1,'open_folder' if kind=='folder' else 'open_file',{'path':str(direct)},source)
            except OSError:pass
        if direct is None and intent.target_kind in (None,'site'):

            for label,url in (aliases.get('websites') or {}).items():
                if target==clean(label) or target==clean(url):
                    self._add(found,'site',label,url,1,'open_url',{'url':url},source)
            if re.match(r'^https?://[^\s]+$',literal):
                url=literal
                if urlsplit(url).scheme in ('http','https'):
                    self._add(found,'site',url,url,1,'open_url',{'url':url},source)
        if direct is None and intent.target_kind in (None,'folder'):
            for key,names in (aliases.get('known_folders') or {}).items():
                if target in [clean(x) for x in names]:
                    try:
                        folder=known_folder(key)
                        if folder.is_dir() and not sensitive(str(folder)):
                            self._add(found,'folder',folder.name,str(folder),1,'open_folder',{'path':str(folder)},source)
                    except (OSError,ValueError):pass
        if direct is None and intent.target_kind in (None,'app'):
            lookup=alias_target(target,aliases.get('apps') or {})
            canon={name:score for name,score in lookup}
            for entry in self.app_source():
                label=str(entry.get('label',''))
                from difflib import SequenceMatcher
                # Exact Arabic/English alias refers to a canonical installed app.
                # Compare its identity, not only the display-language string.
                identity = _app_identity(label, aliases.get('apps') or {})
                aliases_score = max((value for name, value in canon.items()
                    if identity == clean(name)
                    or clean(label) == clean(name)
                    or clean(label).endswith(' ' + clean(name))), default=0)
                score=max(SequenceMatcher(None,target,clean(label)).ratio(), aliases_score)
                if score<.7:continue
                appid=entry.get('appid');path=entry.get('path')
                if appid:
                    if not re.fullmatch(r'[\w.\-!]+',appid):continue
                    args={'name':label,'appid':appid}
                    self._add(found,'app',label,appid,score,'open_app',args,source)
                elif path and Path(path).is_file():
                    self._add(found,'app',label,str(path),score,'open_app',{'name':str(path)},source)
        # An exact installed-app match should not be made ambiguous by a
        # similarly named document or folder in the general local index.
        # Explicit "ملف" or "مجلد" requests still search those categories.
        exact_app = any(obj.kind == 'app' and obj.score >= 0.999
                        for obj, _ in found)
        if (direct is None and intent.target_kind in (None,'file','folder')
                and (intent.target_kind is not None or not exact_app)):
            if intent.target_kind in ('folder','file'):
                extras=list(self.policy.allowed_folders)
                if self.index.roots is None:
                    from .preferences import load
                    extras.extend(load().get('extra_roots',[]))
                    from services import device_index
                    cfg=device_index.settings()
                    if cfg.get('enabled'):extras.extend(device_index.scan_roots(cfg,extras))
                rows=self.index.find_paths(intent.target_text,kind=intent.target_kind,extra_roots=extras)
            else:
                rows=self.index.search(target,intent.target_kind,intent.ext_hints)
            for row in rows:
                label=row['label'];kind=row['kind'];path=row['path']
                if not Path(path).exists() or (kind=='folder' and not Path(path).is_dir()):continue
                self._add(found,kind,label,path,row['score'],'open_folder' if kind=='folder' else 'open_file',{'path':path},source)
        found = _collapse_app_representations(found, aliases.get('apps') or {})
        found.sort(key=lambda item:-item[0].score)
        # Remove duplicate destinations without arbitrary selection on ties.
        unique=[];seen=set()
        for obj,decision in found:
            if (obj.kind,obj.path_or_appid) in seen:continue
            seen.add((obj.kind,obj.path_or_appid));unique.append((obj,decision))
        self._pending={k:v for k,v in self._pending.items() if time.monotonic()-v.created<90}
        shortlist=unique[:4]
        for obj,_ in shortlist:self._pending[obj.id]=obj
        if not shortlist:
            if intent.target_kind in ('folder','file'):
                detail=self.index.last_folder_search
                text=('البحث المحلي المحدود ماوصلش لاسم الفولدر بالضبط. حدّد القرص أو مكانه لتضييق البحث؛ مش هفتح فولدر شبيه.' if detail.get('truncated') else 'ملقيتش فولدر بالاسم ده في مجلدات البحث المتاحة. حدّد القرص أو المجلد الأب؛ مش هفتح نتيجة شبيهة.')
                if intent.target_kind=='file':text=text.replace('الفولدر','الملف').replace('فولدر','ملف').replace('فولدرات','ملفات')
                return LaunchResult('not_found',[],text,text,asdict(intent))
            return LaunchResult('not_found',[],'مش لاقي الحاجة دي عندك.','مش لاقي نتيجة مطابقة. اكتب المسار الكامل للملف أو المجلد، أو حدّث فهرس الملفات من إعدادات التشغيل بالأمر.',asdict(intent))
        first,gate=shortlist[0]
        if len(shortlist)>1 and ((intent.target_kind=='file' and clean(first.label)!=target) or first.score-shortlist[1][0].score<.12):
            decision='choose';text='لقيت أكتر من نتيجة، اختار واحدة.'
        elif intent.target_kind in ('folder','file') and first.score<1.0:
            decision='choose';text='مفيش تطابق كامل للاسم. دي أسماء قريبة؛ اختار المقصود ومش هفتحها تلقائيًا.'
        elif first.score<.84:
            decision='choose';text='محتاج تختار النتيجة الصح.'
        else:
            decision='ask_approval' if gate==Decision.ASK else 'auto'
            text=('محتاج موافقتك قبل الفتح.' if decision=='ask_approval' else 'تمام، لقيت '+first.label+'.')
        output=[{k:v for k,v in asdict(obj).items() if k in ('id','kind','label','path_or_appid','score','risk')} for obj,_ in shortlist]
        return LaunchResult(decision,output,text,text,asdict(intent))
    def candidate(self,candidate_id:str)->Candidate|None:
        entry=self._pending.get(candidate_id)
        return entry if entry and time.monotonic()-entry.created<90 else None
