import os
import sys
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from services import music_library as library
from services.music_discovery import find_tracks
from services.web_research import public_query
router=APIRouter(prefix='/v1/music',tags=['personal-music'])

@router.get('/discover')
def discover(provider: Literal['spotify', 'anghami'], q: str = Query(min_length=2, max_length=100),
             market: str = Query('SA', pattern=r'^[A-Z]{2}$')):
    if len(q.strip()) < 2 or not public_query('search for ' + q + ' music'):
        raise HTTPException(400, 'Enter a song, album, or artist name.')
    return find_tracks(provider, q.strip().replace('"', ' '), market)

@router.get('/library')
def tracks():return {'tracks':library.tracks()}

class Import(BaseModel):
    mode:Literal['files','folder']='files'

@router.post('/import')
def import_music(request:Import):
    if sys.platform!='win32':raise HTTPException(501,'Local music import requires the Windows desktop app.')
    try:
        import mutagen  # fail before showing a picker when packaging is incomplete
        from tkinter import Tk,filedialog
        root=Tk();root.withdraw();root.attributes('-topmost',True)
        try:
            if request.mode=='folder':
                chosen=filedialog.askdirectory(parent=root,title='BARQ ONE — Music folder')
                paths=[]
                if chosen:
                    for base,dirs,files in os.walk(chosen,followlinks=False):
                        dirs[:]=[d for d in dirs if not (Path(base)/d).is_symlink()]
                        paths.extend(str(Path(base)/f) for f in files if Path(f).suffix.lower() in library.EXTENSIONS)
                        if len(paths)>=5000:break
            else:paths=list(filedialog.askopenfilenames(parent=root,title='BARQ ONE — Import music',filetypes=[('Audio','*.mp3 *.m4a *.aac *.flac *.ogg *.opus *.wav')]))
        finally:root.destroy()
    except Exception as exc:raise HTTPException(503,'Music import unavailable. Check the desktop installation and try again.') from exc
    if not paths:return {'cancelled':True,'tracks':library.tracks()}
    result=library.import_selected(paths[:5000]);result['limited']=len(paths)>=5000
    return result

@router.get('/stream/{identifier}')
def stream(identifier:str):
    try:p=library.source(identifier)
    except ValueError as exc:raise HTTPException(404,str(exc)) from exc
    return FileResponse(p)

@router.get('/art/{identifier}')
def art(identifier:str):
    if len(identifier)!=24 or any(c not in '0123456789abcdef' for c in identifier):raise HTTPException(404)
    for ext in ('.jpg','.png'):
        p=library.folder()/(identifier+ext)
        if p.is_file():return FileResponse(p,media_type='image/jpeg' if ext=='.jpg' else 'image/png',headers={'Cache-Control':'private, max-age=3600'})
    raise HTTPException(404)
