"""WINTER MUSIC import preserves original audio bytes and keeps a durable library."""
from pathlib import Path
from zipfile import ZipFile, ZIP_STORED

import pytest
from services import music_library as music

FORMATS={
 "WINTER MUSIC 01.webm":b"\x1a\x45\xdf\xa3"+b"webm opus test bytes"*6,
 "WINTER MUSIC 02.m4a":b"\x00\x00\x00\x18ftypM4A "+b"aac test bytes"*10,
 "WINTER MUSIC 03.m4a":b"\x00\x00\x00\x18ftypM4A "+b"aac second test bytes"*9,
}

def setup(tmp_path,monkeypatch):
 monkeypatch.setattr(music,"data_dir",lambda:tmp_path)
 archive=tmp_path/"WINTER MUSIC.zip"
 with ZipFile(archive,"w",compression=ZIP_STORED) as pkg:
  for name,contents in FORMATS.items():
   pkg.writestr("WINTER MUSIC/"+name,contents)
  pkg.writestr("WINTER MUSIC/WINTER MUSIC playlist.json",'{"album":"WINTER MUSIC"}')
 return archive

def test_import_winter_zip_adds_all_three_tracks_with_persistent_paths(tmp_path,monkeypatch):
 archive=setup(tmp_path,monkeypatch)
 result=music.import_winter_pack(archive)
 assert result["collection"]=="WINTER MUSIC"
 assert [r["title"] for r in result["imported"]]==[
  "WINTER MUSIC 01","WINTER MUSIC 02","WINTER MUSIC 03"
 ]
 assert len(result["tracks"])==3
 assert all(t["album"]=="WINTER MUSIC" and "path" not in t for t in result["tracks"])
 for item in result["imported"]:
  stored=music.source(item["id"])
  assert stored.parent==tmp_path/"music"/"WINTER MUSIC"
  assert stored.read_bytes()==FORMATS[stored.name]
 archive.unlink()
 assert len(music.tracks())==3
 assert len(music.import_winter_pack(setup(tmp_path,monkeypatch))["tracks"])==3

def test_incomplete_winter_zip_cannot_claim_success(tmp_path,monkeypatch):
 monkeypatch.setattr(music,"data_dir",lambda:tmp_path)
 archive=tmp_path/"WINTER MUSIC.zip"
 with ZipFile(archive,"w") as z:
  z.writestr("WINTER MUSIC/WINTER MUSIC 01.webm",FORMATS["WINTER MUSIC 01.webm"])
 with pytest.raises(ValueError,match="all three"):
  music.import_winter_pack(archive)
 assert music.tracks()==[]

def test_reject_mislabeled_file_and_never_create_playable_index(tmp_path,monkeypatch):
 archive=setup(tmp_path,monkeypatch)
 with ZipFile(archive,"a") as z:
  # Duplicate archive entries must fail rather than silently select one.
  z.writestr("WINTER MUSIC/WINTER MUSIC 03.m4a",b"dangerous fake file")
 with pytest.raises(ValueError,match="all three"):
  music.import_winter_pack(archive)
 assert music.tracks()==[]

def test_unsupported_webm_data_is_rejected(tmp_path,monkeypatch):
 archive=setup(tmp_path,monkeypatch)
 archive.unlink()
 with ZipFile(archive,"w") as z:
  for name,blob in FORMATS.items():
   z.writestr("WINTER MUSIC/"+name,b"not a real webm format"*5 if name.endswith("webm") else blob)
 with pytest.raises(ValueError,match="mislabeled"):
  music.import_winter_pack(archive)
 assert music.tracks()==[]
