import {useEffect,useId,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {Check,ChevronDown,Cloud,HardDrive,Search,Sparkles} from 'lucide-react';
import {useApp,type Model} from '../../store';
import {useT} from '../../i18n';
import {Button} from '../ui/Button';

function ModelIcon({model}:{model:Model}){
 return model.id==='auto'?<Sparkles size={17}/>:model.local?<HardDrive size={17}/>:<Cloud size={17}/>;
}
export function ModelSelector({compact=false}:{compact?:boolean}){
 const available=useApp(s=>s.availableModels),selected=useApp(s=>s.selectedModel),setModel=useApp(s=>s.setModel),onlyLocal=useApp(s=>s.options.localOnly),language=useApp(s=>s.language),toast=useApp(s=>s.toast);
 const t=useT();const [open,setOpen]=useState(false),[query,setQuery]=useState(''),[active,setActive]=useState(0);
 const menuId=useId();const root=useRef<HTMLDivElement>(null),menu=useRef<HTMLDivElement>(null),search=useRef<HTMLInputElement>(null);
 const [position,setPosition]=useState({top:0,left:0,width:350,maxHeight:380});
 const current=available.find(m=>m.id===selected)||available[0];
 const items=useMemo(()=>available.filter(m=>(m.id==='auto'||!onlyLocal||m.local)&&(m.id==='auto'||`${m.name} ${m.provider}`.toLowerCase().includes(query.toLowerCase()))),[available,onlyLocal,query]);
 const groups=useMemo(()=>{const providers=new Map<string,Model[]>();items.forEach(m=>{const key=m.id==='auto'?'Auto':m.provider;providers.set(key,[...(providers.get(key)||[]),m])});return Array.from(providers.entries())},[items]);
 const choose=(m:Model)=>{if(m.id!=='auto'&&m.available===false){toast('info',language==='ar'?'النموذج غير جاهز':'Model unavailable',m.unavailableReason||(language==='ar'?'افتح إعدادات النماذج وأضف المفتاح أو شغّل Ollama.':'Configure the provider or start Ollama in Settings.'));return}setModel(m.id);setOpen(false);setQuery('');root.current?.querySelector<HTMLButtonElement>('button')?.focus()};
 useEffect(()=>{if(!open)return;const onOutside=(event:PointerEvent)=>{
  const target=event.target as Node;
  if(!root.current?.contains(target)&&!menu.current?.contains(target))setOpen(false);
 };document.addEventListener('pointerdown',onOutside);return()=>document.removeEventListener('pointerdown',onOutside)},[open]);
 // Portals escape the composer's overflow:hidden; place the menu above bottom composers.
 useLayoutEffect(()=>{if(!open)return;const update=()=>{
  const anchor=root.current?.getBoundingClientRect(),pop=menu.current;
  if(!anchor||!pop)return;
  const vw=document.documentElement.clientWidth, vh=window.visualViewport?.height||window.innerHeight;
  const width=Math.min(350,vw-24),gap=8;
  const maxHeight=Math.min(410,vh-24),height=Math.min(pop.scrollHeight,maxHeight);
  const left=Math.min(vw-width-12,Math.max(12,anchor.right-width));
  const above=anchor.top-height-gap>=12;
  const top=above?anchor.top-height-gap:Math.min(vh-height-12,anchor.bottom+gap);
  setPosition(prev=>prev.top===top&&prev.left===left&&prev.width===width&&prev.maxHeight===maxHeight?prev:{top,left,width,maxHeight});
 };update();window.addEventListener('resize',update);window.addEventListener('scroll',update,true);window.visualViewport?.addEventListener('resize',update);
 return()=>{window.removeEventListener('resize',update);window.removeEventListener('scroll',update,true);window.visualViewport?.removeEventListener('resize',update)};
 },[open,query,items.length]);
 useEffect(()=>{if(open){setActive(0);const frame=requestAnimationFrame(()=>search.current?.focus());return()=>cancelAnimationFrame(frame)}},[open]);
 const nav=(event:React.KeyboardEvent)=>{if(event.key==='Escape'){event.preventDefault();setOpen(false);root.current?.querySelector<HTMLButtonElement>('button')?.focus()}
  if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();setActive(v=>(v+(event.key==='ArrowDown'?1:items.length-1))%Math.max(1,items.length))}
  if(event.key==='Enter'&&open&&items[active]){event.preventDefault();choose(items[active])}};
 return <div ref={root} className="relative inline-flex max-w-full" onKeyDown={nav}>
  <Button variant="secondary" size="sm" aria-haspopup="listbox" aria-expanded={open} aria-controls={open?menuId:undefined} aria-label={t('modelSelect')} icon={<ModelIcon model={current}/>} trailingIcon={<ChevronDown size={14} className={open?'rotate-180 transition-transform':'transition-transform'}/>} className="!rounded-full max-w-[220px] !border-stroke" onClick={()=>setOpen(v=>!v)}>
    <span className="block max-w-[140px] truncate">{current.id==='auto'?(language==='ar'?'تلقائي':'Auto'):compact?current.name:current.name}</span>
  </Button>
  {open&&createPortal(<div ref={menu} id={menuId} style={{position:'fixed',top:position.top,left:position.left,width:position.width,maxHeight:position.maxHeight}} className="model-menu z-[10000] flex flex-col overflow-hidden rounded-xl border border-stroke bg-surface p-2 shadow-float" role="listbox" aria-label={t('modelSelect')}>
    <div className="relative mb-2"><Search size={16} className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-muted"/><input ref={search} className="ui-input !ps-10 text-sm" value={query} onChange={e=>{setQuery(e.target.value);setActive(0)}} placeholder={language==='ar'?'ابحث عن نموذج أو مزود':'Search models or providers'} aria-activedescendant={items[active]?`${menuId}-${active}`:undefined} aria-label={t('modelSelect')}/></div>
    <div className="min-h-0 flex-1 overflow-y-auto" role="presentation">{groups.map(([provider,models])=><section key={provider} aria-label={provider} className="mb-2"><p className="px-3 py-1 text-[11px] font-semibold text-muted" dir="auto">{provider==='Auto'?(language==='ar'?'اختيار تلقائي':'Automatic'):provider}</p>{models.map(m=><button type="button" id={`${menuId}-${items.findIndex(x=>x.id===m.id)}`} key={m.id} title={m.unavailableReason} role="option" aria-selected={selected===m.id} aria-disabled={m.id!=='auto'&&!m.available} onMouseEnter={()=>setActive(items.findIndex(x=>x.id===m.id))} onClick={()=>choose(m)} className={`model-option flex w-full items-center gap-3 rounded-lg px-3 py-2 text-start focus-ring ${selected===m.id||items[active]?.id===m.id?'bg-elevated':''} ${m.id!=='auto'&&!m.available?'opacity-60':''}`}>
      <span className="text-secondary"><ModelIcon model={m}/></span><span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium" dir="auto">{m.id==='auto'?(language==='ar'?'تلقائي · Ollama أولًا للبرمجة':'Auto · local-first for coding'):m.name}</span><span className="block truncate text-xs text-muted">{m.id==='auto'?(language==='ar'?'اختيار حسب المهمة والحالة والسرعة':'By task, health and speed'):`${m.speed} · ${m.quality}${!m.available?(` · ${m.unavailableReason||(language==='ar'?'يحتاج إعداد':'Configure')}`):''}`}</span></span>{selected===m.id&&<Check size={16} className="text-success"/>}
     </button>)}</section>)}{!items.length&&<p className="px-3 py-5 text-center text-sm text-secondary">{language==='ar'?'لا توجد نتائج':'No matching models'}</p>}</div>
    <p className="border-t border-stroke px-2 pt-2 text-xs text-secondary">{language==='ar'?'النماذج غير الجاهزة تظهر لتسهيل إعدادها من الإعدادات.':'Unavailable models stay visible for configuration.'}</p>
   </div>,document.body)}
 </div>
}
export function ModelOverview(){const current=useApp(s=>s.selectedModel),setModel=useApp(s=>s.setModel),available=useApp(s=>s.availableModels),language=useApp(s=>s.language);return <div className="grid gap-2 sm:grid-cols-2">{available.map(m=><button key={m.id} disabled={m.id!=='auto'&&!m.available} className={`flex items-center gap-3 rounded-xl border p-3 text-start transition-colors hover:bg-elevated focus-ring disabled:opacity-50 ${current===m.id?'border-[var(--accent-2)]':'border-stroke'}`} onClick={()=>setModel(m.id)}><ModelIcon model={m}/><span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold" dir="auto">{m.id==='auto'?(language==='ar'?'تلقائي · الأفضل مجانًا':'Auto · best free model'):m.name}</span><span className="text-xs text-secondary">{m.provider} · {m.speed} · {m.available===false?(language==='ar'?'يحتاج إعداد':'Not ready'):m.quality}</span></span>{current===m.id&&<Check size={16} className="text-success"/>}</button>)}</div>}
