import {useApp,type Conversation} from '../store';
import {requestJSON,deleteConversation} from './backend';

type RecordValue={at:number;value:string|null};
type Records=Record<string,RecordValue>;
const root='/v1/reading/drive';
const portable=['theme','language','voiceId','sidebarCollapsed','selectedModel'] as const;
const isReadingKey=(key:string)=>key.startsWith('barq-reader:')||key==='barq-stories-v1';
const isPortableKey=(key:string)=>portable.some(option=>key==='option:'+option)||key.startsWith('chat:')||isReadingKey(key);
const journal='barq-drive-sync-journal-v1';

function snapshot():Record<string,string>{
 const current=useApp.getState();
 const values:Record<string,string>={};
 for(const option of portable)values['option:'+option]=JSON.stringify(current[option]);
 for(const chat of current.chats){
  if(chat.messages.some(message=>message.isStreaming))continue;
  const messages=chat.messages.map(({agentTask:_task,toolRequest:_tool,attachments:_attachments,...message})=>message);
  values['chat:'+chat.id]=JSON.stringify({...chat,messages});
 }
 for(let index=0;index<localStorage.length;index++){
  const key=localStorage.key(index);
  if(key&&isReadingKey(key)){
   const value=localStorage.getItem(key);
   if(value!==null)values[key]=value;
  }
 }
 return values;
}

function apply(key:string,value:string|null){
 if(isReadingKey(key)){
  if(value===null)localStorage.removeItem(key);
  else localStorage.setItem(key,value);
  return;
 }
 if(key.startsWith('chat:')){
  const id=key.slice(5);
  const current=useApp.getState();
  if(current.chats.find(chat=>chat.id===id)?.messages.some(message=>message.isStreaming))return;
  if(value===null){
   if(current.chats.some(chat=>chat.id===id)){
    current.deleteChat(id);
    void deleteConversation(id).catch(()=>{});
   }
   return;
  }
  const chat=JSON.parse(value) as Conversation;
  if(chat.id!==id||!Array.isArray(chat.messages)||typeof chat.title!=='string')return;
  useApp.setState({chats:[chat,...current.chats.filter(item=>item.id!==id)].sort((a,b)=>b.updatedAt-a.updatedAt)});
  return;
 }
 if(value===null)return;
 const option=key.slice(7);
 const decoded:unknown=JSON.parse(value);
 if(option==='theme'&&(decoded==='dark'||decoded==='light'))useApp.getState().setTheme(decoded);
 if(option==='language'&&(decoded==='ar'||decoded==='en'))useApp.getState().setLanguage(decoded);
 if(option==='selectedModel'&&typeof decoded==='string')useApp.getState().setModel(decoded);
 if(option==='voiceId'&&typeof decoded==='string')useApp.setState({voiceId:decoded});
 if(option==='sidebarCollapsed'&&typeof decoded==='boolean')useApp.setState({sidebarCollapsed:decoded});
}

export function startDriveSync(){
 let busy=false,alive=true,applying=false;
 const deleted=new Map<string,number>();
 const unsubscribe=useApp.subscribe((current,previous)=>{
  if(applying||current.chats===previous.chats)return;
  const remaining=new Set(current.chats.map(chat=>chat.id));
  for(const chat of previous.chats)if(!remaining.has(chat.id))deleted.set('chat:'+chat.id,Date.now());
  for(const id of remaining)deleted.delete('chat:'+id);
 });
 async function tick(){
  if(busy||!alive)return;
  busy=true;
  try{
   const status=await requestJSON<{sync?:boolean}>(root+'/status');
   if(!status.sync||!alive)return;
   let device=localStorage.getItem('barq-drive-sync-device');
   if(!device){device=crypto.randomUUID().replaceAll('-','');localStorage.setItem('barq-drive-sync-device',device);}
   const history=JSON.parse(localStorage.getItem(journal)||'{}') as Records;
   const before=snapshot();
   const outgoing:Records={};
   for(const [key,value] of Object.entries(before)){
    if(!history[key])outgoing[key]={at:0,value};
    else if(history[key].value!==value)outgoing[key]={at:Math.max(Date.now(),history[key].at+1),value};
   }
   for(const [key,entry] of Object.entries(history)){
    if(!(key in before)&&entry.value!==null&&isReadingKey(key))outgoing[key]={at:Math.max(Date.now(),entry.at+1),value:null};
   }
   for(const [key,at] of deleted)outgoing[key]={at,value:null};
   const result=await requestJSON<{records:Records}>(root+'/sync',{method:'POST',body:JSON.stringify({device,records:outgoing})});
   if(!alive)return;
   const after=snapshot();
   for(const [key,entry] of Object.entries(result.records)){
    if(!isPortableKey(key)||after[key]!==before[key]||!(entry.value===null||typeof entry.value==='string'))continue;
    try{
     applying=true;
     if((after[key]??null)!==entry.value)apply(key,entry.value);
     history[key]=entry;
     if(deleted.get(key)===entry.at&&entry.value===null)deleted.delete(key);
    }catch{/* A malformed or incompatible entry does not stop other preferences. */}
    finally{applying=false;}
   }
   localStorage.setItem(journal,JSON.stringify(history));
  }catch{/* Local BARQ remains usable offline. */}
  finally{busy=false;}
 }
 const wake=()=>void tick();
 const timer=window.setInterval(wake,45000);
 window.addEventListener('barq:drive-sync',wake);
 void tick();
 return()=>{alive=false;unsubscribe();window.clearInterval(timer);window.removeEventListener('barq:drive-sync',wake);};
}
