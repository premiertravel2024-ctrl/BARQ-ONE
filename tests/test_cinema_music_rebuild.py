from pathlib import Path
from unittest.mock import Mock
import json
import wave
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from services import cinema_catalog as catalog

@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    catalog._cache.clear();catalog._retry_at=0
    monkeypatch.setattr(catalog,'token',lambda:'test-token')

def test_catalog_no_key_is_explicit(monkeypatch):
    monkeypatch.setattr(catalog,'token',lambda:'')
    with pytest.raises(catalog.CatalogError,match='TMDB_SETUP_REQUIRED'):catalog.browse()

def test_discovery_forwards_filters_and_never_invents_ratings(monkeypatch):
    fetch=Mock(return_value={'page':2,'total_pages':900,'total_results':10000,'results':[{'id':12,'title':'Actual title','vote_average':9,'vote_count':0}]})
    monkeypatch.setattr(catalog,'_fetch',fetch)
    result=catalog.browse(kind='movie',page=2,year=2025,genre=18,rating=7,anime=True)
    path,params=fetch.call_args.args
    assert path=='discover/movie' and params['with_genres']=='18,16'
    assert params['with_original_language']=='ja' and params['primary_release_year']==2025
    assert params['page']==2 and params['vote_average.gte']==7
    assert result['total_pages']==500 and result['results'][0]['rating'] is None
    assert result['results'][0]['poster'] is None

def test_search_is_remote_not_six_titles(monkeypatch):
    fetch=Mock(return_value={'page':4,'total_pages':8,'results':[]})
    monkeypatch.setattr(catalog,'_fetch',fetch)
    result=catalog.browse(kind='tv',query='test search',page=4)
    assert fetch.call_args.args[0]=='search/tv'
    assert fetch.call_args.args[1]['query']=='test search'
    assert result['page']==4

def test_http_cache_and_auth_header(monkeypatch):
    response=Mock(status_code=200);response.json.return_value={'results':[]}
    client=Mock();client.__enter__=Mock(return_value=client);client.__exit__=Mock(return_value=False);client.get.return_value=response
    monkeypatch.setattr(catalog.httpx,'Client',Mock(return_value=client))
    catalog._fetch('discover/movie',{'page':1});catalog._fetch('discover/movie',{'page':1})
    assert client.get.call_count==1
    assert client.get.call_args.kwargs['headers']['Authorization']=='Bearer test-token'
    assert 'api_key' not in client.get.call_args.kwargs['params']

def test_rate_limit_honors_retry_without_hammering(monkeypatch):
    response=Mock(status_code=429,headers={'retry-after':'20'})
    client=Mock();client.__enter__=Mock(return_value=client);client.__exit__=Mock(return_value=False);client.get.return_value=response
    monkeypatch.setattr(catalog.httpx,'Client',Mock(return_value=client))
    for _ in range(2):
        with pytest.raises(catalog.CatalogError) as e:catalog._fetch('discover/movie',{})
        assert e.value.status==429
    assert client.get.call_count==1

def test_cinema_route_validation():
    from api_routes.cinema import router
    app=FastAPI();app.include_router(router);client=TestClient(app)
    assert client.get('/v1/cinema/browse?page=501').status_code==422
    assert client.get('/v1/cinema/browse?kind=person').status_code==422
    assert client.get('/v1/cinema/status').json()=={'configured':True,'provider':'TMDB'}

def test_music_metadata_and_persistence(monkeypatch,tmp_path):
    from services import music_library as music
    monkeypatch.setattr(music,'folder',lambda:tmp_path)
    file=tmp_path/'real.wav'
    with wave.open(str(file),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(b'\0\0'*8000)
    from mutagen.wave import WAVE
    from mutagen.id3 import TIT2,TPE1,TALB
    audio=WAVE(file);audio.add_tags();audio.tags.add(TIT2(encoding=3,text='My title'));audio.tags.add(TPE1(encoding=3,text='My artist'));audio.tags.add(TALB(encoding=3,text='My album'));audio.save()
    result=music.import_selected([file]);t=result['tracks'][0]
    assert t['title']=='My title' and t['artist']=='My artist' and t['album']=='My album'
    assert t['duration']==1 and 'path' not in t
    assert music.source(t['id'])==file
    music.import_selected([file]);assert len(music.tracks())==1
    file.unlink()
    with pytest.raises(ValueError,match='unavailable'):music.source(t['id'])
    with pytest.raises(ValueError):music.source('../../etc/passwd')

def test_native_apply_routes_to_native_manifest(monkeypatch):
    from api_routes import lively
    from services import native_wallpaper as native
    monkeypatch.setattr(lively,'_native_enabled',lambda:True)
    monkeypatch.setattr(lively,'_consent',lambda:None)
    monkeypatch.setattr(lively,'_wallpaper',Mock(side_effect=AssertionError('Legacy manifest used')))
    apply=Mock(return_value={'status':'attached','verified':True})
    monkeypatch.setattr(native,'apply',apply)
    assert lively.wallpaper_action(lively.Action(action='apply',wallpaper_id='a'*24))['verified']
    apply.assert_called_once_with('a'*24)

def test_native_decoder_failure_is_preserved(monkeypatch,tmp_path):
    from services import native_wallpaper as native
    monkeypatch.setattr(native,'supported',lambda:True)
    monkeypatch.setattr(native,'_file',lambda ident:tmp_path/'file.mp4')
    monkeypatch.setattr(native,'_folder',lambda:tmp_path)
    process=Mock(pid=42);process.poll.return_value=None
    monkeypatch.setattr(native.subprocess,'Popen',Mock(return_value=process))
    monkeypatch.setattr(native,'_state',lambda:{'pid':42})
    monkeypatch.setattr(native,'_request',lambda *a:{'error':'Decoder failed'})
    def stop():native._process=None
    monkeypatch.setattr(native,'stop',stop)
    with pytest.raises(RuntimeError,match='Decoder failed'):native.apply('a'*24)
