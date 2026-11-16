"""GitHub repository import with explicit consent and zero automatic code execution.

Only https://github.com/<owner>/<repo> is accepted. Clone without credentials,
submodules, hooks or global Git configuration. Dependency installation is
separate, staged, and never invokes repository scripts or source builds.
"""
from __future__ import annotations

import asyncio
import io
import json
import stat
import struct
import urllib.request
import zipfile
import os
import re
import shutil
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from core.processes import background_options

PENDING: dict[str, dict] = {}
SAFE_COMPONENT = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?\Z")
MAX_REPO_BYTES = 250 * 1024 * 1024
MAX_ARCHIVE_BYTES = 75 * 1024 * 1024

class RepositoryError(ValueError):
    pass


def parse_url(text: str) -> tuple[str, str, str]:
    if not isinstance(text, str) or len(text) > 2048:
        raise RepositoryError('ابعت رابط مستودع GitHub صالح.')
    text = text.strip().strip('<>\"\'').rstrip('،.؛!؟,;!')
    try:
        url = urlsplit(text)
        path = url.path.strip('/').split('/')
        if url.scheme != 'https' or url.hostname != 'github.com' or url.netloc.lower() != 'github.com' or url.username or url.password or url.query or url.fragment or len(path) != 2:
            raise RepositoryError('الاستيراد متاح لروابط https://github.com/owner/repo فقط.')
        owner, repo = path
        if repo.endswith('.git'):
            repo = repo[:-4]
        if not SAFE_COMPONENT.fullmatch(owner) or not SAFE_COMPONENT.fullmatch(repo) or owner in ('.','..') or repo in ('.','..') or '..' in owner or '..' in repo or owner.startswith('-') or repo.startswith('-'):
            raise RepositoryError('اسم المستودع غير صالح.')
        return owner, repo, f'https://github.com/{owner}/{repo}.git'
    except ValueError as exc:
        if isinstance(exc, RepositoryError):
            raise
        raise RepositoryError('رابط GitHub غير صالح.') from exc


def local_root() -> Path:
    # User-visible code is stored separately from BARQ's installation and secrets.
    return Path.home() / 'BARQ-Projects'


def target_path(owner: str, repo: str) -> Path:
    return local_root() / f'{owner}--{repo}'


def create_preview(url: str) -> dict:
    owner, repo, canonical = parse_url(url)
    target = target_path(owner, repo)
    if target.exists() or target.is_symlink():
        raise RepositoryError('المستودع موجود بالفعل على الجهاز. افتحه من مساحة العمل بدل تنزيل نسخة فوقه.')
    token = uuid.uuid4().hex
    PENDING[token] = {'owner': owner, 'repo': repo, 'url': canonical, 'path': str(target), 'expires': time.monotonic()+600}
    return {'approval_id': token, 'repository': f'{owner}/{repo}', 'url': canonical.replace('.git',''),
            'destination': str(target), 'expires_in_seconds': 600, 'git_ready': True, 'download_mode':'git' if shutil.which('git') else 'github-archive',
            'summary': 'برق هينسخ الملفات فقط في مجلد مشاريع مستقل، ويفحص تعليمات التشغيل. مش هيشغل أي سكربت أو يثبّت اعتماديات من غير موافقة منفصلة.'}


def _git_environment() -> dict:
    env = os.environ.copy()
    env.update(GIT_TERMINAL_PROMPT='0', GIT_CONFIG_NOSYSTEM='1',
               GIT_CONFIG_GLOBAL='NUL' if os.name == 'nt' else os.devnull,
               GIT_LFS_SKIP_SMUDGE='1', GCM_INTERACTIVE='never')
    for key in list(env):
        if key.startswith('GIT_CONFIG_KEY_') or key.startswith('GIT_CONFIG_VALUE_') or key == 'GIT_CONFIG_COUNT':
            env.pop(key, None)
    return env


async def _command(argv: list[str], *, cwd: Path, timeout: int = 120, env: dict | None = None) -> dict:
    prog = shutil.which(argv[0])
    if not prog:
        raise RepositoryError(f'البرنامج {argv[0]} مش متثبت أو مش موجود في PATH.')
    opts = background_options() if os.name == 'nt' else {}
    proc = await asyncio.create_subprocess_exec(prog,*argv[1:],cwd=str(cwd),env=env or _git_environment(),
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,**opts)
    try:
        out, err=await asyncio.wait_for(proc.communicate(),timeout)
    except asyncio.TimeoutError:
        proc.kill();await proc.wait()
        raise RepositoryError(f'العملية تجاوزت المهلة ({timeout} ثانية)، وتم إيقافها.')
    if proc.returncode:
        # Never return embedded tokens, auth prompts, or arbitrary unbounded output.
        raise RepositoryError(f'الأداة {argv[0]} فشلت (كود {proc.returncode}). اتأكد من الإنترنت وصلاحيات المستودع. ' + err.decode(errors='replace')[:220])
    return {'exit_code': 0, 'stdout': out.decode(errors='replace')[:2000]}


class _GithubOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target=urlsplit(newurl)
        if target.scheme!='https' or target.hostname not in ('api.github.com','codeload.github.com') or target.username or target.password or target.port not in (None,443):
            raise RepositoryError('GitHub حاول يحوّل التنزيل إلى مصدر غير معتمد.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def _fetch_github_archive(owner: str, repo: str) -> bytes:
    req=urllib.request.Request(f'https://api.github.com/repos/{owner}/{repo}/zipball',
                               headers={'User-Agent':'BARQ-AI-Repository-Importer','Accept':'application/vnd.github+json'})
    opener=urllib.request.build_opener(_GithubOnlyRedirect())
    try:
        with opener.open(req,timeout=25) as reply:
            data=reply.read(MAX_ARCHIVE_BYTES+1)
    except (OSError, TimeoutError, urllib.error.URLError, ValueError) as exc:
        raise RepositoryError('تعذّر تنزيل المستودع من GitHub الرسمي؛ راجع اتصال الإنترنت أو إذا كان عامًا.') from exc
    if len(data)>MAX_ARCHIVE_BYTES:raise RepositoryError('حجم المستودع المضغوط أكبر من الحد الآمن.')
    return data


def _validate_raw_zip_entry_name(blob: bytes, member: zipfile.ZipInfo) -> None:
    """Reject unsafe bytes before ZipInfo normalizes Windows backslashes.

    On Windows zipfile.ZipInfo changes backslashes to '/', even when reading
    archive names. Validating only member.filename would therefore accept
    a raw backslash-containing ZIP entry that Linux rejects. Read the original
    local-file header name before creating any output directories.
    """
    offset = member.header_offset
    if offset < 0 or offset + 30 > len(blob) or blob[offset:offset + 4] != b'PK\x03\x04':
        raise RepositoryError('ترويسة ZIP غير سليمة.')
    name_length, extra_length = struct.unpack_from('<HH', blob, offset + 26)
    start = offset + 30
    end = start + name_length
    if not name_length or end + extra_length > len(blob):
        raise RepositoryError('اسم ملف ZIP غير صالح.')
    raw = blob[start:end]
    if b'\\' in raw or b'\x00' in raw:
        raise RepositoryError('اسم ZIP يحتوي فواصل Windows غير آمنة.')


def _extract_safe_archive(blob: bytes, target: Path) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            members=archive.infolist()
            if not members or len(members)>12000:raise RepositoryError('عدد ملفات الأرشيف غير آمن.')
            roots={member.filename.split('/')[0] for member in members if member.filename}
            if len(roots)!=1:raise RepositoryError('أرشيف GitHub لا يحتوي على مجلد جذر واحد.')
            total=0
            seen=set()
            windows_seen=set()
            reserved = {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'}
            reserved.update(f'COM{i}' for i in range(1, 10))
            reserved.update(f'LPT{i}' for i in range(1, 10))
            for member in members:
                _validate_raw_zip_entry_name(blob, member)
                parts=member.filename.split('/')
                rel=parts[1:]
                check_parts = rel[:-1] if member.is_dir() else rel
                if len(parts)<2 or any(not part or part in ('.','..') or '\\' in part or ':' in part or len(part)>240 or part[-1] in (' ', '.') for part in check_parts) or member.filename.startswith('/'):
                    raise RepositoryError('اسم ملف غير آمن داخل مستودع GitHub.')
                if any(part.upper().split('.')[0] in reserved for part in check_parts):
                    raise RepositoryError('اسم ملف محجوز في Windows.')
                # NTFS is normally case-insensitive: never let two entries
                # overwrite the same destination on Windows.
                canonical = '/'.join(rel).rstrip('/').casefold()
                if member.filename in seen or canonical in windows_seen:
                    raise RepositoryError('اسم ملف مكرر في الأرشيف.')
                seen.add(member.filename)
                windows_seen.add(canonical)
                if stat.S_IFMT(member.external_attr>>16)==stat.S_IFLNK:
                    raise RepositoryError('الأرشيف يحتوي رابطًا رمزيًا غير موثوق.')
                total+=member.file_size
                if total>MAX_REPO_BYTES:raise RepositoryError('حجم الملفات بعد فك الضغط أكبر من المسموح.')
            target.mkdir(parents=True,exist_ok=False)
            for member in members:
                parts=[p for p in member.filename.split('/')[1:] if p]
                if not parts:continue
                dest=target.joinpath(*parts)
                if not dest.resolve().is_relative_to(target.resolve()):raise RepositoryError('ملف يحاول الخروج من مجلد الاستيراد.')
                if member.is_dir():dest.mkdir(parents=True,exist_ok=True);continue
                dest.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(member) as source, dest.open('wb') as sink:
                    shutil.copyfileobj(source,sink,length=1024*1024)
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise RepositoryError('ملف GitHub المضغوط تالف أو غير قابل للفك.') from exc


def scan_repository(root: Path) -> dict:
    names={p.name for p in root.iterdir() if p.is_file() and not p.is_symlink()}
    def read_short(name: str) -> str:
        p=root/name
        if not p.is_file() or p.is_symlink() or p.stat().st_size>100_000: return ''
        return p.read_text(encoding='utf-8',errors='replace')[:2200]
    kinds=[]; installs=[]; warnings=[]
    if 'package.json' in names:
        kinds.append('Node.js')
        manifest=read_short('package.json')
        try:
            value=json.loads(manifest)
            installs.append('npm ci --ignore-scripts --no-audit --no-fund' if 'package-lock.json' in names else 'npm install --ignore-scripts --no-audit --no-fund')
            if value.get('scripts'): warnings.append('فيه سكربتات package.json؛ برق مش هيشغلها تلقائيًا.')
        except (ValueError, TypeError, AttributeError): warnings.append('ملف package.json محتاج مراجعة.')
    if 'requirements.txt' in names or 'pyproject.toml' in names:
        kinds.append('Python')
        if 'requirements.txt' in names: installs.append('venv + pip install --only-binary=:all: -r requirements.txt (after validating requirements)')
        else: warnings.append('pyproject.toml موجود لكن تثبيت المشروع أو بناؤه مش تلقائي لأنه ممكن يشغّل كود.')
    if 'Cargo.toml' in names: kinds.append('Rust')
    if 'go.mod' in names: kinds.append('Go')
    if 'Dockerfile' in names or 'docker-compose.yml' in names: warnings.append('مش هيتم تشغيل Docker من غير مراجعة مستقلة.')
    total=0
    for base,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=[d for d in dirs if d not in ('.git','node_modules','.venv','target','dist') and not (Path(base)/d).is_symlink()]
        if len(Path(base).relative_to(root).parts)>=4:dirs[:]=[]
        for name in files:
            try:
                p=Path(base)/name
                if p.is_file() and not p.is_symlink(): total+=p.stat().st_size
            except OSError:pass
            if total>MAX_REPO_BYTES:
                warnings.append('حجم ملفات المشروع كبير؛ راجع المستودع قبل الاستخدام.');dirs[:]=[];break
    readme=next((name for name in ('README.md','README.MD','readme.md','README.txt') if name in names),'')
    return {'workspace':str(root),'frameworks':kinds,'suggested_install':installs,
            'readme_excerpt':read_short(readme)[:1600] if readme else '',
            'warnings':warnings,'file_count_top':len(names),'status':'imported_untrusted'}


async def apply_import(approval_id: str, confirmed: bool = False) -> dict:
    if not confirmed:raise RepositoryError('لازم توافق على الاستيراد الأول.')
    item=PENDING.pop(approval_id,None)
    if not item or time.monotonic()>item['expires']:
        raise RepositoryError('الموافقة انتهت. راجع المستودع من جديد.')
    root=local_root();root.mkdir(parents=True,exist_ok=True)
    if root.is_symlink():raise RepositoryError('مجلد المشاريع رابط رمزي وغير مسموح.')
    dest=Path(item['path'])
    if dest.parent.resolve()!=root.resolve() or dest.exists() or dest.is_symlink():
        raise RepositoryError('مجلد الهدف موجود أو غير آمن، مش هنكتب فوقه.')
    temp=root/f'.barq-clone-{uuid.uuid4().hex}'
    try:
        if shutil.which('git'):
            await _command(['git','-c','core.hooksPath='+str(root/'.barq-no-hooks'),
                            'clone','--depth','1','--single-branch','--no-recurse-submodules','--',item['url'],str(temp)],cwd=root,timeout=150)
            if not (temp/'.git').is_dir():raise RepositoryError('Git لم ينشئ مستودعًا محليًا صالحًا.')
            mode='git'
        else:
            blob=await asyncio.to_thread(_fetch_github_archive,item['owner'],item['repo'])
            _extract_safe_archive(blob,temp)
            (temp/'.barq-import.json').write_text(json.dumps({'repository':f"{item['owner']}/{item['repo']}", 'mode':'github-archive'}),encoding='utf-8')
            mode='github-archive'
        data=scan_repository(temp)
        temp.rename(dest)
        data['workspace']=str(dest)
        data['repository']=f"{item['owner']}/{item['repo']}"
        data['installed']=False
        data['cloned']=True
        data['download_mode']=mode
        return data
    finally:
        if temp.exists():shutil.rmtree(temp,ignore_errors=True)


_REQUIREMENT = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[A-Za-z0-9_,.-]+\])?(?:\s*(?:==|>=|<=|~=|!=|>|<)\s*[A-Za-z0-9.*+_-]+)?(?:\s*;\s*python_version\s*[<>=!]+\s*[\"\'][0-9.]+[\"\'])?\Z')

def safe_python_requirements(root: Path) -> bool:
    f=root/'requirements.txt'
    if not f.is_file() or f.is_symlink() or f.stat().st_size>50000:return False
    lines=f.read_text(encoding='utf-8',errors='replace').splitlines()
    return len(lines)<=120 and all(not line.strip() or line.lstrip().startswith('#') or _REQUIREMENT.fullmatch(line.strip()) for line in lines)


def _safe_npm_manifest(root: Path) -> bool:
    manifest = root/'package.json'
    if not manifest.is_file() or manifest.is_symlink() or manifest.stat().st_size > 200_000:
        return False
    try:
        content = json.loads(manifest.read_text(encoding='utf-8'))
        if not isinstance(content,dict):return False
        for section in ('dependencies','devDependencies','optionalDependencies'):
            for name,version in content.get(section,{}).items():
                if not isinstance(name,str) or not isinstance(version,str) or not re.fullmatch(r'[@A-Za-z0-9_.\-/]+',name):return False
                if re.search(r'(?i)(?:git[+:]|https?://|file:|workspace:|link:|\.\./|^\s*-)',version):return False
        lock = root/'package-lock.json'
        if lock.exists():
            if not lock.is_file() or lock.is_symlink() or lock.stat().st_size>8_000_000:return False
            parsed=json.loads(lock.read_text(encoding='utf-8'))
            for entry in parsed.get('packages',{}).values():
                if not isinstance(entry,dict):return False
                resolved=entry.get('resolved','')
                if resolved and (not isinstance(resolved,str) or not resolved.startswith('https://registry.npmjs.org/')):
                    return False
        return True
    except (ValueError,OSError,TypeError,AttributeError):return False


def installation_preview(workspace: str) -> dict:
    root=Path(workspace).resolve()
    base=local_root().resolve()
    if root.parent!=base or not root.is_dir() or root.is_symlink() or not ((root/'.git').is_dir() or (root/'.barq-import.json').is_file()):
        raise RepositoryError('اختار مستودعًا مستوردًا بواسطة برق أولًا.')
    if (root/'package.json').is_file():
        if not _safe_npm_manifest(root):raise RepositoryError('مصادر اعتماديات Node.js غير موثوقة أو ملف القفل غير صالح؛ راجعها يدويًا.')
        tool='npm'; command=['npm','ci' if (root/'package-lock.json').is_file() else 'install', '--ignore-scripts','--no-audit','--no-fund']
    elif safe_python_requirements(root):
        tool='python';command=[sys.executable,'-m','venv',str(root/'.barq-venv')]
    else:raise RepositoryError('المشروع محتاج خطوات تثبيت خاصة؛ برق مش هيشغل تعليمات README أو سكربتات غير موثوقة تلقائيًا.')
    token=uuid.uuid4().hex
    PENDING[token]={'install':True,'path':str(root),'command':command,'tool':tool,'expires':time.monotonic()+600}
    return {'approval_id':token,'workspace':str(root),'tool':tool,'command_preview':command,
            'summary':'تثبيت اعتماديات المشروع فقط؛ npm بدون scripts أو Python wheels في بيئة معزولة. مش هنشغّل المشروع تلقائيًا.'}


async def apply_install(approval_id: str, confirmed: bool = False) -> dict:
    if not confirmed:raise RepositoryError('موافقة تثبيت الاعتماديات مطلوبة.')
    item=PENDING.pop(approval_id,None)
    if not item or not item.get('install') or time.monotonic()>item['expires']:
        raise RepositoryError('موافقة التثبيت غير صالحة أو انتهت.')
    root=Path(item['path']);base=local_root().resolve()
    if root.resolve().parent!=base or not root.is_dir() or root.is_symlink() or not ((root/'.git').is_dir() or (root/'.barq-import.json').is_file()):
        raise RepositoryError('مجلد المشروع غير آمن.')
    if item['tool']=='python':
        if not safe_python_requirements(root):raise RepositoryError('requirements.txt تغير أو يحتوي مصادر غير موثوقة.')
        await _command(item['command'],cwd=root,timeout=80)
        exe=root/'.barq-venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        result=await _command([str(exe),'-m','pip','install','--only-binary=:all:','--disable-pip-version-check','-r','requirements.txt'],cwd=root,timeout=180)
    else:
        if not _safe_npm_manifest(root):
            raise RepositoryError('ملف الاعتماديات اتغير أو فيه مصادر غير آمنة؛ راجعه قبل التثبيت.')
        env=_git_environment();env['npm_config_ignore_scripts']='true'
        result=await _command(item['command'],cwd=root,timeout=180,env=env)
    return {'workspace':str(root),'installed':True,'scripts_executed':False,'tool':item['tool'],**result}
