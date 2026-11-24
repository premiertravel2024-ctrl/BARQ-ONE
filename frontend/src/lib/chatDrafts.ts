import type {UploadedAttachment} from '../store';
import {releaseAttachment} from './attachmentRegistry';

// Attachment bytes are kept in memory. Only draft text is saved on disk.
export const draftFiles=new Map<string,UploadedAttachment[]>();
export const loadingDrafts=new Set<string>();
export const draftEvents=new EventTarget();
const key=(id:string)=>'barq-chat-draft:'+id;

export function readDraft(id:string){
 try{return localStorage.getItem(key(id))||''}catch{return ''}
}

export function writeDraft(id:string,text:string){
 try{
  if(text)localStorage.setItem(key(id),text);
  else localStorage.removeItem(key(id));
 }catch{/* Storage may be unavailable. */}
}

export function removeDraft(id:string){
 writeDraft(id,'');
 for(const attachment of draftFiles.get(id)||[])releaseAttachment(attachment.id);
 draftFiles.delete(id);
 loadingDrafts.delete(id);
 draftEvents.dispatchEvent(new Event(id));
}
