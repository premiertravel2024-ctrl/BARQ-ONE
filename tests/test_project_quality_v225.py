import hashlib,json
import pytest
from mission.quality import public_interfaces,review_project
from mission.validation import next_validation,repair_context,fingerprint,record_validation
from mission.tracking import start,mark_saved,load_project


def project(tmp_path,monkeypatch,files):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'state'))
    root=tmp_path/'workspace';(root/'app').mkdir(parents=True)
    start(str(root),'app','desktop_python','Build Windows EXE',list(files))
    for name,code in files.items():
        (root/'app'/name).write_text(code)
        mark_saved(str(root),'app','app/'+name,hashlib.sha256(code.encode()).hexdigest())
    return str(root),load_project(str(root),'app')


def test_interfaces_include_parameters_and_class_methods():
    result=public_interfaces('def save(path, data, *, atomic=True):\n pass\nclass Store:\n def load(self, key):\n  pass\n')
    assert result==['save(path, data, *, atomic=True)','Store.load(self, key)']


def test_missing_local_api_blocks_build_even_after_passing_tests(tmp_path,monkeypatch):
    root,m=project(tmp_path,monkeypatch,{'storage.py':'def load():\n return {}\n','main.py':'from storage import save\n',
                                      'test_app.py':'from storage import load\ndef test_load():\n assert load()=={}\n'})
    record_validation(root,'app',{'tool':'run_tests','success':True,'result':'1 passed'},fingerprint(root,'app'))
    m=load_project(root,'app');report=review_project(root,m)
    assert report['issues'][0]['code']=='missing_local_export'
    assert next_validation(root,'app',m) is None
    assert 'does not export save' in repair_context(root,'app',m)


@pytest.mark.parametrize('body',['pass','assert True','"docstring only"','...'])
def test_placeholder_tests_require_repair(tmp_path,monkeypatch,body):
    root,m=project(tmp_path,monkeypatch,{'main.py':'value=1\n','test_app.py':f'def test_app():\n {body}\n'})
    assert not review_project(root,m)['passed']
    assert next_validation(root,'app',m) is None


def test_real_assertion_and_dynamic_exports_are_not_falsely_blocked(tmp_path,monkeypatch):
    root,m=project(tmp_path,monkeypatch,{'storage.py':'def __getattr__(name):\n return 1\n','main.py':'from storage import value\n',
        'test_app.py':'from main import value\ndef test_value():\n assert value==1\n'})
    assert review_project(root,m)['passed']
    assert next_validation(root,'app',m)['steps'][0]['tool']=='run_tests'


def test_review_never_executes_project_code(tmp_path,monkeypatch):
    marker=tmp_path/'executed'
    code=f'from pathlib import Path\nPath({str(marker)!r}).write_text("bad")\n'
    root,m=project(tmp_path,monkeypatch,{'main.py':code})
    review_project(root,m)
    assert not marker.exists()


@pytest.mark.asyncio
async def test_model_cannot_claim_completion_with_quality_blockers(tmp_path,monkeypatch):
    from agent.orchestrator import plan
    from mission.tracking import mark_syntax_checked
    root,m=project(tmp_path,monkeypatch,{'main.py':'value=1\n','test_app.py':'def test_app():\n assert True\n'})
    for row in m['manifest']:
        mark_syntax_checked(root,'app',row['path'],{'valid':True})
    class Premature:
        network=object()
        limiter=object()
        async def run(self,*args,**kwargs):
            return {'model':'fake','content':json.dumps({'steps':[],'reason':'Done','answer':'Completed'})}
    with pytest.raises(ValueError,match='blocking findings'):
        await plan(Premature(),root,[{'role':'user','content':'Build Windows EXE'}],project_hint='app',round_number=1)
