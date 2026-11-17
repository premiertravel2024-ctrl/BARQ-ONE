import {useState} from 'react';
import {AudioLines,Ellipsis,Menu,Copy,PanelLeftClose,PanelLeftOpen,Pencil,Plus,Search,Settings2,Trash2,X} from 'lucide-react';
import {useApp} from '../../store';
import {sections,type OnePage} from '../../pages/BarqOne';
import {ModelSelector} from '../chat/ModelSelector';
import {Dropdown} from '../ui/Dropdown';
import {IconButton} from '../ui/IconButton';
import {AppUpdates} from './AppUpdates';
import './operationsFrame.css';

type Actions={page:OnePage;navigate:(page:OnePage)=>void;search:()=>void;settings:()=>void};
export function OperationsHeader({page,navigate,search,settings}:Actions){
 const ar=useApp(s=>s.language)==='ar',setOpen=useApp(s=>s.setSidebarOpen);
 return <header className="ops-header">
  <div className="ops-brand">
   <button className="ops-mobile-menu" type="button" aria-label={ar?'القائمة':'Menu'} onClick={()=>setOpen(true)}><Menu size={19}/></button>
   <button className="ops-wordmark" type="button" onClick={()=>navigate('center')}><span className="ops-mark"><AudioLines size={17}/></span><span>BARQ <b>ONE</b></span></button>
  </div>
  <nav aria-label={ar?'التنقل الرئيسي':'Main navigation'}>
   {(['center','chat','library','tools','monitor'] as const).map(key=>{
    const item=sections.find(section=>section[0]===key)!;
    return <button key={key} className={key==='chat'?'ops-mobile-chat':undefined} type="button" onClick={()=>navigate(key)} aria-current={page===key?'page':undefined}>{item[ar?1:2]}</button>;
   })}
  </nav>
  <div className="ops-header-actions">
   <AppUpdates ar={ar}/>
   <button className="ops-search" type="button" onClick={search} aria-label={ar?'البحث':'Search'}><Search size={14}/><span>{ar?'بحث سريع':'Quick search'}</span><kbd dir="ltr">Ctrl K</kbd></button>
   <button type="button" onClick={settings} aria-label={ar?'الإعدادات':'Settings'}><Settings2 size={16}/></button>
  </div>
 </header>;
}

export function OperationsRail({page,navigate}:Pick<Actions,'page'|'navigate'>&{newChat:()=>void;onDelete:(id:string)=>void;onPlayground:()=>void}){
 const ar=useApp(s=>s.language)==='ar',open=useApp(s=>s.sidebarOpen),setOpen=useApp(s=>s.setSidebarOpen);
 const collapsed=useApp(s=>s.sidebarCollapsed),setCollapsed=useApp(s=>s.setSidebarCollapsed);
 function choose(target:OnePage){navigate(target);setOpen(false);}
 return <>
  {open&&<button type="button" className="ops-drawer-backdrop" aria-label={ar?'إغلاق':'Close'} onClick={()=>setOpen(false)}/>}
  <aside className="ops-rail" data-open={open} data-collapsed={collapsed} aria-label={ar?'الشريط الجانبي':'Sidebar'}>
   <div className="ops-rail-heading">
    <span>{ar?'التطبيق':'Application'}</span>
    <button className="ops-rail-collapse" type="button" title={ar?'طي الشريط الجانبي':'Collapse sidebar'} aria-label={ar?'طي الشريط الجانبي':'Collapse sidebar'} aria-expanded={!collapsed} onClick={()=>setCollapsed(!collapsed)}>{collapsed?<PanelLeftOpen size={15}/>:<PanelLeftClose size={15}/>}</button>
    <button className="ops-rail-close" type="button" aria-label={ar?'إغلاق':'Close'} onClick={()=>setOpen(false)}><X size={17}/></button>
   </div>
   <nav aria-label={ar?'أقسام التطبيق':'Application sections'}>
    {sections.filter(([key])=>key!=='chat').map(([key,label,english,Icon])=><button key={key} data-section={key} type="button" title={ar?label:english} aria-current={page===key?'page':undefined} aria-label={ar?label:english} onClick={()=>choose(key)}><i><Icon size={15}/></i><span>{ar?label:english}</span></button>)}
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
  <div>
   <ModelSelector compact/>
   <Dropdown trigger={<IconButton label={ar?'خيارات المحادثة':'Conversation options'} icon={<Ellipsis size={17}/>}/>} items={[
    {id:'new',label:ar?'محادثة جديدة':'New chat',icon:<Plus size={15}/>,onClick:onNew},
    {id:'voice',label:ar?'المساعد الصوتي':'Voice assistant',icon:<AudioLines size={15}/>,onClick:onVoice},
    {id:'rename',label:ar?'تعديل الاسم':'Rename',icon:<Pencil size={15}/>,disabled:!chat,onClick:()=>setName(chat?.title)},
    {id:'copy',label:ar?'نسخ المحادثة':'Copy conversation',icon:<Copy size={15}/>,disabled:!chat?.messages.length,onClick:()=>void share()},
    {id:'options',label:ar?'خيارات النموذج':'Model options',icon:<Settings2 size={15}/>,onClick:()=>setRightOpen(true)},
    {id:'delete',label:ar?'حذف المحادثة':'Delete conversation',icon:<Trash2 size={15}/>,danger:true,disabled:!chat,onClick:onDelete},
   ]}/>
  </div>
 </div>;
}
