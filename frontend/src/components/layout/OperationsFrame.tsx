import {useEffect,useRef,useState} from 'react';
import {AudioLines,Ellipsis,Menu,Copy,PanelLeftClose,PanelLeftOpen,Pencil,Plus,Search,Settings2,Trash2,X} from 'lucide-react';
import {useApp} from '../../store';
import {sections,type OnePage} from '../../pages/BarqOne';
import {ModelSelector} from '../chat/ModelSelector';
import {Dropdown} from '../ui/Dropdown';
import {IconButton} from '../ui/IconButton';
import {AppUpdates} from './AppUpdates';
import {DayStatus} from './DayStatus';
import './operationsFrame.css';

type Actions={page:OnePage;navigate:(page:OnePage)=>void;search:()=>void};
export function OperationsHeader({page,navigate,search}:Actions){
 const ar=useApp(s=>s.language)==='ar',setOpen=useApp(s=>s.setSidebarOpen),toast=useApp(s=>s.toast);
 const open=useApp(s=>s.sidebarOpen);
 const section=sections.find(([key])=>key===page);

 return <header className="ops-header" data-focus-region tabIndex={-1}>
  <div className="ops-brand">
   <button className="ops-mobile-menu" type="button" aria-label={ar?'القائمة':'Menu'} aria-controls="barq-sidebar" aria-expanded={open} onClick={()=>setOpen(true)}><Menu size={19}/></button>
   <button className="ops-wordmark" type="button" onClick={()=>navigate('center')}><span className="ops-mark"><AudioLines size={17}/></span><span>BARQ <b>ONE</b></span></button>
  </div>
  <p className="ops-current-section">{section?.[ar?1:2]}</p>
  <div className="ops-header-actions">
   <DayStatus ar={ar} onOpen={()=>navigate('automation')} onFocusDone={()=>toast('success',ar?'انتهى وقت التركيز':'Focus session finished')}/>
   <AppUpdates ar={ar}/>
   <button className="ops-search" type="button" onClick={search} aria-label={ar?'البحث':'Search'}><Search size={14}/><span>{ar?'بحث سريع':'Quick search'}</span><kbd dir="ltr">Ctrl K</kbd></button>
  </div>
 </header>;
}

const navigationGroups = [
 {ar:'برق',en:'BARQ',pages:['center','chat','voice','mission']},
 {ar:'المكتبة والوسائط',en:'Library and media',pages:['stories','watch','music','wallpapers']},
 {ar:'النظام والأدوات',en:'System and tools',pages:['library','installed','tools','monitor','resources','automation','settings']},
] as const satisfies ReadonlyArray<{ar:string;en:string;pages:readonly OnePage[]}>;

export function OperationsRail({page,navigate,newChat,search}:Pick<Actions,'page'|'navigate'|'search'>&{newChat:()=>void}){
 const ar=useApp(s=>s.language)==='ar',open=useApp(s=>s.sidebarOpen),setOpen=useApp(s=>s.setSidebarOpen);
 const collapsed=useApp(s=>s.sidebarCollapsed),setCollapsed=useApp(s=>s.setSidebarCollapsed);
 const chats=useApp(s=>s.chats),activeId=useApp(s=>s.activeId),selectChat=useApp(s=>s.selectChat);
 const closeButton=useRef<HTMLButtonElement>(null);
 const rail=useRef<HTMLElement>(null);
 const [narrow,setNarrow]=useState(()=>window.matchMedia('(max-width: 730px)').matches);
 const drawer=open&&narrow;
 const history=page==='chat'?[...chats].filter(chat=>chat.messages.length||chat.id===activeId)
  .sort((a,b)=>Number(b.pinned)-Number(a.pinned)||b.updatedAt-a.updatedAt):[];
 const recent=history.slice(0,8);
 const current=history.find(chat=>chat.id===activeId);
 if(current&&!recent.includes(current))recent[recent.length-1]=current;

 useEffect(()=>{
  const query=window.matchMedia('(max-width: 730px)');
  const update=()=>setNarrow(query.matches);
  query.addEventListener('change',update);
  return()=>query.removeEventListener('change',update);
 },[]);
 useEffect(()=>{
  if(!drawer)return;
  const opener=document.activeElement as HTMLElement|null;
  closeButton.current?.focus();
  return()=>{if(opener?.isConnected)opener.focus()};
 },[drawer]);

 function choose(target:OnePage){navigate(target);setOpen(false);}

 return <>
  {drawer&&<button type="button" tabIndex={-1} className="ops-drawer-backdrop" aria-label={ar?'إغلاق':'Close'} onClick={()=>setOpen(false)}/>}
  <aside ref={rail} id="barq-sidebar" className="ops-rail" data-open={drawer} data-collapsed={collapsed}
   role={drawer?'dialog':undefined} aria-modal={drawer||undefined} data-focus-region tabIndex={-1}
   dir={ar?'rtl':'ltr'} aria-label={ar?'الشريط الجانبي':'Sidebar'}
   onKeyDown={event=>{
    if(!drawer||event.key!=='Tab')return;
    const items=Array.from(rail.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')??[])
     .filter(button=>button.tabIndex>=0&&button.getClientRects().length);
    const first=items[0],last=items.at(-1);
    if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus()}
    if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus()}
   }}>
   <div className="ops-rail-heading">
    <span>{ar?'الأقسام':'Sections'}</span>
    <button className="ops-rail-collapse" type="button" title={ar?(collapsed?'توسيع الشريط':'طي الشريط'):(collapsed?'Expand sidebar':'Collapse sidebar')}
     aria-label={ar?(collapsed?'توسيع الشريط':'طي الشريط'):(collapsed?'Expand sidebar':'Collapse sidebar')} aria-expanded={!collapsed} onClick={()=>setCollapsed(!collapsed)}>
     {collapsed?<PanelLeftOpen size={15}/>:<PanelLeftClose size={15}/>}
    </button>
    <button ref={closeButton} className="ops-rail-close" type="button" aria-label={ar?'إغلاق':'Close'} onClick={()=>setOpen(false)}><X size={17}/></button>
   </div>
   <nav aria-label={ar?'أقسام التطبيق':'Application sections'}>
    {navigationGroups.map(group=><div className="ops-rail-group" role="group" aria-label={ar?group.ar:group.en} key={group.en}>
     <span className="ops-rail-group-title" aria-hidden="true">{ar?group.ar:group.en}</span>
     {group.pages.map(key=>{
      const [,label,english,Icon]=sections.find(section=>section[0]===key)!;
      return <button key={key} data-section={key} type="button" title={ar?label:english} aria-current={page===key?'page':undefined}
       aria-label={ar?label:english} onClick={()=>choose(key)}><i><Icon size={16}/></i><span>{ar?label:english}</span></button>;
     })}
     {group.en==='BARQ'&&page==='chat'&&<section className="ops-chat-history" aria-label={ar?'المحادثات الأخيرة':'Recent conversations'}>
      <button type="button" className="ops-new-chat" onClick={()=>{newChat();setOpen(false)}}><Plus size={16}/>{ar?'محادثة جديدة':'New chat'}</button>
      {recent.length>0&&<p>{ar?'المحادثات الأخيرة':'Recent conversations'}</p>}
      {recent.map(chat=><button type="button" className="ops-history-item" key={chat.id} dir="auto" title={chat.title}
       aria-current={chat.id===activeId?'true':undefined} onClick={()=>{selectChat(chat.id);setOpen(false)}}>{chat.title}</button>)}
      {history.length>recent.length&&<button type="button" className="ops-history-more" onClick={()=>{setOpen(false);search()}}>{ar?'البحث في كل المحادثات':'Search all conversations'}</button>}
     </section>}
    </div>)}
   </nav>
  </aside>
 </>;
}

export function ConversationHeader({onDelete,onVoice,onNew}:{onDelete:()=>void;onVoice:()=>void;onNew:()=>void}){
 const ar=useApp(s=>s.language)==='ar';
 const chat=useApp(s=>s.chats.find(c=>c.id===s.activeId));
 const rename=useApp(s=>s.renameChat),setRightOpen=useApp(s=>s.setRightOpen),toast=useApp(s=>s.toast);
 const [name,setName]=useState<string>();
 function save(){if(chat&&name?.trim())rename(chat.id,name.trim());setName(undefined);}
 async function share(){
  if(!chat?.messages.length)return;
  const value=chat.messages.map(m=>m.role+': '+m.content).join('\n\n');
  try{await navigator.clipboard.writeText(value);toast('success',ar?'اتنسخت المحادثة':'Conversation copied');}
  catch{toast('error',ar?'تعذّر نسخ المحادثة':'Could not copy conversation');}
 }
 return <div className="ops-conversation-head">
  {name===undefined?<h1 dir="auto">{chat?.title||(ar?'المحادثة':'Conversation')}</h1>:
   <input autoFocus className="ui-input" value={name} aria-label={ar?'اسم المحادثة':'Conversation name'} onChange={e=>setName(e.target.value)} onBlur={save}
    onKeyDown={e=>{if(e.key==='Enter')save();if(e.key==='Escape')setName(undefined)}}/>}
  <div className="barq-conversation-actions">
   <ModelSelector compact/>
   <button type="button" className="barq-new-conversation" onClick={onNew} aria-label={ar?'محادثة جديدة':'New chat'}>
    <Plus size={16}/><span>{ar?'محادثة جديدة':'New chat'}</span>
   </button>
   <Dropdown trigger={<IconButton label={ar?'خيارات المحادثة':'Conversation options'} icon={<Ellipsis size={17}/>}/>} items={[
    {id:'voice',label:ar?'المساعد الصوتي':'Voice assistant',icon:<AudioLines size={15}/>,onClick:onVoice},
    {id:'rename',label:ar?'تعديل الاسم':'Rename',icon:<Pencil size={15}/>,disabled:!chat,onClick:()=>setName(chat?.title)},
    {id:'copy',label:ar?'نسخ المحادثة':'Copy conversation',icon:<Copy size={15}/>,disabled:!chat?.messages.length,onClick:()=>void share()},
    {id:'options',label:ar?'خيارات النموذج':'Model options',icon:<Settings2 size={15}/>,onClick:()=>setRightOpen(true)},
    {id:'delete',label:ar?'حذف المحادثة':'Delete conversation',icon:<Trash2 size={15}/>,danger:true,disabled:!chat,onClick:onDelete},
   ]}/>
  </div>
 </div>;
}
