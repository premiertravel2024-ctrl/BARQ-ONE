import {useEffect,useId,useRef,useState,type ReactNode} from 'react';
import {MessageSquarePlus,Sun,Moon,PanelLeft,Keyboard,FlaskConical,Search,MessageCircle} from 'lucide-react';
import {useApp} from '../../store';
import {Modal} from './Modal';
import {useT} from '../../i18n';
import {sections,type OnePage} from '../../pages/BarqOne';

type Command={id:string;name:string;icon:ReactNode;run:()=>void};
type Props={
 open:boolean;
 onClose:()=>void;
 onNavigate:(page:OnePage)=>void;
 onSettings:()=>void;
 onShortcuts:()=>void;
 onPlayground:()=>void;
};

function searchKey(value:string){
 return value.toLowerCase().replace(/[\u064b-\u065f\u0670\u0640]/g,'').replace(/[أإآ]/g,'ا').replace(/ى/g,'ي').trim();
}

export function CommandPalette({open,onClose,onNavigate,onSettings,onShortcuts,onPlayground}:Props){
 const [query,setQuery]=useState('');
 const [active,setActive]=useState(0);
 const input=useRef<HTMLInputElement>(null);
 const optionsId=useId();
 const t=useT();
 const language=useApp(s=>s.language);
 const chats=useApp(s=>s.chats);
 const newChat=useApp(s=>s.newChat);
 const select=useApp(s=>s.selectChat);
 const theme=useApp(s=>s.theme);
 const toggle=useApp(s=>s.toggleTheme);
 const collapsed=useApp(s=>s.sidebarCollapsed);
 const setCollapsed=useApp(s=>s.setSidebarCollapsed);

 useEffect(()=>{
  if(open){setQuery('');setActive(0)}
 },[open]);

 const commands:Command[]=[
  {id:'new',name:t('newChat'),icon:<MessageSquarePlus size={17}/>,run:()=>{newChat();onNavigate('chat')}},
  ...sections.map(([page,ar,en,Icon])=>({
   id:'page-'+page,name:language==='ar'?ar:en,icon:<Icon size={17}/>,
   run:page==='settings'?onSettings:()=>onNavigate(page),
  })),
  {id:'theme',name:theme==='dark'?t('light'):t('dark'),icon:theme==='dark'?<Sun size={17}/>:<Moon size={17}/>,run:toggle},
  {id:'sidebar',name:t('sidebar'),icon:<PanelLeft size={17}/>,run:()=>setCollapsed(!collapsed)},
  {id:'shortcuts',name:t('shortcutsTitle'),icon:<Keyboard size={17}/>,run:onShortcuts},
  {id:'playground',name:t('playground'),icon:<FlaskConical size={17}/>,run:onPlayground},
  ...chats.map(c=>({id:'chat-'+c.id,name:c.title,icon:<MessageCircle size={17}/>,run:()=>{select(c.id);onNavigate('chat')}})),
 ];
 const terms=searchKey(query).split(/\s+/).filter(Boolean);
 const visible=commands.filter(command=>terms.every(term=>searchKey(command.name).includes(term)));
 const activeIndex=Math.min(active,visible.length-1);
 const activeCommand=visible[activeIndex];
 const optionId=(command:Command)=>optionsId+'-'+command.id;
 const execute=(command:Command)=>{onClose();command.run()};

 return <Modal open={open} onClose={onClose} title={t('searchCommands')} initialFocus={input}>
  <div className="relative mb-3">
   <Search aria-hidden="true" size={17} className="absolute start-3 top-1/2 -translate-y-1/2 text-muted"/>
   <input ref={input} className="ui-input ps-10" role="combobox" aria-autocomplete="list"
    aria-expanded={visible.length>0} aria-controls={optionsId} aria-activedescendant={activeCommand?optionId(activeCommand):undefined}
    aria-label={t('searchCommands')} placeholder={t('searchCommands')} value={query}
    onChange={event=>{setQuery(event.target.value);setActive(0)}}
    onKeyDown={event=>{
     if(!activeCommand||event.nativeEvent.isComposing)return;
     if(event.key==='Enter'){event.preventDefault();execute(activeCommand)}
     if(event.key==='ArrowDown'||event.key==='ArrowUp'){
      event.preventDefault();
      const next=(activeIndex+(event.key==='ArrowDown'?1:-1)+visible.length)%visible.length;
      setActive(next);
      document.getElementById(optionId(visible[next]))?.scrollIntoView({block:'nearest'});
     }
    }}/>
  </div>
  <div id={optionsId} role="listbox" aria-label={t('searchCommands')} className="max-h-80 overflow-y-auto">
   {visible.map((command,index)=><button type="button" role="option" tabIndex={-1} aria-selected={index===activeIndex}
    id={optionId(command)} key={command.id} onMouseDown={event=>event.preventDefault()} onClick={()=>execute(command)}
    className="flex w-full items-center gap-3 rounded-sm px-3 py-3 text-start text-sm text-secondary hover:bg-elevated aria-selected:bg-elevated aria-selected:text-primary">
    <span className="text-accent">{command.icon}</span><span className="flex-1 truncate">{command.name}</span>
   </button>)}
  </div>
  {!visible.length&&<p role="status" className="p-4 text-center text-sm text-muted">{language==='ar'?'مفيش نتائج':'No results'}</p>}
 </Modal>
}
