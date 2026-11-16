import hashlib
from pathlib import Path
from mission import tracking


def test_syntax_evidence_requires_approved_saved_hash(tmp_path, monkeypatch):
    state=tmp_path/'state'
    monkeypatch.setattr(tracking, 'state_file', lambda name: state/name)
    root=tmp_path/'workspace'
    root.mkdir()
    project=root/'barq-app'
    project.mkdir()
    file=project/'main.py'
    file.write_text('print(1)\n', encoding='utf-8')
    tracking.start(str(root), 'barq-app', 'desktop_python', 'build app', ['main.py'])
    assert tracking.mark_syntax_checked(str(root),'barq-app','barq-app/main.py',{'valid':True}) is None
    digest=hashlib.sha256(file.read_text(encoding='utf-8').encode()).hexdigest()
    tracking.mark_saved(str(root),'barq-app','barq-app/main.py',digest)
    assert tracking.mark_syntax_checked(str(root),'barq-app','barq-app/main.py',{'valid':False}) is None
    mission=tracking.mark_syntax_checked(str(root),'barq-app','barq-app/main.py',{'valid':True})
    assert mission['manifest'][0]['syntax_checked_hash']==digest
    assert mission['manifest'][0]['status']=='written'
    file.write_text('print(2)\n', encoding='utf-8')
    assert tracking.mark_syntax_checked(str(root),'barq-app','barq-app/main.py',{'valid':True}) is None


def test_untracked_file_not_promoted(tmp_path, monkeypatch):
    monkeypatch.setattr(tracking,'state_file',lambda name:tmp_path/'state'/name)
    root=tmp_path/'workspace';root.mkdir()
    project=root/'barq-app';project.mkdir()
    (project/'main.py').write_text('x=1',encoding='utf-8')
    tracking.start(str(root),'barq-app','desktop_python','goal',['main.py'])
    assert tracking.mark_syntax_checked(str(root),'barq-app','barq-app/main.py',{'valid':True}) is None
