"""Durable, evidence-based bookkeeping for user-approved coding missions.

This module never executes a tool, creates workspace files, or grants approval.
"""
import hashlib
import json
from pathlib import Path
from core.paths import state_file
from mission.state import MissionStore, create
from workspace.manager import checked_path, read_text


def _key(workspace, project):
    token=(str(Path(workspace).resolve())+'\0'+project).encode('utf-8')
    return hashlib.sha256(token).hexdigest()


def _index():
    return state_file('missions')/'project-index'


def start(workspace, project, kind, goal, files, planning_required=False):
    """Record a scaffold only AFTER the approved scaffold tool succeeds."""
    from mission.state import MissionStore
    store=MissionStore(state_file('missions'))
    mission=create(goal,workspace,kind,[project.rstrip('/')+'/'+x for x in files])
    mission['planning_required']=planning_required
    # A scaffold is not a finished implementation and is never verified.
    for item in mission['manifest']:
        item['status']='pending'
    store.save(mission)
    folder=_index();folder.mkdir(parents=True,exist_ok=True)
    path=folder/(_key(workspace,project)+'.json')
    import os, uuid
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        tmp.write_text(json.dumps({'mission_id':mission['id'],'workspace':str(workspace),'project':project}),encoding='utf-8')
        os.replace(tmp,path)
    finally:
        tmp.unlink(missing_ok=True)
    return mission['id']


def load_project(workspace, project):
    idx=_index()/(_key(workspace,project)+'.json')
    if not idx.is_file():return None
    data=json.loads(idx.read_text(encoding='utf-8'))
    if data['workspace']!=str(workspace) or data['project']!=project:
        raise ValueError('Mission index scope mismatch')
    return MissionStore(state_file('missions')).load(data['mission_id'])


def mark_saved(workspace, project, path, expected_hash):
    """Only a verified approval backup and matching disk contents can mark written."""
    mission=load_project(workspace,project)
    if mission is None:return None
    checked_path(workspace,path)
    if hashlib.sha256(read_text(workspace,path).encode('utf-8')).hexdigest()!=expected_hash:
        raise ValueError('Saved source does not match approved edit')
    for item in mission['manifest']:
        if item['path']==path:
            item['status']='written'   # NEVER verified without real verification evidence
            if item.get('hash')!=expected_hash:
                item.pop('syntax_checked_hash',None);item.pop('syntax_checked_at',None)
            item['hash']=expected_hash
            item['last_error']=''
            break
    else:
        # Safe extension of manifest only for a confirmed file in this project.
        if not path.startswith(project.rstrip('/')+'/'):
            raise ValueError('Saved file outside mission project')
        mission['manifest'].append({'path':path,'status':'written','attempts':0,
                                   'model_history':[],'last_error':'','hash':expected_hash})
    MissionStore(state_file('missions')).save(mission)
    return mission


def mark_syntax_checked(workspace, project, path, check_result):
    """Persist genuine local syntax-check evidence; never claim app/test verification.

    A check may be recorded only against bytes that were previously committed
    through the approved edit path, and which are still present on disk.
    """
    if not isinstance(check_result, dict) or check_result.get('valid') is not True:
        return None
    mission=load_project(workspace,project)
    if mission is None:return None
    checked_path(workspace,path)
    digest=hashlib.sha256(read_text(workspace,path).encode('utf-8')).hexdigest()
    for item in mission['manifest']:
        if item['path'] != path:continue
        if item.get('status') not in ('written','verified') or item.get('hash') != digest:
            return None
        item['syntax_checked_hash']=digest
        item['syntax_checked_at']=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
        MissionStore(state_file('missions')).save(mission)
        return mission
    return None


def project_for_goal(workspace, goal):
    """Find an existing mission only by original goal and workspace scope.

    A user's unrelated request never silently attaches to another project.
    """
    if not isinstance(goal,str) or not goal.strip():return None
    index=_index()
    if not index.is_dir():return None
    for file in sorted(index.glob('*.json'),key=lambda x:x.stat().st_mtime,reverse=True)[:100]:
        try:
            item=json.loads(file.read_text(encoding='utf-8'))
            if item.get('workspace')!=str(workspace):continue
            mission=MissionStore(state_file('missions')).load(item['mission_id'])
            if mission['goal']==goal or (goal.startswith(mission['goal']+'\nمتابعة المستخدم:')):
                project=item['project']
                if checked_path(workspace,project).is_dir():return project
        except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError):
            continue
    return None


def project_for_requested_name(workspace, goal):
    """Resume a named, unfinished project despite natural wording changes.

    Name and workspace MUST both match an approved indexed mission. Do not
    attach a generic 'barq-app' or an unrelated request to prior projects.
    """
    from mission.engine import project_name
    from mission.state import MissionStore
    if not isinstance(goal,str) or not goal.strip():return None
    if __import__('re').search(r'نسخة\s+جديدة|مشروع\s+مختلف|من\s+الصفر\s+مرة\s+تانية|brand.new\s+copy',goal,__import__('re').I):return None
    wanted=project_name(goal)
    if wanted=='barq-app':return None
    index=_index()
    if not index.is_dir():return None
    for file in sorted(index.glob('*.json'), key=lambda x:x.stat().st_mtime, reverse=True)[:100]:
        try:
            item=json.loads(file.read_text(encoding='utf-8'))
            if item.get('workspace')!=str(workspace) or item.get('project')!=wanted:continue
            mission=MissionStore(state_file('missions')).load(item['mission_id'])
            if mission.get('kind') not in ('desktop_python','web_static'):continue
            # Do not hijack a completed project or one with no remaining work.
            if not any(row['status'] in ('pending','writing','failed','needs_attention') for row in mission.get('manifest',[])):
                continue
            if checked_path(workspace,wanted).is_dir():return wanted
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue
    return None

# OpenJarvis-inspired persistent operative checkpoints / loop protection.
# Integrated into BARQ's existing mission tracking, not a second agent runtime.
# No prompts, source, paths, tool args, credentials, or model output are stored.

def _action_signature(tool, args):
    if not isinstance(tool, str) or not isinstance(args, dict):
        raise ValueError('Invalid approved tool call')
    canonical=json.dumps({'tool':tool,'args':args},sort_keys=True,ensure_ascii=False,
                         separators=(',',':'),default=str).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()


def _workflow_path(workspace,goal):
    if not isinstance(goal,str) or not goal.strip():
        return None
    # The full prompt must not be embedded in a filename or saved on disk.
    key=hashlib.sha256((str(Path(workspace).resolve())+'\0'+goal).encode()).hexdigest()
    return state_file('missions')/'workflow-actions'/(key+'.json')


def _load_action_log(workspace,goal,project):
    if project:
        mission=load_project(workspace,project)
        return list(mission.get('approved_actions',[])) if mission else []
    file=_workflow_path(workspace,goal)
    if file is None or not file.is_file():return []
    try:
        value=json.loads(file.read_text(encoding='utf-8'))
        if value.get('workspace_hash')!=hashlib.sha256(str(Path(workspace).resolve()).encode()).hexdigest():return []
        return value.get('approved_actions',[]) if isinstance(value.get('approved_actions'),list) else []
    except (OSError,ValueError,TypeError):
        return []


def remembered_actions(workspace,goal,project=None):
    """Minimal, local, factual memory of approved tool outcomes for the planner."""
    actions=[{'tool':x['tool'],'success':x['success'],'timestamp':x['at']}
             for x in _load_action_log(workspace,goal,project)[-16:]
             if isinstance(x,dict) and isinstance(x.get('tool'),str)
             and isinstance(x.get('success'),bool)]
    if project:
        mission=load_project(workspace,project)
        if mission:
            # Keep the architecturally important facts from the original,
            # approved mission (not an LLM-generated memory summary).
            files=[{'path':f['path'],'status':f['status'],
                    'checked':f.get('syntax_checked_hash')==f.get('hash') and bool(f.get('hash'))}
                   for f in mission.get('manifest',[])[:32]]
            requirements=[{'id':r['id'],'title':r['title']}
                          for r in mission.get('blueprint',{}).get('requirements',[])[:12]]
            return {'approved_actions':actions,'project':project,
                    'goal':__import__('coding.redaction',fromlist=['redact']).redact(str(mission.get('goal',''))[:2500]),
                    'files':files,'requirements':requirements}
    return {'approved_actions':actions}


def check_action_loop(workspace,goal,project,tool,args,input_revision=None):
    """Guard repeated tool loops without blocking changed project state.

    Adapted from OpenJarvis's hash/sequence-based LoopGuard ideas. No new
    permissions, no executions, and no prompt-content inspection occur here.
    """
    actions=_load_action_log(workspace,goal,project)
    sig=_action_signature(tool,args)
    current=str(input_revision or '')
    same=[x for x in actions[-12:] if x.get('revision','')==current]
    if tool=='project_bootstrap' and any(x.get('signature')==sig and x.get('success') for x in same):
        return 'مشروع البداية اتعمل بالفعل'
    matches=[x for x in same if x.get('signature')==sig]
    # A-B-A-B-A-B is unproductive when neither the workspace nor inputs move.
    pattern=[x.get('signature') for x in same[-6:]]
    if (len(pattern)==6 and pattern[0]==pattern[2]==pattern[4]
            and pattern[1]==pattern[3]==pattern[5] and pattern[0]!=pattern[1]):
        if sig in (pattern[0],pattern[1]):
            return 'الأدوات دخلت في حلقة متكررة بدون تقدم'
    # Consecutive retries of a failed tool on identical inputs add no value.
    if len(matches)>=2 and all(x.get('success') is False for x in matches[-2:]):
        return 'نفس الأداة فشلت مرتين على نفس المدخلات'
    if len(matches)>=3:
        return 'نفس الأداة والمدخلات اتكررت ثلاث مرات'
    return None


def remember_approved_action(workspace,goal,project,tool,args,success,input_revision=None):
    """Persist actual approved outcomes; a preview is NOT a saved edit.

    This is best-effort bookkeeping and must never grant access to a tool.
    """
    if tool in ('workspace_edit','code_replace'):
        # Those only create uncommitted proposals, not file edits.
        return False
    if not isinstance(success,bool):raise ValueError('Tool success must be a boolean')
    from datetime import datetime, timezone
    entry={'tool':str(tool)[:80],'signature':_action_signature(tool,args),
           'success':success,'revision':str(input_revision or '')[:96],
           'at':datetime.now(timezone.utc).isoformat()}
    if project:
        mission=load_project(workspace,project)
        if not mission:return False
        mission['approved_actions']=(mission.get('approved_actions',[])+[entry])[-80:]
        MissionStore(state_file('missions')).save(mission)
        return True
    file=_workflow_path(workspace,goal)
    if file is None:return False
    file.parent.mkdir(parents=True,exist_ok=True)
    from uuid import uuid4
    import os
    record={'workspace_hash':hashlib.sha256(str(Path(workspace).resolve()).encode()).hexdigest(),
            'approved_actions':(_load_action_log(workspace,goal,None)+[entry])[-80:]}
    temp=file.with_name(file.name+'.'+uuid4().hex+'.tmp')
    try:
        with temp.open('x',encoding='utf-8') as stream:
            json.dump(record,stream,ensure_ascii=False)
            stream.flush();os.fsync(stream.fileno())
        os.replace(temp,file)
    finally:
        temp.unlink(missing_ok=True)
    return True
