"""Read-only inspection of generated UIs, without evaluating project source."""
from studio.ui_audit import inspect_ui


def test_html_duplicate_id_is_real_issue(tmp_path):
    (tmp_path/'index.html').write_text('<label for="x">Name</label><input id="x"><button id="x">Save</button>')
    result=inspect_ui(str(tmp_path))
    assert result['checked_files']==1
    assert any(f['kind']=='duplicate_ui_id' and f['severity']=='issue' for f in result['findings'])
    assert result['visual_verified'] is False and result['runtime_verified'] is False


def test_tsx_review_is_caution_not_false_proof(tmp_path):
    (tmp_path/'App.tsx').write_text('<button className="submit">Click</button>\n<img src="hero.png"/>')
    result=inspect_ui(str(tmp_path))
    assert len(result['findings'])==2
    assert all(f['severity']=='review' for f in result['findings'])
    assert 'code execution' in result['scope']


def test_ui_audit_does_not_run_source_or_read_secrets(tmp_path):
    (tmp_path/'App.tsx').write_text('raise RuntimeError("run")\nconst example = "safe";')
    (tmp_path/'.env').write_text('SECRET=PRIVATE')
    (tmp_path/'node_modules').mkdir()
    (tmp_path/'node_modules'/'example.tsx').write_text('<img src="no-alt">')
    result=inspect_ui(str(tmp_path))
    assert result['checked_files']==1
    assert not result['findings']


def test_responsive_and_rtl_are_observations_not_certifications(tmp_path):
    (tmp_path/'site.css').write_text('@media(max-width:600px){.card{padding-inline:12px}}\nbutton:focus-visible{outline:2px solid red}')
    result=inspect_ui(str(tmp_path))
    assert result['observations']['responsive_files']['count']==1
    assert result['observations']['rtl_files']['count']==1
    assert result['observations']['focus_styles']['count']==1
    assert not result['visual_verified']


def test_contextual_work_followup_is_an_existing_coding_intent():
    from agent.task_intent import classify_task
    old='ابنيلي برنامج إدارة الحجوزات'
    text=old+'\nمتابعة المستخدم: كمّل من آخر خطوة مؤكدة، وافحص الملفات والاختبارات قبل أي تعديل.'
    intent=classify_task(text)
    assert intent and intent['kind']=='coding'
    assert intent['goal'].startswith(old+'\nمتابعة المستخدم:')
