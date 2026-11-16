import {useEffect,useRef,useState} from 'react';
import {Command,MessageSquarePlus,Settings2,Sun,Moon,PanelLeft,Keyboard,FlaskConical,Search,MessageCircle} from 'lucide-react';
import {useApp} from '../../store';import {Modal} from './Modal';
import {useT} from '../../i18n';
export function CommandPalette({open,onClose,onSettings,onShortcuts,onPlayground}:{open:boolean;onClose:()=>void;onSettings:()=>void;onShortcuts:()=>void;onPlayground:()=>void}){
 const [query,setQuery]=useState(''),input=useRef<HTMLInputElement>(null),t=useT();const chats=useApp(s=>s.chats),newChat=useApp(s=>s.newChat),select=useApp(s=>s.selectChat),theme=useApp(s=>s.theme),toggle=useApp(s=>s.toggleTheme),collapsed=useApp(s=>s.sidebarCollapsed),setCollapsed=useApp(s=>s.setSidebarCollapsed);
 useEffect(()=>{if(open){setQuery('');setTimeout(()=>input.current?.focus(),20)}},[open]);
 const commands=[{id:'new',name:t('newChat'),icon:<MessageSquarePlus size={17}/>,run:newChat},
   {id:'settings',name:t('settings'),icon:<Settings2 size={17}/>,run:onSettings},
   {id:'theme',name:theme==='dark'?t('light'):t('dark'),icon:theme==='dark'?<Sun size={17}/>:<Moon size={17}/>,run:toggle},
   {id:'sidebar',name:t('sidebar'),icon:<PanelLeft size={17}/>,run:()=>setCollapsed(!collapsed)},
   {id:'shortcuts',name:t('shortcutsTitle'),icon:<Keyboard size={17}/>,run:onShortcuts},
   {id:'playground',name:t('playground'),icon:<FlaskConical size={17}/>,run:onPlayground},
   ...chats.map(c=>({id:c.id,name:c.title,icon:<MessageCircle size={17}/>,run:()=>select(c.id)}))]
  .filter(c=>c.name.toLowerCase().includes(query.toLowerCase())).slice(0,18);
 return <Modal open={open} onClose={onClose} title={t('searchCommands')}><div className="-mt-2"><div className="relative mb-3"><Search size={17} className="absolute start-3 top-1/2 -translate-y-1/2 text-muted"/><input ref={input} className="ui-input ps-10" value={query} onChange={e=>setQuery(e.target.value)} placeholder={t('searchCommands')} onKeyDown={e=>{if(e.key==='Enter'&&commands[0]){onClose();commands[0].run()}}}/></div>
   <div role="listbox" aria-label="Commands" className="max-h-80 overflow-y-auto">{commands.map(c=><button role="option" aria-selected={false} key={c.id} className="focus-ring flex w-full items-center gap-3 rounded-sm px-3 py-3 text-start text-sm text-secondary hover:bg-elevated hover:text-primary focus-visible:bg-elevated" onClick={()=>{onClose();c.run()}}><span className="text-accent">{c.icon}</span><span className="flex-1 truncate">{c.name}</span><Command size={14} className="opacity-20"/></button>)}{!commands.length&&<p className="p-4 text-center text-sm text-muted">No results</p>}</div>
  </div></Modal>
}
