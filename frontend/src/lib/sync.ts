import {useApp,type Conversation} from '../store';
import {loadConversation,loadConversations,loadModels,loadProviders,saveConversation,type RouterProvider} from './backend';

/** Sync from the local Python SQLite store without overwriting newer browser drafts. */
export function startDataSync(onProviders:(items:RouterProvider[])=>void){
 let alive=true;
 const saves=new Map<string,ReturnType<typeof setTimeout>>();
 const revision=new Map<string,number>();
 const refresh=async()=>{
  try{const [models,providers]=await Promise.all([loadModels(),loadProviders()]);if(!alive)return;
   useApp.getState().setAvailableModels(models);onProviders(providers)}catch{if(alive)onProviders([])}
 };
 const hydration=(async()=>{try{
    const list=await loadConversations();const remote=await Promise.all(list.conversations.slice(0,40).map(async item=>{
      try{const raw=await loadConversation(item.id);const messages=Array.isArray(raw.messages)?raw.messages:[];
       return {id:item.id,title:raw.title,createdAt:messages[0]?.createdAt||item.updated*1000,updatedAt:item.updated*1000,pinned:false,
         messages:messages.map((m,i)=>({...m,id:m.id||`restored-${item.id}-${i}`,createdAt:m.createdAt||item.updated*1000,isStreaming:false}))} as Conversation;
      }catch{return null}
    }));if(alive)useApp.getState().importChats(remote.filter((c):c is Conversation=>c!==null));
   }catch{/* No API yet: retain local browser history. */}finally{window.dispatchEvent(new Event('barq:conversations-hydrated'))}})();
 const unsubscribe=useApp.subscribe((state,prev)=>{
   if(state.chats===prev.chats)return;
   for(const chat of state.chats){
     if(!chat.messages.length||chat.messages.some(m=>m.isStreaming))continue;
     if(revision.get(chat.id)===chat.updatedAt)continue;
     const existing=saves.get(chat.id);if(existing)clearTimeout(existing);
     saves.set(chat.id,setTimeout(()=>{saves.delete(chat.id);if(!alive)return;
       const current=useApp.getState().chats.find(c=>c.id===chat.id);
       if(!current||current.messages.some(m=>m.isStreaming))return;
       void saveConversation(current).then(()=>{revision.set(current.id,current.updatedAt)}).catch(()=>{/* local browser copy remains safe */});
     },900));
   }
 });
 void hydration;void refresh();window.addEventListener('barq:providers-updated',refresh);const polling=setInterval(()=>{if(document.visibilityState==='visible')void refresh()},30000);
 return ()=>{alive=false;window.removeEventListener('barq:providers-updated',refresh);clearInterval(polling);unsubscribe();saves.forEach(timer=>clearTimeout(timer))};
}
