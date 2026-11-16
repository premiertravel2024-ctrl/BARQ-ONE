"""Coding agent regressions: no unapproved edits, safe repo context and free routing."""
import json
import pytest
from fastapi.testclient import TestClient
from agent import orchestrator
from coding.context import project_map, search_code
from coding.patches import propose_replace
from coding.quality import source_check
from workspace import manager as workspace
from api import app
from router.config import Config
from router.select import Router
from router.limits import RateLimiter
from monitor.health import Health
from classifier.tasks import classify


def test_source_check_never_executes_code(tmp_path):
    marker=tmp_path/'SHOULD_NOT_EXIST'
    code=f'from pathlib import Path\nPath({str(marker)!r}).write_text("bad")\n'
    assert source_check('source.py', code)['valid']
    assert not marker.exists()
    assert not source_check('source.py', 'def broken(:')['valid']
    assert not source_check('data.json','{"a":}')['valid']
    assert source_check('config.yaml','a: 1\n')['valid']
    assert not source_check('config.yaml','a: [') ['valid']


def test_small_code_replace_exact_match_and_undo(tmp_path, monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'state'))
    root=tmp_path/'repo';root.mkdir()
    f=root/'app.py';f.write_text('def total(a, b):\n    return a-b\n',encoding='utf8')
    preview=propose_replace(str(root),'app.py','return a-b','return a+b')
    assert preview['quality']['valid']
    assert 'return a+b' in preview['diff']
    assert f.read_text().endswith('a-b\n')
    with pytest.raises(ValueError,match='Confirmation'):
        workspace.apply(preview['approval_id'],False)
    saved=workspace.apply(preview['approval_id'],True)
    assert f.read_text().endswith('a+b\n')
    workspace.undo(saved['backup_id'],True)
    assert f.read_text().endswith('a-b\n')


def test_code_replace_rejects_ambiguous_invalid_or_conflicted(tmp_path):
    f=tmp_path/'a.py';f.write_text('x=1\nx=1\n')
    with pytest.raises(ValueError,match='exactly one'):propose_replace(str(tmp_path),'a.py','x=1','x=2')
    with pytest.raises(ValueError,match='invalid'):propose_replace(str(tmp_path),'a.py','x=1\nx=1\n','def foo(:\n')
    with pytest.raises(ValueError,match='exactly one'):propose_replace(str(tmp_path),'a.py','missing','value')


def test_coding_context_keeps_paths_local_and_excludes_credentials(tmp_path):
    repo=tmp_path/'repo';repo.mkdir();(repo/'src').mkdir();(repo/'.git').mkdir();(repo/'node_modules').mkdir()
    (repo/'src'/'code.py').write_text('def job():\n    return 42\n')
    (repo/'.env').write_text('GEMINI_API_KEY=VERY_SECRET_VALUE')
    (repo/'src'/'secret_token.py').write_text('do_not_send')
    (repo/'node_modules'/'large.js').write_text('package_vendor')
    (repo/'.git'/'config').write_text('repository_private')
    mapped=project_map(str(repo))
    assert 'src/code.py' in mapped['files']
    assert not any('secret' in x or '.env' in x or 'node_modules' in x for x in mapped['files'])
    hits=search_code(str(repo),'return 42')
    assert hits['hits'][0]['file']=='src/code.py'
    assert not search_code(str(repo),'VERY_SECRET_VALUE')['hits']
    with pytest.raises(ValueError):search_code(str(repo),'')


def test_coding_classifier_and_priority(monkeypatch):
    monkeypatch.setenv('CODING_TEST_KEY','free-only-test')
    cfg=Config.model_validate({'providers':[
        {'name':'general','api_key_env':'CODING_TEST_KEY','base_url':'https://example.invalid','priority':90,'models':[{'name':'chat','strengths':['writing']}]},
        {'name':'coder','api_key_env':'CODING_TEST_KEY','base_url':'https://example.invalid','priority':65,'models':[{'name':'coder','strengths':['coding','reasoning']}]}
    ]})
    pick=Router(cfg,RateLimiter(),Health()).candidates('coding','hard',100)
    assert pick[0][0].name=='coder'
    assert classify([{'role':'system','content':'coding'}, {'role':'user','content':'Hello'}])[0]!='coding'
    assert classify([{'role':'user','content':'Please fix my Rust project'}])[0]=='coding'


def test_coding_api_previews_do_not_auto_write(tmp_path):
    (tmp_path/'app.py').write_text('def x():\n    return 1\n')
    client=TestClient(app)
    m=client.get('/v1/coding/map',params={'workspace':str(tmp_path)})
    assert m.status_code==200 and 'app.py' in m.json()['files']
    r=client.post('/v1/coding/replace/preview',json={'workspace':str(tmp_path),'path':'app.py','before':'return 1','after':'return 2'})
    assert r.status_code==200 and r.json()['quality']['valid']
    assert (tmp_path/'app.py').read_text().endswith('return 1\n')
    bad=client.post('/v1/coding/replace/preview',json={'workspace':str(tmp_path),'path':'app.py','before':'return 1','after':'def malformed(:'})
    assert bad.status_code==400


@pytest.mark.asyncio
async def test_agent_stops_at_edit_preview_before_next_plan(tmp_path):
    (tmp_path/'app.py').write_text('x = 1\n')
    class FakeEngine:
        def __init__(self):self.calls=0
        async def run(self,*args,**kwargs):
            self.calls+=1
            assert kwargs['task_hint']=='coding'
            if self.calls==1:
                assert 'project_map' in args[0][0]['content']
                return {'model':'local-test','content':json.dumps({'reason':'Fix variable','steps':[{'tool':'code_replace','args':{'path':'app.py','before':'x = 1','after':'x = 2'}}],'answer':'preview'})}
            raise AssertionError('No follow-up model call is permitted until user saves the preview')
    engine=FakeEngine()
    plan=await orchestrator.plan(engine,str(tmp_path),[{'role':'user','content':'Please fix app.py'}])
    assert plan['plan']['steps'][0]['tool']=='code_replace'
    result=await orchestrator.execute(engine,plan['plan_id'],True)
    assert result['pending_edit']['diff']
    assert engine.calls==1
    assert (tmp_path/'app.py').read_text()=='x = 1\n'


def test_python_outline_includes_source_boundaries_but_not_bodies(tmp_path):
    from coding.symbols import outline
    path=tmp_path/'code.py'
    path.write_text('import os\nfrom pathlib import Path\nclass Worker:\n    def run(self):\n        password = "NOT_FOR_MODEL"\n        return password\n\nasync def main():\n    return 1\n',encoding='utf-8')
    result=outline(str(tmp_path),'code.py')
    assert result['imports']==['os','pathlib']
    assert [(s['name'],s['line']) for s in result['symbols']]==[
        ('Worker',3),('Worker.run',4),('main',8)]
    assert result['symbols'][0]['end_line']==6
    assert 'NOT_FOR_MODEL' not in str(result)
    path.write_text('def broken(:\n',encoding='utf8')
    assert outline(str(tmp_path),'code.py')['syntax_error']


def test_outline_denies_private_paths_and_outputs_no_source(tmp_path):
    from coding.symbols import outline
    (tmp_path/'.env').write_text('SECRET=XYZ')
    (tmp_path/'secret.py').write_text('secret')
    (tmp_path/'a.ts').write_text('export function render() {}\nclass Demo {}\nconst x = 3;\n')
    assert [s['name'] for s in outline(str(tmp_path),'a.ts')['symbols']]==['render','Demo','x']
    with pytest.raises(ValueError):outline(str(tmp_path),'.env')
    with pytest.raises(ValueError):outline(str(tmp_path),'secret.py')


def test_redaction_and_toml_validation():
    from coding.redaction import redact
    value='"password": "a-very-secret-value"\nAPI_KEY=abc000zzz\nAuthorization: Bearer VERY_LONG_SECRET_TOKEN\n'
    safe=redact(value)
    assert 'a-very-secret-value' not in safe
    assert 'abc000zzz' not in safe
    assert 'VERY_LONG_SECRET_TOKEN' not in safe
    assert '"password": "[REDACTED]"' in safe
    assert source_check('pyproject.toml','[project]\nname = "sample"\n')['valid']
    assert not source_check('pyproject.toml','[project\n')['valid']


@pytest.mark.asyncio
async def test_saved_edit_can_resume_to_approved_test_plan(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'state'))
    repo=tmp_path/'repo';repo.mkdir()
    (repo/'app.py').write_text('x = 1\n')
    class FakeEngine:
        def __init__(self):self.calls=0
        async def run(self,messages,**kwargs):
            self.calls+=1
            assert kwargs.get('task_hint')=='coding'
            if self.calls==1:
                return {'model':'ollama/test','content':json.dumps({'steps':[{'tool':'code_replace','args':{'path':'app.py','before':'x = 1','after':'x = 2'}}], 'answer':'التعديل'})}
            assert 'SAVED' in messages[-1]['content']
            return {'model':'ollama/test','content':json.dumps({'steps':[{'tool':'run_tests','args':{}}], 'answer':'راجع الاختبارات'})}
    engine=FakeEngine()
    plan=await orchestrator.plan(engine,str(repo),[{'role':'user','content':'Fix app.py'}])
    result=await orchestrator.execute(engine,plan['plan_id'],True)
    approval=result['pending_edit']['approval_id']
    with pytest.raises(ValueError,match='Confirmation'):
        await orchestrator.resume_after_saved_edit(engine,approval,'0'*32,False)
    with pytest.raises(ValueError,match='backup not found'):
        await orchestrator.resume_after_saved_edit(engine,approval,'0'*32,True)
    assert engine.calls==1
    saved=workspace.apply(approval,True)
    cont=await orchestrator.resume_after_saved_edit(engine,approval,saved['backup_id'],True)
    assert cont['next_plan']['plan']['steps'][0]['tool']=='run_tests'
    assert engine.calls==2
    assert (repo/'app.py').read_text()=='x = 2\n'
    with pytest.raises(ValueError,match='No pending'):
        await orchestrator.resume_after_saved_edit(engine,approval,saved['backup_id'],True)
    workspace.undo(saved['backup_id'],True)
    assert (repo/'app.py').read_text()=='x = 1\n'


def test_outline_http_status_and_escape(tmp_path):
    path=tmp_path/'source.py';path.write_text('def useful():\n    return True\n')
    c=TestClient(app)
    good=c.get('/v1/coding/outline',params={'workspace':str(tmp_path),'path':'source.py'})
    assert good.status_code==200 and good.json()['symbols'][0]['name']=='useful'
    bad=c.get('/v1/coding/outline',params={'workspace':str(tmp_path),'path':'../outside.py'})
    assert bad.status_code==400


def test_static_coding_review_flags_likely_risks():
    result=source_check('source.py','secret_token="a-long-hardcoded-token"\nexec("print(1)")\ntry:\n    pass\nexcept:\n    pass\n')
    assert result['valid']
    assert any('credential' in x for x in result['warnings'])
    assert any('dynamic Python' in x for x in result['warnings'])
    assert any('bare except' in x for x in result['warnings'])


def test_agent_plan_args_validation():
    from agent.orchestrator import parse_plan,ACTIONS
    with pytest.raises(ValueError,match='missing required'):
        parse_plan('{"steps":[{"tool":"code_replace","args":{"path":"app.py"}}]}',set(ACTIONS))
    with pytest.raises(ValueError,match='arguments must'):
        parse_plan('{"steps":[{"tool":"rea_analyze","args":{"name":"test","arguments":[]}}]}',set(ACTIONS))


@pytest.mark.asyncio
async def test_invalid_local_model_plan_gets_single_corrective_attempt(tmp_path):
    class FakeEngine:
        def __init__(self):self.calls=0
        async def run(self,messages,**kwargs):
            self.calls+=1
            return {'content':('Sure, here is your plan' if self.calls==1 else '{"steps":[], "answer":"لا تحتاج أداة"}'), 'model':'ollama/local'}
    e=FakeEngine()
    result=await orchestrator.plan(e,str(tmp_path),[{'role':'user','content':'Check app'}])
    assert e.calls==2
    assert not result['plan']['steps']


def test_repository_diagnostics_never_runs_scripts(tmp_path):
    from coding.diagnostics import diagnose
    root=tmp_path/'repo';root.mkdir()
    marker=tmp_path/'SHOULD_NOT_EXIST'
    (root/'package.json').write_text(json.dumps({'scripts':{'test':f'echo test > {marker}','build':'vite build'}}))
    (root/'README.md').write_text('Repo summary')
    (root/'app.py').write_text('def broken(:\n')
    tests=root/'tests';tests.mkdir()
    (tests/'test_demo.py').write_text('def test_demo():\n    assert True\n')
    report=diagnose(str(root))
    assert not marker.exists()
    assert report['syntax_errors'][0]['file']=='app.py'
    assert 'tests/test_demo.py' in report['test_files']
    assert 'test' in report['package_scripts']
    client=TestClient(app)
    r=client.get('/v1/coding/diagnostics',params={'workspace':str(root)})
    assert r.status_code==200 and r.json()['syntax_errors']
