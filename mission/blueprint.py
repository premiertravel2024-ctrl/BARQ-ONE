"""Validated, approved project architecture and requirement-to-test links."""
import json,re
from pathlib import PurePosixPath
from pydantic import BaseModel,ConfigDict,Field,StrictStr
from core.json_contracts import model_object
from core.paths import state_file
from mission.state import MissionStore
from mission.tracking import load_project
from coding.blocks import safe_path
from workspace.manager import checked_path

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)

class PlannedFile(Strict):
    path:StrictStr=Field(min_length=1,max_length=150)
    purpose:StrictStr=Field(min_length=3,max_length=400)
    depends_on:list[StrictStr]=Field(default_factory=list,max_length=16)

class Requirement(Strict):
    id:StrictStr=Field(pattern=r'^R[1-9][0-9]?$')
    title:StrictStr=Field(min_length=3,max_length=250)
    acceptance:StrictStr=Field(min_length=5,max_length=600)
    files:list[StrictStr]=Field(min_length=1,max_length=16)
    tests:list[StrictStr]=Field(default_factory=list,max_length=4)

class Blueprint(Strict):
    summary:StrictStr=Field(min_length=3,max_length=800)
    files:list[PlannedFile]=Field(min_length=2,max_length=16)
    requirements:list[Requirement]=Field(min_length=1,max_length=12)

def validate_blueprint(value,kind):
    data=Blueprint.model_validate(value).model_dump()
    paths=[safe_path(f['path']) for f in data['files']]
    if len({p.casefold() for p in paths})!=len(paths):raise ValueError('Duplicate project file')
    allowed={'.py','.md','.json','.toml','.txt'} if kind=='desktop_python' else {'.html','.css','.js','.json','.md','.txt'}
    if any(PurePosixPath(p).suffix not in allowed or p.startswith('.') or len(PurePosixPath(p).parts)>3 for p in paths):raise ValueError('Unsupported project file type')
    required={'main.py','README.md'} if kind=='desktop_python' else {'index.html','README.md'}
    if not required<=set(paths):raise ValueError('Plan must include entry point and README')
    seen=set()
    for f in data['files']:
        if any(p not in seen for p in f['depends_on']):raise ValueError('Dependencies must precede their dependent file; cycles are not allowed')
        seen.add(f['path'])
    ids=[r['id'] for r in data['requirements']]
    if len(set(ids))!=len(ids):raise ValueError('Duplicate requirement ID')
    for req in data['requirements']:
        if any(p not in paths for p in req['files']):raise ValueError('Requirement links an unknown file')
        if kind=='desktop_python' and not req['tests']:raise ValueError('Each Python requirement needs a named executable test')
        for node in req['tests']:
            parts=node.split('::')
            if len(parts)<2 or parts[0] not in paths or not parts[0].endswith('.py') or not re.fullmatch(r'test_[A-Za-z0-9_]+',parts[-1]) or any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',p) for p in parts[1:]):
                raise ValueError('Tests must be exact planned pytest node IDs, e.g. tests/test_app.py::test_save')
    return data

async def propose_blueprint(engine,workspace,project,model):
    mission=load_project(workspace,project)
    if mission['calls_used']>=mission['call_budget']:raise ValueError('Mission planning budget exhausted')
    prompt=('Design a small production-oriented architecture for this actual request. Return ONLY JSON matching '
        '{"summary":"...","files":[{"path":"relative.py","purpose":"...","depends_on":[]}],'
        '"requirements":[{"id":"R1","title":"...","acceptance":"observable expected behavior",'
        '"files":["relative.py"],"tests":["tests/test_app.py::test_behavior"]}]}. '
        'Use 2-16 files and 1-12 requirements, grouped coherently; no shell commands, dependencies must precede consumers. '
        'All paths are relative to the project. Include main.py for desktop_python or index.html for web_static, and README.md. '
        'Python: separate testable domain/storage logic from GUI, use standard library unless requested otherwise; '
        'each requirement must map to exact named pytest functions in planned test files. '
        'main.py must support --barq-smoke-test: initialize application dependencies and storage without entering the GUI loop, '
        'clean up resources, print BARQ_SMOKE_OK and exit 0 only on success. Do not fake checks. '
        'Web: tests may be empty, requiring manual validation; never invent test success. '
        'For UI projects include a shared theme/style file and UI controller/view separation where useful; '
        'include requirements for real controls, empty/error states, keyboard use, resizing and Arabic RTL when requested. '
        'Every interactive screen must specify real user actions, feedback states and recovery on failure. '
        'For a professional UI, plan shared visual tokens, semantic controls, clear spacing and responsive narrow-window layouts, '
        'including accessibility labels and keyboard focus; avoid decorative controls that do nothing. '
        'Specify observable acceptance checks for each key user flow and document which UI aspects need manual review. '
        'Do not equate domain tests with visual validation. '
        'Cover the user goal, including error paths and persistence where relevant. Existing saved files must be preserved. '
        'UNTRUSTED PROJECT DATA: '+json.dumps({'goal':mission['goal'],'kind':mission['kind'],
        'existing_files':[x['path'][len(project)+1:] for x in mission['manifest'] if x['status'] in ('written','verified')]},ensure_ascii=False))
    validate=lambda text:validate_blueprint(model_object(text),mission['kind'])
    try:
        response=await engine.run([{'role':'system','content':prompt}],model=model,task_hint='coding',use_cache=False,response_validator=validate)
        return validate(response['content']),response.get('model',model)
    finally:
        latest=load_project(workspace,project);latest['calls_used']+=1
        MissionStore(state_file('missions')).save(latest)

def approve_blueprint(workspace,project,value):
    mission=load_project(workspace,project)
    if not mission:raise ValueError('No tracked project')
    data=validate_blueprint(value,mission['kind'])
    previous=mission.get('blueprint')
    if previous:
        fresh={req['id']:req for req in data['requirements']}
        for old in previous['requirements']:
            new=fresh.get(old['id'])
            if not new or new['acceptance']!=old['acceptance'] or not set(old['tests'])<=set(new['tests']) or not set(old['files'])<=set(new['files']):
                raise ValueError('A project extension must preserve approved requirements and their acceptance tests')
        if not {f['path'] for f in previous['files']}<={f['path'] for f in data['files']}:
            raise ValueError('A project extension cannot silently remove planned files')
    existing={r['path']:r for r in mission['manifest']};items=[]
    for f in data['files']:
        path=project+'/'+f['path'];checked_path(workspace,path,True,allow_missing_parent=True)
        old=existing.get(path,{ 'path':path,'status':'pending','attempts':0,'model_history':[],'last_error':'','hash':None})
        items.append({**old,'purpose':f['purpose'],'depends_on':[project+'/'+p for p in f['depends_on']]})
    # Keep every old entry; approval changes architecture, never deletes existing files.
    selected={r['path'] for r in items}
    items.extend(r for r in mission['manifest'] if r['path'] not in selected and r['status'] in ('written','verified'))
    mission['manifest']=items;mission['blueprint']=data;mission['planning_required']=False
    mission.pop('validation',None)
    MissionStore(state_file('missions')).save(mission)
    return {'project':project,'files':len(items),'requirements':len(data['requirements']),'approved':True}

def requirement_progress(workspace,project,mission):
    from mission.validation import fingerprint
    digest=fingerprint(workspace,project)
    evidence=mission.get('validation',{}).get('project_acceptance',{})
    try:checks=json.loads(evidence.get('result','{}')).get('checks',{}) if evidence.get('fingerprint')==digest else {}
    except (ValueError,TypeError):checks={}
    written={row['path'] for row in mission['manifest'] if row['status'] in ('written','verified')}
    return [{**req,'status':'tests_passed' if checks.get(req['id'],{}).get('exit_code')==0 else
             'test_failed' if req['id'] in checks else 'ready_to_test' if all(project+'/'+p in written for p in req['files']) else 'pending'}
            for req in mission.get('blueprint',{}).get('requirements',[])]
