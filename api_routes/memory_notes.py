from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from memory.notes import notes

router=APIRouter(prefix='/v1/memory',tags=['local-memory'])

class AddNote(BaseModel):
    project:str=Field(min_length=1,max_length=80)
    text:str=Field(min_length=3,max_length=1000)

@router.get('/notes')
def list_notes(query:str='',project:str='',limit:int=20):
    try:return {'notes':notes().search(query,project,limit),'scope':'user-approved local-only notes'}
    except ValueError as exc:raise HTTPException(400,str(exc))

@router.post('/notes')
def add_note(item:AddNote):
    try:return notes().add(item.project,item.text)
    except ValueError as exc:raise HTTPException(400,str(exc))

@router.delete('/notes/{note_id}')
def delete_note(note_id:str):
    try:return {'deleted':notes().delete(note_id)}
    except ValueError as exc:raise HTTPException(400,str(exc))
