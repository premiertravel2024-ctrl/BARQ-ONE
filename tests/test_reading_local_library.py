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
        'position':1,'published':True,
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
    assert updated['title'] == '01 - Episode'
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
    first, second, other = books.values()
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
