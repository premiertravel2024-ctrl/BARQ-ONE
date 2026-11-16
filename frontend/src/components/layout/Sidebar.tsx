import {AnimatePresence,motion,useReducedMotion} from 'framer-motion';
import {MessageSquarePlus,MessagesSquare,PanelLeftClose,PanelLeftOpen,Search,MoreHorizontal,Pin,PinOff,Trash2,Pencil,Settings2,Sun,Moon,X,FlaskConical,Headphones} from 'lucide-react';
import {useEffect,useMemo,useRef,useState,type TouchEvent} from 'react';
import {useApp,type Conversation} from '../../store';
import {useT} from '../../i18n';
import {Button} from '../ui/Button';import {IconButton} from '../ui/IconButton';import {Dropdown} from '../ui/Dropdown';
import {motionTokens} from '../../lib/motion';
import {BrandLockup} from '../ui/BrandMark';
type Props={onSettings:()=>void;onSearch:()=>void;onDelete:(id:string)=>void;onPlayground:()=>void;onListening:()=>void;onNewChat:()=>void;onSelectChat:()=>void};
function groupChats(chats:Conversation[],lang:'ar'|'en'){
  const now=new Date();now.setHours(0,0,0,0);const day=86400000;
  const items=[{key:'pinned',label:lang==='ar'?'المثبتة':'Pinned',chats:[] as Conversation[]},
    {key:'today',label:lang==='ar'?'اليوم':'Today',chats:[] as Conversation[]},
    {key:'yesterday',label:lang==='ar'?'أمس':'Yesterday',chats:[] as Conversation[]},
    {key:'week',label:lang==='ar'?'آخر ٧ أيام':'Previous 7 days',chats:[] as Conversation[]},
    {key:'older',label:lang==='ar'?'الأقدم':'Older',chats:[] as Conversation[]}];
  chats.sort((a,b)=>b.updatedAt-a.updatedAt).forEach(c=>{const delta=now.getTime()-c.updatedAt;
    const bucket=c.pinned?0:delta<0?1:delta<day?2:delta<day*7?3:4;items[bucket].chats.push(c)});
  return items.filter(g=>g.chats.length);
}
function ChatRow({chat,compact,onDelete,onSelectChat}:{chat:Conversation;compact:boolean;onDelete:(id:string)=>void;onSelectChat:()=>void}){
  const active=useApp(s=>s.activeId===chat.id),select=useApp(s=>s.selectChat),rename=useApp(s=>s.renameChat),pin=useApp(s=>s.pinChat);const t=useT();
  const [editing,setEditing]=useState(false),[value,setValue]=useState(chat.title);const editRef=useRef<HTMLInputElement>(null);
  useEffect(()=>{if(editing)editRef.current?.select()},[editing]);
  function commit(){rename(chat.id,value);setEditing(false)}
  const menu=[{id:'rename',label:t('rename'),icon:<Pencil size={15}/>,onClick:()=>setEditing(true)},
    {id:'pin',label:chat.pinned?t('unpin'):t('pin'),icon:chat.pinned?<PinOff size={15}/>:<Pin size={15}/>,onClick:()=>pin(chat.id)},
    {id:'delete',label:t('delete'),icon:<Trash2 size={15}/>,danger:true,onClick:()=>onDelete(chat.id)}];
  if(compact)return <IconButton label={chat.title} icon={<MessageSquarePlus size={17}/>} onClick={()=>{select(chat.id);onSelectChat()}} className={active?'!bg-accent/20':''}/>;
  return <motion.div layout className={`sidebar-item group flex min-w-0 items-center gap-1 rounded-sm px-1 transition-colors ${active?'bg-accent/10 text-primary':'text-secondary hover:bg-elevated'}`}>
    {editing?<input ref={editRef} value={value} maxLength={100} className="ui-input my-1 !py-1 text-xs" aria-label={t('rename')} onChange={e=>setValue(e.target.value)} onBlur={commit} onKeyDown={e=>{if(e.key==='Enter')commit();if(e.key==='Escape')setEditing(false)}}/>:
    <button aria-current={active?'page':undefined} onClick={()=>{select(chat.id);onSelectChat()}} className="focus-ring flex min-w-0 flex-1 items-center gap-2 rounded-sm px-2 py-2 text-start text-[13px]">
      <MessageSquarePlus size={15} className="shrink-0 opacity-70"/><span className="flex-1 truncate">{chat.title}</span>{chat.pinned&&<Pin size={12} className="shrink-0"/>}
    </button>}
    {!editing&&<span className="sidebar-actions shrink-0"><Dropdown trigger={<IconButton label={t('more')} icon={<MoreHorizontal size={16}/>} size="sm" className="!min-w-8 !min-h-8"/>} items={menu}/></span>}
  </motion.div>
}
export function Sidebar({onSettings,onSearch,onDelete,onPlayground,onListening,onNewChat,onSelectChat}:Props){
 const collapsed=useApp(s=>s.sidebarCollapsed),open=useApp(s=>s.sidebarOpen),setOpen=useApp(s=>s.setSidebarOpen),setCollapsed=useApp(s=>s.setSidebarCollapsed),newChat=useApp(s=>s.newChat);
 const chats=useApp(s=>s.chats),language=useApp(s=>s.language),theme=useApp(s=>s.theme),toggleTheme=useApp(s=>s.toggleTheme);const t=useT();const reduced=useReducedMotion();
 const [loadingHistory,setLoadingHistory]=useState(true);useEffect(()=>{const ready=()=>setLoadingHistory(false);window.addEventListener('barq:conversations-hydrated',ready);const fallback=window.setTimeout(ready,6000);return()=>{window.removeEventListener('barq:conversations-hydrated',ready);window.clearTimeout(fallback)}},[]);
 const [query,setQuery]=useState('');const groups=useMemo(()=>groupChats(chats.filter(c=>c.title.toLowerCase().includes(query.toLowerCase())||c.messages.some(m=>m.content.toLowerCase().includes(query.toLowerCase()))),language),[chats,query,language]);
 const swipe=useRef<number|null>(null);function start(e:TouchEvent){swipe.current=e.touches[0].clientX}function end(e:TouchEvent){if(swipe.current===null)return;const delta=e.changedTouches[0].clientX-swipe.current;if(Math.abs(delta)>90&&(language==='ar'?delta>0:delta<0))setOpen(false);swipe.current=null}
 // Build the mobile drawer in expanded mode even if the desktop rail is collapsed.
 // Brand has a dedicated, non-shrinking header row: it never shares the New Chat button's space.
 const renderBody=(compact:boolean,mobile=false)=><>
  <header data-compact={compact} className={`sidebar-brand-header flex w-full shrink-0 items-center gap-3 ${compact?'justify-center':'justify-between'}`}>
    {!compact&&<div role="img" aria-label="BARQ" className="sidebar-brand-lockup flex min-w-0 items-center justify-start">
      <BrandLockup compact={compact}/>
    </div>}
    {!mobile&&<IconButton label={t('sidebar')} aria-expanded={!compact} icon={compact?<PanelLeftOpen size={18}/>:<PanelLeftClose size={18}/>} onClick={()=>setCollapsed(!collapsed)}/>}
  </header>
  <div className="sidebar-new-chat-row w-full shrink-0 px-3 pb-3">
    {compact?<IconButton label={t('newChat')} variant="primary" icon={<MessageSquarePlus size={19}/>} onClick={()=>{newChat();onNewChat()}} className="w-full"/>:
      <Button variant="primary" magnetic icon={<MessageSquarePlus size={17}/>} onClick={()=>{newChat();onNewChat()}} className="w-full justify-center">{t('newChat')}</Button>}
  </div>
  <nav aria-label={language==='ar'?'مساحات العمل':'Workspaces'} className={`sidebar-workspaces shrink-0 px-3 pb-3 ${compact?'flex flex-col items-center gap-1':'space-y-1'}`}>
    {(['chat'] as const).map(item=>{const label=language==='ar'?'المحادثة':'Chat';const icon=<MessagesSquare size={18}/>;const selected=true;
      const choose=()=>{onSelectChat();if(mobile)setOpen(false)};
      return compact?<IconButton key={item} label={label} icon={icon} aria-current={selected?'page':undefined} className={selected?'!bg-accent/15 !text-accent':''} onClick={choose}/>:
        <button key={item} type="button" aria-current={selected?'page':undefined} onClick={choose} className={`focus-ring flex min-h-11 w-full items-center gap-3 rounded-lg px-3 py-2 text-start text-sm transition-colors ${selected?'bg-accent/10 text-primary':'text-secondary hover:bg-elevated'}`}>{icon}<span>{label}</span></button>;
    })}
  </nav>
  <div className="w-full shrink-0 px-3 pb-3">{compact?<IconButton label="غرفة الاستماع" icon={<Headphones size={18}/>} onClick={onListening}/>:<button onClick={onListening} className="focus-ring flex min-h-11 w-full items-center gap-3 rounded-lg px-3 py-2 text-start text-sm text-secondary hover:bg-elevated"><Headphones size={18}/>غرفة الاستماع</button>}</div>
  {!compact&&<div className="w-full shrink-0 px-3 pb-3"><div className="relative"><Search className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-muted" size={16}/><input aria-label={t('search')} className="ui-input !ps-10 !pe-16 text-sm" placeholder={t('search')} value={query} onChange={e=>setQuery(e.target.value)}/><button onClick={onSearch} className="absolute end-2 top-1/2 -translate-y-1/2 rounded-md border border-stroke px-1.5 text-[10px] text-muted focus-ring" title={language==='ar'?'فتح البحث السريع':'Open command search'}>{language==='ar'?'Ctrl K':'Ctrl K'}</button></div></div>}
 <nav aria-label={language==='ar'?'سجل المحادثات':'Chat history'} className={`min-h-0 flex-1 overflow-y-auto ${compact?'px-2':'px-3'}`}>
  {groups.length?groups.map(g=><section key={g.key} className="mb-4">{!compact&&<h3 className="mb-1.5 px-2 text-[11px] font-semibold uppercase tracking-[.08em] text-muted">{g.label}</h3>}<div className="flex flex-col gap-1"><AnimatePresence initial={false}>{g.chats.map(c=><ChatRow key={c.id} chat={c} compact={compact} onDelete={onDelete} onSelectChat={onSelectChat}/>)}</AnimatePresence></div></section>):loadingHistory&&!compact?<div role="status" aria-label="جاري تحميل المحادثات" className="space-y-3 px-2 py-4"><div className="shimmer h-9 rounded-lg"/><div className="shimmer h-9 rounded-lg"/><div className="shimmer h-9 rounded-lg"/></div>:!compact&&<p className="px-2 py-4 text-sm text-muted">{query?(language==='ar'?'لا توجد نتائج مطابقة':'No matching chats'):(language==='ar'?'ستظهر محادثاتك هنا.':'Your conversations will appear here.')}</p>}
 </nav>
 <div className={`barq-sidebar-footer border-t border-stroke p-3 ${compact?'flex flex-col items-center gap-2':''}`}>
  <div className={`flex items-center gap-1 ${compact?'flex-col':'justify-between'}`}><IconButton label={t('settings')} icon={<Settings2 size={18}/>} onClick={onSettings}/><IconButton label={theme==='dark'?t('light'):t('dark')} icon={theme==='dark'?<Sun size={18}/>:<Moon size={18}/>} onClick={toggleTheme}/><IconButton label={t('playground')} icon={<FlaskConical size={18}/>} onClick={onPlayground}/></div>
 </div></>;
 return <>
  <motion.aside initial={false} animate={{width:collapsed?72:280}} transition={reduced?{duration:.05}:motionTokens.spring.sidebar} className="barq-sidebar hidden lg:flex shrink-0 flex-col overflow-hidden border-e border-stroke bg-surface" aria-label="Sidebar">{renderBody(collapsed)}</motion.aside>
  <AnimatePresence>{open&&<div className="fixed inset-0 z-50 lg:hidden"><motion.div className="absolute inset-0 bg-black/50" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} onClick={()=>setOpen(false)} aria-hidden/><motion.aside initial={{x:language==='ar'?'100%':'-100%'}} animate={{x:0}} exit={{x:language==='ar'?'100%':'-100%'}} transition={motionTokens.spring.sidebar} onTouchStart={start} onTouchEnd={end} className={`barq-sidebar absolute inset-y-0 ${language==='ar'?'right-0':'left-0'} flex w-[min(320px,90vw)] flex-col bg-surface shadow-float`} aria-label="Mobile sidebar"><div className="absolute end-2 top-2 z-10"><IconButton label={t('close')} icon={<X size={18}/>} onClick={()=>setOpen(false)}/></div>{renderBody(false,true)}</motion.aside></div>}</AnimatePresence>
 </>
}
