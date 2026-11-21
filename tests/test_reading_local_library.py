"""Owner-managed BARQ library regression tests; no real Google credentials required."""
import sqlite3
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_routes import reading_local_library


def client(tmp_path, monkeypatch):
    destination = tmp_path / 'barq_library.sqlite3'
    monkeypatch.setattr(reading_local_library, 'db_path', lambda: destination)
    app = FastAPI()
    app.include_router(reading_local_library.router)
    return TestClient(app), destination


def test_default_private_and_series_changes_survive_drive_resync(tmp_path, monkeypatch):
    test, db_path = client(tmp_path, monkeypatch)
    from api_routes import reading_drive

    listings = [[
        {'id':'abcdefghijklmnop', 'title':'01 - Episode', 'group':'Series A', 'cover':None},
        {'id':'qrstuvwxyzABCDEF', 'title':'02 - Episode', 'group':'Series A', 'cover':None},
    ]]
    monkeypatch.setattr(reading_drive, 'catalogue', lambda: {'books':listings[0]})
    assert test.post('/library/refresh').json()['synced'] == 2

    data = test.get('/library/items').json()
    assert len(data['books']) == 2
    assert all(book['published'] == 0 for book in data['books'])

    created = test.post('/library/series', json={'title':'Series A'}).json()
    assert created['title'] == 'Series A'
    save = test.post('/library/book', json={
        'id':'abcdefghijklmnop','series_id':created['id'],'issue_number':1,
        'position':1,'published':True,'title':'Owner edited Episode',
    })
    assert save.status_code == 200

    # Source title changes do not override the owner's series mapping or publication.
    listings[0] = [
        {'id':'abcdefghijklmnop','title':'Episode renamed on Drive','group':'Series A','cover':None},
    ]
    assert test.post('/library/refresh').json()['synced'] == 1
    snapshot = test.get('/library/items').json()
    updated = next(book for book in snapshot['books'] if book['id'] == 'abcdefghijklmnop')
    removed = next(book for book in snapshot['books'] if book['id'] == 'qrstuvwxyzABCDEF')
    assert updated['title'] == 'Owner edited Episode'
    assert updated['published'] == 1
    assert updated['series_id'] == created['id']
    assert updated['issue_number'] == 1
    assert removed['active'] == 0

    with sqlite3.connect(db_path) as db:
        assert db.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'


def test_invalid_edit_is_rejected_and_not_published(tmp_path, monkeypatch):
    test, _ = client(tmp_path, monkeypatch)
    assert test.post('/library/book', json={'id':'bad id','published':True}).status_code == 422
    assert test.post('/library/book', json={'id':'abcdefghijklmnop','published':True}).status_code == 404
    assert test.post('/library/series',json={'title':'  '}).status_code == 422
    assert test.delete('/library/series/not-a-uuid').status_code == 422


def test_local_database_location_can_be_configured(tmp_path, monkeypatch):
    monkeypatch.setenv('BARQ_READING_DB_DIR',str(tmp_path))
    assert reading_local_library.db_path() == tmp_path / 'barq_library.sqlite3'



def test_auto_index_groups_folder_issues_and_respects_manual_detach(tmp_path, monkeypatch):
    api, _ = client(tmp_path, monkeypatch)
    from api_routes import reading_drive
    pages = [
        {"id":"abcdefghijklmnop","title":"٠١ - مصاص الدماء","group":"Egyptian / ما وراء الطبيعة","cover":None},
        {"id":"qrstuvwxyzABCDEF","title":"002 - أسطورة النداهة","group":"Egyptian / ما وراء الطبيعة","cover":None},
        {"id":"ABCDEFGHIJKLMNOP","title":"قصة واحدة","group":"كتب","cover":None},
    ]
    monkeypatch.setattr(reading_drive,"catalogue",lambda:{"books":pages})
    scanned = api.post("/library/refresh")
    assert scanned.status_code == 200, scanned.text
    assert scanned.json()["synced"] == 3
    books = {book["id"]:book for book in api.get("/library/items").json()["books"]}
    first = books['abcdefghijklmnop']
    second = books['qrstuvwxyzABCDEF']
    other = books['ABCDEFGHIJKLMNOP']
    assert first["series_id"] == second["series_id"]
    assert first["issue_number"] == 1
    assert second["issue_number"] == 2
    assert other["series_id"] is None
    assert all(item["published"] == 0 for item in books.values())

    # Owner explicitly detaches a book even though it still belongs to the folder.
    assert api.post("/library/book",json={"id":first["id"],"series_id":None}).status_code == 200
    assert api.post("/library/refresh").status_code == 200
    revised = {row["id"]:row for row in api.get("/library/items").json()["books"]}
    assert revised[first["id"]]["series_id"] is None
    assert revised[second["id"]]["series_id"] == second["series_id"]
    assert revised[first["id"]]["manual_series"] == 1
    assert api.post("/library/book/"+first["id"]+"/auto").status_code == 200
    assert {row["id"]:row for row in api.get("/library/items").json()["books"]}[first["id"]]["series_id"] == second["series_id"]


def test_preview_and_bulk_operations_are_safe(tmp_path,monkeypatch):
    api,_=client(tmp_path,monkeypatch)
    from api_routes import reading_drive
    ids=["abcdefghijklmnop","qrstuvwxyzABCDEF"]
    monkeypatch.setattr(reading_drive,"catalogue",lambda:{"books":[
        {"id":identifier,"title":str(n+1)+" - رواية","group":"هاري بوتر","cover":None}
        for n,identifier in enumerate(ids)]})
    assert api.post("/library/refresh").status_code==200
    before=api.get("/library/items").json()
    preview=api.get("/library/preview")
    assert preview.status_code==200 and preview.json()["preview"]
    assert api.get("/library/items").json()==before
    assert api.post("/library/bulk",json={"ids":ids,"hidden":True}).json()["updated"]==2
    assert all(row["hidden"]==1 for row in api.get("/library/items").json()["books"])
    assert api.post("/library/bulk",json={"ids":[ids[0],"invalid!"],"hidden":False}).status_code==422
    assert api.post("/library/bulk",json={"ids":ids,"series_id":"random-value"}).status_code==422
    assert api.post("/library/bulk",json={"ids":ids,"published":True}).status_code==200


def test_series_metadata_edit_merge_and_remove_preserves_manual_rules(tmp_path,monkeypatch):
    api,_=client(tmp_path,monkeypatch)
    from api_routes import reading_drive
    monkeypatch.setattr(reading_drive,"catalogue",lambda:{"books":[
        {"id":"abcdefghijklmnop","title":"01 - Entry","group":"My Series","cover":None}]})
    api.post("/library/refresh")
    first=api.post("/library/series",json={"title":"First"}).json()["id"]
    second=api.post("/library/series",json={"title":"Second"}).json()["id"]
    assert api.post("/library/book",json={"id":"abcdefghijklmnop","series_id":first}).status_code==200
    assert api.post("/library/series/"+first,json={"title":"Changed","position":2,"genre":"مغامرة"}).status_code==200
    assert api.post("/library/merge",json={"source":first,"target":second}).status_code==200
    assert api.get("/library/items").json()["books"][0]["series_id"]==second
    assert api.delete("/library/series/"+second).status_code==200
    assert api.post("/library/refresh").status_code==200
    book=api.get("/library/items").json()["books"][0]
    assert book["series_id"] is None and book["manual_series"]==1



def test_reorder_is_atomic_and_enforces_same_series(tmp_path, monkeypatch):
    api, _ = client(tmp_path, monkeypatch)
    from api_routes import reading_drive
    ids = ["abcdefghijklmnop", "qrstuvwxyzABCDEF", "ABCDEFGHIJKLMNOP"]
    monkeypatch.setattr(reading_drive, "catalogue", lambda: {"books": [
        {"id":id, "title":f"{i+1:02d} - book", "group":"Series Sorted", "cover":None}
        for i, id in enumerate(ids)]})
    assert api.post("/library/refresh").status_code == 200
    assert api.post("/library/reorder", json={"ids":[ids[2], ids[0], ids[1]]}).json()["updated"] == 3
    rows = api.get("/library/items").json()["books"]
    assert [row["id"] for row in rows] == [ids[2], ids[0], ids[1]]
    assert all(row["manual_position"] == 1 for row in rows)
    assert api.post("/library/refresh").status_code == 200
    assert [row["id"] for row in api.get("/library/items").json()["books"]] == [ids[2], ids[0], ids[1]]
    assert api.post("/library/reorder", json={"ids":[ids[1], ids[1]]}).status_code == 422


def test_auto_detection_is_conservative_for_generic_folders(tmp_path,monkeypatch):
    api,_=client(tmp_path,monkeypatch)
    from api_routes import reading_drive
    monkeypatch.setattr(reading_drive,"catalogue",lambda:{"books":[
        {"id":"abcdefghijklmnop","title":"مغامرة مستقلة","group":"روايات","cover":None},
        {"id":"qrstuvwxyzABCDEF","title":"حكايات أخرى","group":"روايات","cover":None},
    ]})
    assert api.post("/library/refresh").status_code==200
    entries=api.get("/library/items").json()["books"]
    assert all(row["series_id"] is None for row in entries)
    assert api.get("/library/status").json()["review"]==2


def test_owner_book_title_and_hidden_state_survive_reindex(tmp_path,monkeypatch):
    api,_=client(tmp_path,monkeypatch)
    from api_routes import reading_drive
    listing=[{"id":"abcdefghijklmnop","title":"Original title","group":"","cover":None}]
    monkeypatch.setattr(reading_drive,"catalogue",lambda:{"books":listing})
    assert api.post("/library/refresh").status_code==200
    assert api.post("/library/book",json={"id":"abcdefghijklmnop","title":"My custom title","hidden":True}).status_code==200
    listing[0]["title"]="Renamed on Drive"
    assert api.post("/library/refresh").status_code==200
    book=api.get("/library/items").json()["books"][0]
    assert book["title"]=="My custom title" and book["source_title"]=="Renamed on Drive"
    assert book["hidden"]==1 and book["manual_title"]==1



def test_reading_progress_and_favorites_survive_reopening_sqlite(tmp_path, monkeypatch):
    api, destination = client(tmp_path, monkeypatch)
    progress = '{"page":51,"marks":[3,51]}'
    favorites = '{"favorites":["egy-zenab","world-dracula"]}'
    assert api.put('/library/state/barq-reader:google:book-01',json={'value':progress}).json()['saved']
    assert api.put('/library/state/barq-stories-v1',json={'value':favorites}).status_code == 200
    reopened, _ = client(tmp_path, monkeypatch)
    assert reopened.get('/library/state/barq-reader:google:book-01').json()['value'] == progress
    assert reopened.get('/library/state/barq-stories-v1').json()['value'] == favorites
    # Browser cache can be blank after a WebView reset: DB remains authoritative.
    snapshot = reopened.post('/library/state/sync',json={'records':{}}).json()['records']
    assert snapshot['barq-reader:google:book-01'] == progress
    assert snapshot['barq-stories-v1'] == favorites
    assert reopened.post('/library/state/sync',json={'records':{'barq-stories-v1':'{"favorites":[]}'}}).json()['records']['barq-stories-v1'] == favorites
    with sqlite3.connect(destination) as con:
        assert con.execute('SELECT COUNT(*) FROM reader_state').fetchone()[0] == 2
        assert con.execute('PRAGMA quick_check(1)').fetchone()[0] == 'ok'
    status = reopened.get('/library/status').json()
    assert status['reading_records'] == 2
    assert status['persistent']
    assert status['last_saved_at']
    assert status['db_bytes'] > 0


def test_backup_snapshot_is_safe_and_has_saved_reading_rows(tmp_path, monkeypatch):
    api, path = client(tmp_path, monkeypatch)
    api.post('/library/series',json={'title':'ما وراء الطبيعة'})
    api.put('/library/state/barq-reader:google:book-42',json={'value':'{"page":42,"marks":[]}'})
    from hashlib import sha256
    image_id = sha256('library-series:backup'.encode()).hexdigest()
    with reading_local_library.LOCK, reading_local_library.database() as db:
        db.execute('INSERT INTO cover_overrides(id,image,modified_ms) VALUES(?,?,?)',
                   (image_id,b'\xff\xd8\xffexample\xff\xd9',1234))
    response = api.post('/library/backup')
    assert response.status_code == 200,response.text
    result = response.json()
    from pathlib import Path
    backup = Path(result['file'])
    assert backup.exists() and backup.parent == path.parent / 'backups'
    with sqlite3.connect(backup) as copy:
        assert copy.execute('PRAGMA quick_check(1)').fetchone()[0] == 'ok'
        assert copy.execute('SELECT COUNT(*) FROM series').fetchone()[0] == 1
        assert copy.execute("SELECT value FROM reader_state WHERE key='barq-reader:google:book-42'").fetchone()[0] == '{"page":42,"marks":[]}'
        assert bytes(copy.execute('SELECT image FROM cover_overrides WHERE id=?',(image_id,)).fetchone()[0]).startswith(b'\xff\xd8\xff')


def test_old_appdata_catalogue_migrates_to_selected_g_drive_without_data_loss(tmp_path, monkeypatch):
    legacy_profile = tmp_path / 'OldProfile'
    old_db = legacy_profile / 'reading' / 'barq_library.sqlite3'
    new_db = tmp_path / 'G_BARQ_DATABASE' / 'barq_library.sqlite3'
    monkeypatch.delenv('BARQ_READING_DB_DIR', raising=False)
    monkeypatch.setattr(reading_local_library, 'data_dir', lambda: legacy_profile)
    monkeypatch.setattr(reading_local_library, 'db_path', lambda: old_db)
    with reading_local_library.LOCK, reading_local_library.database() as db:
        db.execute('INSERT INTO series(id,title) VALUES(?,?)',
                   ('12345678-1234-1234-1234-123456789abc','Legacy saved group'))
        db.execute('INSERT INTO reader_state(key,value) VALUES(?,?)',
                   ('barq-reader:old','{"page":23,"marks":[]}'))
    assert old_db.exists()
    monkeypatch.setattr(reading_local_library, 'db_path', lambda: new_db)
    app = FastAPI()
    app.include_router(reading_local_library.router)
    api = TestClient(app)
    series = api.get('/library/items').json()['series']
    assert len(series) == 1 and series[0]['title'] == 'Legacy saved group'
    assert api.get('/library/state/barq-reader:old').json()['value'] == '{"page":23,"marks":[]}'
    assert old_db.exists() and new_db.exists()
    assert api.get('/library/status').json()['persistent']



def test_dirty_reading_progress_replays_over_stale_database_after_restart(tmp_path, monkeypatch):
    api, destination = client(tmp_path, monkeypatch)
    key = "barq-reader:google:long-book"
    earlier = '{"page":4,"marks":[2]}'
    newest = '{"page":87,"marks":[2,87]}'
    assert api.put('/library/state/'+key, json={"value":earlier}).json() == {"saved": True}
    # Normal initial synchronization should never replace existing stored records.
    assert api.post('/library/state/sync', json={"records":{key:newest}}).json()["records"][key] == earlier
    # Durable outbox replay is an explicit owner edit and must overwrite stale state.
    done = api.post('/library/state/flush', json={"records":{key:newest}})
    assert done.status_code == 200, done.text
    assert done.json() == {"saved":1}
    reopened, _ = client(tmp_path, monkeypatch)
    assert reopened.get('/library/state/'+key).json()["value"] == newest
    assert reopened.get('/library/status').json()["persistent"]
    with sqlite3.connect(destination) as database:
        assert database.execute("PRAGMA quick_check(1)").fetchone()[0] == "ok"


def test_recovery_batch_validates_every_record_before_any_write(tmp_path, monkeypatch):
    api, _ = client(tmp_path, monkeypatch)
    key = "barq-reader:google:novel"
    invalid = api.post('/library/state/flush', json={"records":{
        key:'{"page":25,"marks":[]}',
        "invalid-key":'{"page":1}',
    }})
    assert invalid.status_code == 422
    assert api.get('/library/state/'+key).json()["value"] is None
    invalid_json = api.post('/library/state/flush', json={"records":{key:"broken-json"}})
    assert invalid_json.status_code == 422
    assert api.get('/library/state/'+key).json()["value"] is None
    good = api.post('/library/state/flush', json={"records":{key:'{"page":25,"marks":[]}'}})
    assert good.status_code == 200 and good.json()["saved"] == 1
    assert api.get('/library/state/'+key).json()["value"] == '{"page":25,"marks":[]}'



def test_selected_g_drive_never_falls_back_to_empty_appdata_database(tmp_path,monkeypatch):
    import pytest
    monkeypatch.delenv("BARQ_READING_DB_DIR",raising=False)
    monkeypatch.setattr(reading_local_library,"data_dir",lambda:tmp_path)
    monkeypatch.setattr(reading_local_library,"_PINNED_DB_PATH",None)
    chosen=tmp_path/"reading"/".g_drive_database_selected"
    chosen.parent.mkdir(parents=True)
    chosen.write_text("G:/BARQ DATABASE",encoding="utf-8")
    path=reading_local_library.db_path()
    assert path.as_posix()=="G:/BARQ DATABASE/barq_library.sqlite3"
    with pytest.raises(FileNotFoundError,match="G:"):
        with reading_local_library.LOCK, reading_local_library.database():
            pass
    # Never tell the owner a second, empty catalogue is their actual library.
    assert not (tmp_path/"reading"/"barq_library.sqlite3").exists()
