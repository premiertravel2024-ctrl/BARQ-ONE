/** BARQ reading-state durability guardian.
 *
 * A localStorage cache keeps the reader responsive. An explicit durable outbox
 * survives restarts when the local SQLite API is temporarily unavailable.
 * Dirty edits replay BEFORE hydration, preventing an older DB record from
 * silently replacing a newer page or favourite.
 */
import {requestJSON} from './backend';

const base='/v1/reading/library/state';
const JOURNAL='barq-reading-pending-v2';
const MAX=32768;
const MAX_PENDING=250;
type ReadingStorageStatus={pending:number;error:string|null};
let lastError:string|null=null;
let pendingHydration:Promise<void>|undefined;
let operationQueue:Promise<unknown>=Promise.resolve();
const memoryPending=new Map<string,string>();

function eligible(key:string){
 return key==='barq-stories-v1'||(key.startsWith('barq-reader:')&&key.length<=600);
}
function validValue(value:unknown):value is string{
 if(typeof value!=='string'||new TextEncoder().encode(value).byteLength>MAX)return false;
 try{
  const parsed=JSON.parse(value) as unknown;
  return parsed!==null&&typeof parsed==='object'&&!Array.isArray(parsed);
 }catch{return false;}
}
function readJournal():Record<string,string>{
 try{
  const data=JSON.parse(localStorage.getItem(JOURNAL)||'{}') as unknown;
  if(!data||typeof data!=='object'||Array.isArray(data))return {};
  const entries=Object.entries(data).filter(([key,value])=>eligible(key)&&validValue(value)).slice(0,MAX_PENDING);
  return Object.fromEntries(entries);
 }catch{return {};}
}
function pendingSnapshot():Record<string,string>{
 return {...readJournal(),...Object.fromEntries(memoryPending)};
}
function emitStatus(){
 if(typeof window!=='undefined')
  window.dispatchEvent(new CustomEvent<ReadingStorageStatus>('barq:reading-storage-status',{
   detail:{pending:Object.keys(pendingSnapshot()).length,error:lastError},
  }));
}
export function getReadingStorageStatus():ReadingStorageStatus{
 return {pending:Object.keys(pendingSnapshot()).length,error:lastError};
}
function updateJournal(key:string,value:string){
 memoryPending.set(key,value);
 try{
  const next={...readJournal(),[key]:value};
  if(Object.keys(next).length>MAX_PENDING){
   lastError='Too many offline reading changes; reconnect to save them.';
  }else localStorage.setItem(JOURNAL,JSON.stringify(next));
 }catch{
  lastError='Unable to persist the offline save queue on this device.';
 }
 emitStatus();
}
function clearPendingIfCurrent(key:string,value:string){
 if(memoryPending.get(key)===value)memoryPending.delete(key);
 try{
  const saved=readJournal();
  if(saved[key]===value){
   delete saved[key];
   if(Object.keys(saved).length)localStorage.setItem(JOURNAL,JSON.stringify(saved));
   else localStorage.removeItem(JOURNAL);
  }
 }catch{
  lastError='Unable to clear the local save queue.';
 }
 if(!Object.keys(pendingSnapshot()).length)lastError=null;
 emitStatus();
}
function schedule<T>(job:()=>Promise<T>):Promise<T>{
 const promise=operationQueue.then(job,job);
 operationQueue=promise.then(()=>undefined,()=>undefined);
 return promise;
}
function localSnapshot():Record<string,string>{
 const result:Record<string,string>={};
 try{
  for(let i=0;i<localStorage.length&&i<2500;i++){
   const key=localStorage.key(i);
   if(!key||!eligible(key))continue;
   const value=localStorage.getItem(key);
   if(value&&validValue(value))result[key]=value;
   if(Object.keys(result).length>=250)break;
  }
 }catch{/* Leave the UI usable when WebView storage is disabled. */}
 return result;
}

export async function retryReadingLocalState():Promise<boolean>{
 try{
  await schedule(async()=>{
   const records=pendingSnapshot();
   const keys=Object.keys(records);
   if(!keys.length)return;
   if(keys.length>MAX_PENDING)throw new Error('Too many queued reading changes');
   // Keep each transaction below the API's 2 MB limit, including large bookmarks.
   for(let offset=0;offset<keys.length;offset+=40){
    const slice=keys.slice(offset,offset+40);
    const batch=Object.fromEntries(slice.map(key=>[key,records[key]]));
    const reply=await requestJSON<{saved:number}>(base+'/flush',{
     method:'POST',body:JSON.stringify({records:batch}),
    });
    if(reply.saved!==slice.length)throw new Error('SQLite did not confirm all reading changes');
    for(const key of slice)clearPendingIfCurrent(key,records[key]);
   }
  });
  if(!Object.keys(pendingSnapshot()).length)lastError=null;
  emitStatus();
  return true;
 }catch{
  lastError='Reading changes are still pending on this device. Retry after reconnecting.';
  emitStatus();
  return false;
 }
}
export async function hydrateReadingLocalState():Promise<void>{
 if(pendingHydration)return pendingHydration;
 pendingHydration=(async()=>{
  // Replay previous-session edits before reading possibly stale DB values.
  await retryReadingLocalState();
  const before=localSnapshot();
  const res=await requestJSON<{records:Record<string,string>}>(base+'/sync',{
   method:'POST',body:JSON.stringify({records:before}),
  });
  let changed=false;
  for(const [key,value] of Object.entries(res.records)){
   if(!eligible(key)||!validValue(value)||pendingSnapshot()[key]!==undefined)continue;
   try{
    const current=localStorage.getItem(key);
    if(current!==null&&current!==before[key])continue; // modified while syncing
    if(current!==value){localStorage.setItem(key,value);changed=true;}
   }catch{/* Do not break the reader in privacy mode. */}
  }
  if(changed)window.dispatchEvent(new Event('barq:reading-state-hydrated'));
 })().finally(()=>{pendingHydration=undefined;});
 return pendingHydration;
}
export function saveReadingLocalState(key:string,value:string):void{
 if(!eligible(key))return;
 if(!validValue(value)){
  lastError='Reading data is too large or invalid; the change was not saved.';
  emitStatus();
  return;
 }
 try{localStorage.setItem(key,value);}catch{
  lastError='Reading cache unavailable; checking durable SQLite save.';
 }
 // The outbox must be marked BEFORE any asynchronous network request.
 updateJournal(key,value);
 void schedule(async()=>{
  if(pendingSnapshot()[key]!==value)return; // a newer edit superseded this request
  const reply=await requestJSON<{saved:boolean}>(base+'/'+encodeURIComponent(key),{
   method:'PUT',body:JSON.stringify({value}),
  });
  if(reply.saved!==true)throw new Error('SQLite did not confirm save');
  clearPendingIfCurrent(key,value);
 }).catch(()=>{
  lastError='Reading save not confirmed. Your pending changes will be retried.';
  emitStatus();
 });
}
export async function loadReadingLocalState(key:string):Promise<string|null>{
 if(!eligible(key))return null;
 const pending=pendingSnapshot()[key];
 if(pending!==undefined)return pending; // never restore stale SQLite over dirty local data
 const before=localSnapshot();
 const fallback=before[key]||null;
 try{
  const res=await requestJSON<{value:string|null}>(base+'/'+encodeURIComponent(key));
  if(pendingSnapshot()[key]!==undefined)return pendingSnapshot()[key];
  if(res.value!==null&&validValue(res.value)){
   try{localStorage.setItem(key,res.value);}catch{}
   return res.value;
  }
  if(fallback!==null)saveReadingLocalState(key,fallback);
 }catch{
  if(fallback!==null)saveReadingLocalState(key,fallback);
 }
 return fallback;
}
