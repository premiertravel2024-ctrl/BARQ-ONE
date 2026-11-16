import pytest
from mission.interface import review_interface
from mission.quality import review_project
from mission.validation import next_validation


def check(tmp_path,name,source):
    (tmp_path/name).write_text(source)
    mission={'kind':'web_static' if name.endswith('.html') else 'desktop_python','manifest':[{'path':name,'status':'written'}]}
    return mission,review_interface(str(tmp_path),mission)

@pytest.mark.parametrize('source,code',[
    ('<input id="x"><button id="x">Save</button>','duplicate_ui_id'),
    ('<label for="gone">Name</label><input id="name">','broken_label_target'),
])
def test_broken_html_associations_block_validation(tmp_path,source,code):
    mission,result=check(tmp_path,'index.html',source)
    assert not result['passed'] and result['issues'][0]['code']==code
    assert not review_project(str(tmp_path),mission)['passed']
    assert next_validation(str(tmp_path),'app',mission) is None


def test_valid_labels_and_decorative_image_do_not_warn(tmp_path):
    _,result=check(tmp_path,'index.html','<label for="name">Name</label><input id="name"><img alt="" src="x">')
    assert result['passed'] and not result['warnings'] and not result['visual_verified']


def test_missing_accessible_name_is_review_warning_not_false_block(tmp_path):
    _,result=check(tmp_path,'index.html','<label>Name<input></label><img src="x">')
    assert result['passed'] and len(result['warnings'])==2


def test_tk_empty_callback_is_blocked_without_executing_source(tmp_path):
    source='import tkinter as tk\nraise RuntimeError("never execute")\nb = tk.Button(command=lambda: None)\n'
    _,result=check(tmp_path,'main.py',source)
    assert not result['passed'] and result['issues'][0]['code']=='empty_ui_callback'


def test_disabled_or_real_tk_controls_are_not_blocked(tmp_path):
    _,result=check(tmp_path,'main.py','import tkinter as tk\nb = tk.Button(command=lambda: None, state="disabled")\nc = tk.Button(command=lambda: save())\n')
    assert result['passed']


def test_pending_files_are_not_prematurely_reviewed(tmp_path):
    result=review_interface(str(tmp_path),{'manifest':[{'path':'missing.html','status':'pending'}]})
    assert result['passed'] and result['checked_files']==0
