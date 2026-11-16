import {useEffect,useRef,useState} from 'react';
import {PanelLeft,SlidersHorizontal,Share2,Ellipsis,Copy,Keyboard,Trash2,Pencil,ScanFace} from 'lucide-react';
import {useApp} from '../../store';import {useT} from '../../i18n';
import {IconButton} from '../ui/IconButton';import {Dropdown} from '../ui/Dropdown';import {ModelSelector} from '../chat/ModelSelector';
import type {RouterProvider} from '../../lib/backend';import {ConnectionStatus} from './ConnectionStatus';
export function TopBar({onShortcuts,onDelete,onModels,onHologram,hologram,providers}:{onShortcuts:()=>void;onDelete:(id:string)=>void;onModels:()=>void;onHologram:()=>void;hologram:boolean;providers:RouterProvider[]}){
 const id=useApp(s=>s.activeId),chat=useApp(s=>s.chats.find(c=>c.id===s.activeId)),setSidebarOpen=useApp(s=>s.setSidebarOpen),setRightOpen=useApp(s=>s.setRightOpen),rightOpen=useApp(s=>s.rightOpen),rename=useApp(s=>s.renameChat),toast=useApp(s=>s.toast),language=useApp(s=>s.language);const t=useT();
 const [editing,setEditing]=useState(false),[title,setTitle]=useState('');const ref=useRef<HTMLInputElement>(null);
 useEffect(()=>setTitle(chat?.title||''),[chat?.title]);useEffect(()=>{if(editing)ref.current?.select()},[editing]);
 function saveTitle(){if(chat)rename(chat.id,title);setEditing(false)}
 async function share(){if(!chat)return;const content=chat.messages.map(m=>`${m.role==='user'?'You':'AI'}: ${m.content}`).join('\n\n');
  try{if(navigator.share)await navigator.share({title:chat.title,text:content});else{await navigator.clipboard.writeText(content);toast('success',t('copied'))}}catch{/* native share canceled */}}
 return <header className="barq-topbar z-10 flex h-[68px] shrink-0 items-center gap-2 border-b border-stroke bg-base/90 px-3 backdrop-blur-md md:px-5">
  <div className="lg:hidden"><IconButton label={language==='ar'?'فتح الشريط الجانبي':'Open sidebar'} icon={<PanelLeft size={20}/>} onClick={()=>setSidebarOpen(true)}/></div>
  <div className="barq-current-chat min-w-0 flex-1">{editing?<input ref={ref} className="ui-input !py-1.5 text-sm" value={title} onChange={e=>setTitle(e.target.value)} onBlur={saveTitle} onKeyDown={e=>{if(e.key==='Enter')saveTitle();if(e.key==='Escape')setEditing(false)}}/>:
   <button onClick={()=>chat&&setEditing(true)} className="focus-ring group flex max-w-full items-center gap-2 rounded-md px-2 py-1.5 text-start text-sm font-semibold"><span className="truncate">{chat?.title||(language==='ar'?'محادثة جديدة':'New chat')}</span>{chat&&<Pencil size={13} className="shrink-0 text-muted opacity-0 group-hover:opacity-100"/>}</button>}
   {chat&&<span className="barq-chat-meta" aria-label={language==='ar'?'عدد الرسائل':'Message count'}>{chat.messages.length} {language==='ar'?'رسالة':'messages'}</span>}
  </div>
  <div className="barq-topbar-model hidden sm:block"><ModelSelector compact/></div>
  <div className="barq-topbar-connection hidden md:block"><ConnectionStatus providers={providers} onModels={onModels}/></div>

  <nav className="barq-header-actions flex shrink-0 items-center gap-1" aria-label={language==='ar'?'أدوات المحادثة':'Chat actions'}>
  <div className="hidden sm:block"><IconButton label={t('share')} icon={<Share2 size={17}/>} disabled={!chat?.messages.length} onClick={share}/></div>
  <IconButton label={t('chatSettings')} icon={<SlidersHorizontal size={18}/>} className={rightOpen?'!bg-accent/15':''} onClick={()=>setRightOpen(!rightOpen)}/>
  <IconButton label={language==='ar'?(hologram?'الرجوع للمحادثة':'هولوجرام برق'):(hologram?'Back to chat':'BARQ hologram')} icon={<ScanFace size={19}/>} onClick={onHologram} aria-pressed={hologram} className={hologram?'!bg-accent/15':''}/>
  <Dropdown trigger={<IconButton label={t('more')} icon={<Ellipsis size={19}/>} />} items={[
    {id:'copy',label:t('share'),icon:<Copy size={16}/>,onClick:share,disabled:!chat?.messages.length},
    {id:'rename',label:t('rename'),icon:<Pencil size={16}/>,onClick:()=>setEditing(true),disabled:!chat},
    {id:'shortcuts',label:t('shortcutsTitle'),icon:<Keyboard size={16}/>,onClick:onShortcuts},
    {id:'delete',label:t('delete'),icon:<Trash2 size={16}/>,danger:true,onClick:()=>{if(id)onDelete(id)},disabled:!chat}
  ]}/>
  </nav>
 </header>
}
