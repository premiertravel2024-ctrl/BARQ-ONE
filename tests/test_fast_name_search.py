import asyncio
from pathlib import Path
from contextlib import closing
from threading import Event
from types import SimpleNamespace as NS
import time
import pytest
from launcher.indexes import Index
from launcher.resolver import Resolver
from computer_control.safety.policy import Policy
from services.name_search import query_from_request


def make_resolver(tmp_path):
 root=tmp_path/'Desktop';root.mkdir()
 def no_apps():raise AssertionError('A folder/file command must never enumerate apps or call PowerShell')
 return root,Resolver(Index(tmp_path/'index.sqlite',[root]),Policy(enabled=True,direct_commands=True,allowed_folders=[str(root)]),app_source=no_apps)


def test_cold_index_finds_iata_report_without_model_or_app_inventory(tmp_path,monkeypatch):
 root,r=make_resolver(tmp_path)
 (root/'IATA REPORT').mkdir();(root/'IATA REPORT OLD').mkdir()
 monkeypatch.setattr('socket.socket.connect',lambda *a,**kw: (_ for _ in ()).throw(AssertionError('No network')))
 start=time.monotonic();result=r.resolve('افتح فولدر IATA REPORT')
 assert result.decision=='auto' and len(result.candidates)==1
 assert result.candidates[0]['path_or_appid']==str(root/'IATA REPORT')
 assert time.monotonic()-start<1.0
 # The warm lookup must use cached metadata and still open the exact destination.
 r.index.allowed_roots=lambda: (_ for _ in ()).throw(AssertionError('Warm lookup must not rescan'))
 assert r.resolve('افتح فولدر IATA REPORT').decision=='auto'


def test_similar_folder_never_auto_opens_and_duplicates_show_real_locations(tmp_path):
 root,r=make_resolver(tmp_path)
 (root/'IATA REPORT OLD').mkdir()
 out=r.resolve('افتح فولدر IATA REPORT')
 assert out.decision=='choose'
 (root/'IATA REPORT').mkdir();other=root/'2026';other.mkdir();(other/'IATA REPORT').mkdir()
 out=r.resolve('افتح فولدر IATA REPORT')
 assert out.decision=='choose'
 assert {Path(c['path_or_appid']).parent.name for c in out.candidates}=={'Desktop','2026'}


def test_missing_folder_is_local_not_found_and_deadline_is_visible(tmp_path):
 root,r=make_resolver(tmp_path)
 for i in range(20):(root/f'item-{i}').mkdir()
 assert r.resolve('افتح فولدر definitely-missing').decision=='not_found'
 assert r.index.find_paths('missing',max_entries=1)==[]
 assert r.index.last_folder_search['truncated'] is True


def test_filename_and_stem_lookup_never_choose_a_similar_document(tmp_path):
 root,r=make_resolver(tmp_path)
 (root/'Sales 2026.xlsx').write_text('one');(root/'Sales 2026 old.xlsx').write_text('two')
 exact=r.resolve('افتح ملف Sales 2026.xlsx')
 assert exact.decision=='auto'
 stem=r.resolve('افتح ملف Sales 2026')
 assert stem.decision=='choose'
 assert r.resolve('افتح ملف Sales').decision=='choose'


@pytest.mark.parametrize('text,kind,query',[
 ('دورلي على ملف IATA REPORT.xlsx جوا الجهاز','file','iata report.xlsx'),
 ('ابحث عن فولدر IATA REPORT','folder','iata report'),
 ('فين ملف اسمه report.pdf','file','report.pdf'),
 ('search for file Budget.xlsx','file','budget.xlsx'),
])
def test_search_words_keep_literal_name(text,kind,query):
 found=query_from_request(text)
 assert found and found[0]==kind and found[1].casefold()==query


def test_global_index_stores_folder_names_and_keeps_connections_closed(tmp_path,monkeypatch):
 from services import device_index
 root=tmp_path/'Documents';root.mkdir();(root/'IATA REPORT').mkdir()
 (root/'IATA REPORT'/'Report.pdf').write_text('data')
 state=tmp_path/'state';state.mkdir()
 monkeypatch.setattr(device_index,'state_file',lambda name:state/name)
 result=device_index._scan([root],Event())
 assert result['entries']==1
 with closing(device_index._connect()) as db:
  assert db.execute("SELECT name FROM files WHERE kind='folder'").fetchall()==[('IATA REPORT',)]
  assert db.execute("SELECT name FROM files WHERE kind='file'").fetchall()==[('Report.pdf',)]

 from services.name_search import indexed_names
 import core.paths
 monkeypatch.setattr(core.paths,'state_file',lambda name:state/name)
 device_index.configure(enabled=True)
 assert indexed_names('IATA REPORT','folder',[root])[0]['path']==str(root/'IATA REPORT')
 assert indexed_names('Report','file',[root])[0]['path']==str(root/'IATA REPORT'/'Report.pdf')
 assert indexed_names('IATA REPORT','folder',[tmp_path/'different-root'])==[]
