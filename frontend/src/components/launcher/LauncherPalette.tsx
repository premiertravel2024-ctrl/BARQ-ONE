import {useEffect,useRef,useState} from 'react';
import {FolderOpen,FileText,AppWindow,Globe,Search,RefreshCw, X} from 'lucide-react';
import {confirmLaunch,resolveLaunch,type LaunchCandidate} from '../../lib/launcher';
import {requestJSON} from '../../lib/backend';
import {useApp} from '../../store';

const icons={app:AppWindow,file:FileText,folder:FolderOpen,site:Globe};
export function LauncherPalette({open,onClose,initial=''}:{open:boolean;onClose:()=>void;initial?:string}){
 const [query,setQuery]=useState(''),[items,setItems]=useState<LaunchCandidate[]>([]),[busy,setBusy]=useState(false),[selected,setSelected]=useState(0);
 const input=useRef<HTMLInputElement>(null),toast=useApp(s=>s.toast);
 useEffect(()=>{if(open){setQuery(initial);setSelected(0);setTimeout(()=>input.current?.focus(),0)}},[open,initial]);
 useEffect(()=>{if(!open||!query.trim()){setItems([]);return}let alive=true;const timer=setTimeout(()=>{
  void resolveLaunch(query,'palette',true).then(out=>{if(alive){setItems(out.candidates||[]);setSelected(0)}}).catch(()=>{if(alive)setItems([])});
 },140);return()=>{alive=false;clearTimeout(timer)};},[open,query]);
 if(!open)return null;
 async function openItem(c:LaunchCandidate){setBusy(true);try{
   const result=await confirmLaunch(c.id);
   if(result.status==='opened'){toast('success','برق فتح '+c.label);onClose()}
   else toast('info',result.reason||'التشغيل محتاج موافقتك');
 }catch(error){toast('error','التشغيل ماكملش',error instanceof Error?error.message:'تعذر فتح العنصر')}
 finally{setBusy(false)}}
 return <div className="fixed inset-0 z-[90] flex items-start justify-center bg-black/65 px-3 pt-[12vh]" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}>
  <section role="dialog" aria-modal="true" aria-label="مشغل برق السريع" dir="rtl" className="w-full max-w-[660px] overflow-hidden rounded-xl border border-stroke bg-surface shadow-2xl">
    <header className="flex items-center gap-3 border-b border-stroke px-4 py-3"><Search size={18} className="text-accent"/><input ref={input} value={query} onChange={e=>setQuery(e.target.value)}
      onKeyDown={e=>{if(e.key==='Escape')onClose();if(e.key==='ArrowDown'){e.preventDefault();setSelected(x=>Math.min(x+1,items.length-1))}if(e.key==='ArrowUp'){e.preventDefault();setSelected(x=>Math.max(x-1,0))}if(e.key==='Enter'&&items[selected])void openItem(items[selected])}}
      className="min-w-0 flex-1 bg-transparent text-sm text-primary outline-none" placeholder="افتح برنامج، ملف، فولدر أو موقع…" aria-label="ابحث عن عنصر"/>
      <button className="rounded p-1 hover:bg-elevated" aria-label="إغلاق" onClick={onClose}><X size={18}/></button></header>
    <div className="max-h-[55vh] overflow-y-auto p-2">
      {!query.trim()&&<p className="px-3 py-5 text-center text-sm text-secondary">اكتب اسم البرنامج أو الملف. البحث كله محلي، من غير موديلات سحابية.</p>}
      {query.trim()&&!items.length&&<p className="px-3 py-5 text-center text-sm text-secondary">مفيش نتائج حالياً. جرّب اسم تاني أو حدّث فهرس الملفات.</p>}
      {items.map((c,i)=>{const Icon=icons[c.kind]||FileText;return <button key={c.id} disabled={busy} aria-selected={i===selected} onMouseEnter={()=>setSelected(i)} onClick={()=>void openItem(c)}
        className={`flex w-full items-center gap-3 rounded-lg px-3 py-3 text-start text-sm transition-colors ${selected===i?'bg-accent/10 text-primary':'hover:bg-elevated text-secondary'}`}>
        <Icon size={18}/><span className="min-w-0 flex-1"><span className="block truncate font-semibold">{c.label}</span><span className="block truncate text-xs text-muted" dir="ltr">{c.path_or_appid}</span></span>
        <span className="rounded border border-stroke px-1.5 py-0.5 text-xs">{c.risk==='high'?'موافقة':c.kind==='app'?'تطبيق':c.kind==='site'?'موقع':'ملف'}</span>
       </button>})}
    </div>
    <footer className="flex items-center justify-between gap-2 border-t border-stroke px-4 py-2 text-xs text-secondary"><span>↑ ↓ للتنقل · Enter للفتح · Esc للإغلاق</span>
      <button className="inline-flex items-center gap-1 hover:text-primary" onClick={()=>void requestJSON('/v1/launch/reindex',{method:'POST'}).then(()=>toast('success','اتحدّث فهرس الملفات')).catch(()=>toast('error','تعذّر تحديث الفهرس'))}><RefreshCw size={14}/> تحديث الفهرس</button></footer>
  </section>
 </div>
}
