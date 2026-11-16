"""Regression checks for visible real source and background process launching."""
from pathlib import Path
import os
import subprocess
import json

ROOT=Path(__file__).resolve().parents[1]


def test_windows_subprocesses_hide_their_consoles():
    # Legacy launchers still use CREATE_NO_WINDOW explicitly. The computer
    # command tool delegates execution to the unified Runner, which owns this
    # flag; asserting it inside the wrapper would be checking the wrong layer.
    for path in ('build/jobs.py','tools/registry.py','mcp/bridge.py','studio/project.py'):
        text=(ROOT/path).read_text(encoding='utf-8')
        assert 'CREATE_NO_WINDOW' in text, path
    wrapper=(ROOT/'computer_control/tools/execute.py').read_text(encoding='utf-8')
    runner=(ROOT/'execution/runner.py').read_text(encoding='utf-8')
    assert 'Runner().run(Command(' in wrapper
    assert "getattr(subprocess,'CREATE_NO_WINDOW',0)" in runner
    assert 'shell=False,creationflags=creationflags' in runner


def test_computer_command_uses_structured_runner_with_no_shell(monkeypatch,tmp_path):
    from computer_control.tools.execute import Tools
    from execution.runner import CommandResult
    import execution.runner as engine
    from types import SimpleNamespace
    calls=[]
    def fake_run(self, spec, **kwargs):
        calls.append((spec,kwargs))
        return CommandResult(command='python',returncode=0,stdout='ok',stderr='',duration=0.01)
    monkeypatch.setattr(engine.Runner,'run',fake_run)
    instance=Tools(SimpleNamespace())
    result=instance.act('run_command',{'cmd':'python --version','cwd':str(tmp_path)})
    assert result['verified_process_exit'] is True
    assert len(calls)==1
    assert calls[0][0].program=='python'
    assert calls[0][0].args==('--version',)
    assert calls[0][0].cwd==str(tmp_path.resolve())


def test_main_chat_agent_changes_refresh_real_editor():
    store=(ROOT/'frontend/src/lib/taskActions.ts').read_text(encoding='utf-8')
    ui=(ROOT/'frontend/src/components/workspace/WorkspaceStudio.tsx').read_text(encoding='utf-8')
    assert 'announceWorkspaceChange(saved.workspace,saved.path)' in store
    assert 'chooseWorkspaceSource' in ui
    assert 'setEditorView(\'editor\')' in ui
    assert 'pendingSource(currentPlan)' in ui
    assert 'setFiles(nextFiles)' in ui


def test_approved_code_is_not_saved_without_approval():
    ui=(ROOT/'frontend/src/components/workspace/LiveCodePanel.tsx').read_text(encoding='utf-8')
    assert "proposed?.content||block?.content" in ui
    assert "proposed?'دي مسودة حقيقية" in ui
    assert 'disabled={!code||streaming||!!proposed' in ui
    assert 'onReview(code,targetPath)' in ui


def test_auto_focus_and_agent_draft_in_node_without_react():
    js='''
const fs=require('fs'),ts=require(process.env.BARQ_TSC),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.env.BARQ_SOURCE,'utf8');
const output=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const exports={};vm.runInNewContext(output,{exports});
const {chooseWorkspaceSource,pendingSource}=exports;
const folder=[{path:'barq-app',is_dir:true},{path:'barq-app/README.md',is_dir:false},{path:'barq-app/main.py',is_dir:false}];
assert.equal(chooseWorkspaceSource([],folder),'barq-app/main.py');
assert.equal(chooseWorkspaceSource(folder,[...folder,{path:'barq-app/window.py',is_dir:false}]),'barq-app/window.py');
assert.equal(chooseWorkspaceSource(folder,folder,'barq-app/main.py'),'barq-app/main.py');
assert.equal(chooseWorkspaceSource([{path:'barq-app/main.py',is_dir:false}], [{path:'barq-app/.env',is_dir:false}]),'');
assert.equal(pendingSource({status:'failed',plan:{plan:{steps:[{tool:'workspace_edit',args:{path:'src/a.py',content:'print(1)'}}]}}}),null);
assert.equal(pendingSource({status:'plan_ready',plan:{plan:{steps:[{tool:'workspace_edit',args:{path:'src/a.py',content:'print(1)'}}]}}}).content,'print(1)');
assert.equal(pendingSource({status:'plan_ready',plan:{plan:{steps:[{tool:'project_bootstrap',args:{name:'test'}}]}}}),null);
console.log('direct editor selection and approved draft tests passed');
'''
    script=ROOT/'frontend/src/lib/studioProjectFocus.ts'
    tsc=str(ROOT/'frontend/node_modules/typescript/lib/typescript.js')
    if not Path(tsc).exists():
        import pytest
        pytest.skip('Project TypeScript compiler not installed; run npm ci')
    result=subprocess.run(['node','-e',js],cwd=ROOT,env={**os.environ,'BARQ_TSC':tsc,'BARQ_SOURCE':str(script)},capture_output=True,text=True,timeout=12)
    assert result.returncode==0, result.stderr


def test_runner_actually_sets_hidden_window_flags_and_disables_shell(monkeypatch):
    """Regression: inspect the Popen call, not merely a string in a wrapper."""
    import io
    import execution.runner as engine
    from types import SimpleNamespace
    seen=[]
    class FakeProcess:
        stdout=io.BytesIO(b'good\n')
        stderr=io.BytesIO(b'')
        def poll(self):return 0
        def wait(self,timeout=None):return 0
    def fake_popen(argv,**kwargs):
        seen.append((argv,kwargs))
        return FakeProcess()
    monkeypatch.setattr(engine.Runner,'validate',classmethod(lambda cls,spec: ('python',['python','--version'],None)))
    monkeypatch.setattr(engine,'_WindowsJob',lambda process:SimpleNamespace(close=lambda:None))
    monkeypatch.setattr(engine.subprocess,'CREATE_NO_WINDOW',0x08000000,raising=False)
    monkeypatch.setattr(engine.subprocess,'CREATE_NEW_PROCESS_GROUP',0x200,raising=False)
    monkeypatch.setattr(engine.subprocess,'Popen',fake_popen)
    response=engine.Runner().run(engine.Command('python',('--version',)))
    assert response.returncode==0
    assert response.stdout=='good\n'
    assert len(seen)==1
    argv,kwargs=seen[0]
    assert kwargs['shell'] is False
    assert kwargs['creationflags'] & 0x08000000
    assert kwargs['creationflags'] & 0x200
    assert argv==['python','--version']
