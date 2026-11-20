/** BARQ's durable local reading metadata lives in barq_library.sqlite3.
 * Existing WebView localStorage remains a fast/offline cache, not the sole copy.
 */
import {requestJSON} from './backend';

const base='/v1/reading/library/state';
const MAX=32768;
let pendingHydration:Promise<void>|undefined;
const pendingWrites=new Set<string>();
const writeQueues=new Map<string,Promise<unknown>>();

function eligible(key:string){
 return key==='barq-stories-v1'||(key.startsWith('barq-reader:')&&key.length<=600);
}
function localSnapshot(){
 const result:Record<string,string>={};
 try{
  for(let i=0;i<localStorage.length&&i<2500;i++){
   const key=localStorage.key(i);
   if(!key||!eligible(key))continue;
   const value=localStorage.getItem(key);
   if(value&&new TextEncoder().encode(value).byteLength<=MAX)result[key]=value;
  }
 }catch{/* User storage can be disabled. */}
 return result;
}

export async function hydrateReadingLocalState():Promise<void>{
 if(pendingHydration)return pendingHydration;
 pendingHydration=(async()=>{
  const before=localSnapshot();
  const res=await requestJSON<{records:Record<string,string>}>(base+'/sync',{
   method:'POST',body:JSON.stringify({records:before}),
  });
  let changed=false;
  for(const [key,value] of Object.entries(res.records)){
   if(!eligible(key)||pendingWrites.has(key)||typeof value!=='string')continue;
   try{
    const current=localStorage.getItem(key);
    if(current!==null&&current!==before[key])continue; // edited during synchronization
    if(current!==value){localStorage.setItem(key,value);changed=true;}
   }catch{/* Leave reading working in private mode. */}
  }
  if(changed)window.dispatchEvent(new Event('barq:reading-state-hydrated'));
 })().finally(()=>{pendingHydration=undefined;});
 return pendingHydration;
}

export function saveReadingLocalState(key:string,value:string):void{
 if(!eligible(key)||new TextEncoder().encode(value).byteLength>MAX)return;
 try{localStorage.setItem(key,value);}catch{/* API storage still works. */}
 pendingWrites.add(key);
 const prior=writeQueues.get(key)||Promise.resolve();
 const queued=prior.catch(()=>{}).then(()=>requestJSON<{saved:boolean}>(base+'/'+encodeURIComponent(key),{
  method:'PUT',body:JSON.stringify({value}),
 })).catch(()=>{}).finally(()=>{if(writeQueues.get(key)===queued){writeQueues.delete(key);pendingWrites.delete(key);}});
 writeQueues.set(key,queued);
}

export async function loadReadingLocalState(key:string):Promise<string|null>{
 if(!eligible(key))return null;
 const before=localSnapshot();
 const fallback=before[key]||null;
 try{
  const res=await requestJSON<{value:string|null}>(base+'/'+encodeURIComponent(key));
  if(res.value!==null){
   try{if(!pendingWrites.has(key))localStorage.setItem(key,res.value);}catch{}
   return res.value;
  }
  if(fallback!==null)saveReadingLocalState(key,fallback);
 }catch{/* Reader keeps last cached progress offline. */}
 return fallback;
}
