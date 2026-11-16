import pytest
from launcher.nlu import parse
from launcher.indexes import Index
from launcher.resolver import Resolver
from computer_control.safety.policy import Policy

@pytest.mark.parametrize('prefix',['عاوزك تفتح','عايزك تشغل','يا برق لو سمحت افتح','ممكن تفتح'])
def test_egyptian_requests(prefix):
    assert parse(prefix+' كروم').target_text=='كروم'

@pytest.mark.parametrize('source',['text','voice'])
def test_literal_paths_bypass_index_without_changing_names(tmp_path,source):
    target=tmp_path/'Report, April 2026.txt';target.write_text('private')
    def no_apps():raise AssertionError('Direct path does not need app discovery')
    resolver=Resolver(Index(tmp_path/'index.sqlite',[]),Policy(allowed_folders=[str(tmp_path)]),app_source=no_apps)
    result=resolver.resolve('افتح "'+str(target)+'"',source)
    assert result.decision=='auto' and result.candidates[0]['path_or_appid']==str(target)
    entry=resolver.candidate(result.candidates[0]['id']);assert entry.source==source and entry.realpath==str(target.resolve())
    assert resolver.resolve('افتح '+str(tmp_path/'missing.txt'),source).decision=='not_found'


def test_url_keeps_query_and_case(tmp_path):
    url='https://example.com/Report?Name=April&ID=ABC'
    resolver=Resolver(Index(tmp_path/'index.sqlite',[]),Policy(),app_source=lambda:[])
    result=resolver.resolve('افتح '+url)
    assert result.candidates[0]['path_or_appid']==url


def test_windows_path_keeps_literal_punctuation():
    value=r'C:\Users\Ashraf\My Report, April.PDF'
    assert parse('افتح ملف "'+value+'"').target_text==value


def test_executable_path_still_requires_approval(tmp_path):
    target=tmp_path/'setup.exe';target.write_bytes(b'not executable')
    resolver=Resolver(Index(tmp_path/'index.sqlite',[]),Policy(allowed_folders=[str(tmp_path)]),app_source=lambda:[])
    assert resolver.resolve('افتح '+str(target)).decision=='ask_approval'
