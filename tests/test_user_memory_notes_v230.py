import pytest
from memory.notes import Notes

def test_notes_are_explicit_searchable_and_deletable(tmp_path):
    notes=Notes(tmp_path/'notes.sqlite3')
    item=notes.add('BARQ','Prefer Egyptian Arabic in BARQ voice')
    assert len(notes.search('Egyptian'))==1
    assert len(notes.search('Egyptian',project='ERP'))==0
    assert notes.delete(item['id'])
    assert not notes.search()

def test_notes_reject_secrets_and_query_length(tmp_path):
    notes=Notes(tmp_path/'notes.sqlite3')
    with pytest.raises(ValueError):notes.add('BARQ','password=topsecret123')
    with pytest.raises(ValueError):notes.add('BARQ','sk-'+'a'*30)
    with pytest.raises(ValueError):notes.search('a'*101)

def test_search_literals_not_sql_wildcards(tmp_path):
    notes=Notes(tmp_path/'notes.sqlite3')
    notes.add('BARQ','literal 100% done')
    assert len(notes.search('100%'))==1
    assert not notes.search('100_')
