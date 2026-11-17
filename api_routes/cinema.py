from typing import Literal
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from services import cinema_catalog as catalog
router=APIRouter(prefix='/v1/cinema',tags=['cinema'])

def call(fn,*args,**kwargs):
    try: return fn(*args,**kwargs)
    except catalog.CatalogError as exc: raise HTTPException(exc.status,str(exc)) from exc

@router.get('/status')
def status(): return {'configured':bool(catalog.token()),'provider':'TMDB'}

class Setup(BaseModel):
    token: str=Field(min_length=20,max_length=2000,pattern=r'^[A-Za-z0-9._-]+$')

@router.post('/setup')
def setup(request:Setup):
    call(catalog.configure,request.token)
    return {'configured':True}

@router.get('/genres')
def genres(kind:Literal['movie','tv']='movie',language:Literal['ar-SA','en-US']='ar-SA'):
    return call(catalog._fetch,'genre/'+kind+'/list',{'language':language})

@router.get('/browse')
def browse(kind:Literal['movie','tv']='movie',collection:Literal['popular','trending','recent','top']='popular',
           query:str=Query('',max_length=200),page:int=Query(1,ge=1,le=500),
           language:Literal['ar-SA','en-US']='ar-SA',genre:int|None=Query(None,ge=1),
           year:int|None=Query(None,ge=1870,le=2100),rating:float=Query(0,ge=0,le=10),anime:bool=False):
    return call(catalog.browse,kind,collection,query,page,language,genre,year,rating,anime)

@router.get('/details/{kind}/{identifier}')
def details(kind:Literal['movie','tv'],identifier:int,language:Literal['ar-SA','en-US']='ar-SA'):
    if identifier<1: raise HTTPException(400,'Invalid title')
    return call(catalog.details,kind,identifier,language)


@router.get('/providers/{kind}/{identifier}')
def providers(kind: Literal['movie', 'tv'], identifier: int, region: str = Query('SA', pattern=r'^[A-Z]{2}$')):
    if identifier < 1:
        raise HTTPException(400, 'Invalid title')
    return call(catalog.watch_providers, kind, identifier, region)
