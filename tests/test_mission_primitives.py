import pytest
from coding.blocks import parse_file_blocks, parse_edit_blocks, safe_path
from mission.state import MissionStore, create, next_item, report

@pytest.mark.parametrize('path',['../a.py','C:/foo.py','/etc/a.py','x/../a.py','CON.txt','a.exe','a\\b.py'])
def test_paths_blocked(path):
    with pytest.raises(ValueError):safe_path(path)

def test_file_blocks_and_truncation():
    blocks,truncated=parse_file_blocks('hi\r\n### FILE: src/main.py\r\n```python\r\nprint(42)\r\n```\r\n')
    assert not truncated and blocks[0]['content']=='print(42)\n'
    blocks,truncated=parse_file_blocks('### FILE: app.py\n```py\nprint(1)')
    assert truncated and blocks[0]['truncated']

def test_duplicate_and_edit():
    with pytest.raises(ValueError):parse_file_blocks('### FILE: x.py\n```\na\n```\n### FILE: x.py\n```\nb\n```')
    edits=parse_edit_blocks('### EDIT: x.py\n<<<<<<< SEARCH\na\n=======\nb\n>>>>>>> REPLACE\n')
    assert edits[0]['before']=='a\n' and edits[0]['after']=='b\n'

def test_resume_persistence(tmp_path):
    store=MissionStore(tmp_path);m=create('ابني برنامج',tmp_path,'desktop_python',['main.py','README.md'])
    m['manifest'][0]['status']='verified';store.save(m)
    m2=store.load(m['id'])
    assert next_item(m2)['path']=='README.md'
    assert report(m2)['complete'] is False
    m2['manifest'][1]['status']='needs_attention'
    assert next_item(m2) is None and report(m2)['complete'] is False
