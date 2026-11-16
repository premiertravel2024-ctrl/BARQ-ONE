import {useEffect,useRef,useState} from 'react';
import {Virtuoso,type VirtuosoHandle} from 'react-virtuoso';
import {ArrowDown} from 'lucide-react';
import {useApp} from '../../store';import {MemoizedMessage} from './Message';import {IconButton} from '../ui/IconButton';
const EMPTY_MESSAGES:ReturnType<typeof useApp.getState>['chats'][number]['messages']=[];
export function MessageList({id}:{id:string}){
 const messages=useApp(s=>s.chats.find(c=>c.id===id)?.messages||EMPTY_MESSAGES);
 const list=useRef<HTMLDivElement>(null),virt=useRef<VirtuosoHandle>(null);const [atBottom,setAtBottom]=useState(true);
 useEffect(()=>{if(!atBottom)return;const frame=requestAnimationFrame(()=>{if(messages.length>100)virt.current?.scrollToIndex({index:messages.length-1,align:'end',behavior:'auto'});else if(list.current)list.current.scrollTop=list.current.scrollHeight});return()=>cancelAnimationFrame(frame)},[messages,atBottom]);
 function scrollBottom(){if(messages.length>100)virt.current?.scrollToIndex({index:messages.length-1,align:'end',behavior:'smooth'});else list.current?.scrollTo({top:list.current.scrollHeight,behavior:'smooth'});setAtBottom(true)}
 return <div className="relative min-h-0 flex-1">
  {messages.length>100?<Virtuoso ref={virt} className="h-full" data={messages} computeItemKey={(_,m)=>m.id} followOutput={atBottom} atBottomStateChange={setAtBottom} itemContent={(_,m)=><MemoizedMessage key={m.id} message={m} chatId={id}/>} />:
   <div ref={list} role="log" aria-live="polite" aria-relevant="additions" className="h-full overflow-y-auto overscroll-contain" onScroll={e=>{const el=e.currentTarget;setAtBottom(el.scrollHeight-el.scrollTop-el.clientHeight<110)}}>
    {messages.map(m=><MemoizedMessage key={m.id} message={m} chatId={id}/>)}<div className="h-5"/>
   </div>}
  {!atBottom&&<div className="absolute bottom-4 left-1/2 -translate-x-1/2"><IconButton label={useApp.getState().language==='ar'?'الانتقال لآخر رسالة':'Scroll to latest message'} variant="secondary" icon={<ArrowDown size={18}/>} className="!rounded-full shadow-float" onClick={scrollBottom}/></div>}
 </div>
}
