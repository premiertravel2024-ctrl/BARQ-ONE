import {useEffect,useState} from 'react';
import {Activity, Cpu, HardDrive, RefreshCw, ShieldCheck} from 'lucide-react';
import {Button} from '../ui/Button';
import {useApp} from '../../store';

type Mode='eco'|'balanced'|'performance';
type Profile={
  hardware:{logical_cpu_cores:number;cpu_load_percent:number|null;ram_total_bytes:number|null;
    ram_available_bytes:number|null;gpus:{name:string;vram_mb:number}[];gpu_checked:boolean;platform:string;mode:Mode};
  limits:{mode:Mode;scan_workers:number;scan_max_files:number;routing_history_messages:number};
  modes:Mode[];auto:boolean;
};
const sizes=(n:number|null)=>n===null?'غير متاح':`${(n/1024**3).toFixed(1)} GB`;
const pct=(n:number|null)=>typeof n==='number'?`${Math.round(n)}%`:'غير متاح';
export function AdaptiveBrainSettings({active}:{active:boolean}){
 const language=useApp(s=>s.language),ar=language==='ar';
 const [data,setData]=useState<Profile|null>(null),[pending,setPending]=useState(false),[error,setError]=useState('');
 const refresh=async()=>{
  try{const r=await fetch('/v1/system/resources',{cache:'no-store'});if(!r.ok)throw new Error(`HTTP ${r.status}`);
   setData(await r.json() as Profile);setError('')}
  catch(e){setError(e instanceof Error?e.message:'Resource information unavailable')}
 };
 useEffect(()=>{if(!active)return;void refresh();const timer=window.setInterval(()=>void refresh(),15000);return()=>window.clearInterval(timer)},[active]);
 const setMode=async(mode:Mode)=>{
  setPending(true);
  try{const r=await fetch('/v1/system/resources/mode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode})});
   if(!r.ok)throw new Error(`HTTP ${r.status}`);setData(await r.json() as Profile);setError('')}
  catch(e){setError(e instanceof Error?e.message:'Unable to change mode')}
  finally{setPending(false)}
 };
 const load=data?.hardware.cpu_load_percent??null;
 const ram=data?.hardware.ram_total_bytes??null;
 const available=data?.hardware.ram_available_bytes??null;
 const usedPct=ram&&available!==null?Math.max(0,Math.min(100,Math.round((1-available/ram)*100))):null;
 const modes:{id:Mode;title:string;detail:string}[]=ar?[
  {id:'eco',title:'اقتصادي',detail:'موارد أقل وفحوصات أخف'},
  {id:'balanced',title:'متوازن',detail:'يتكيّف تلقائيًا مع الضغط'},
  {id:'performance',title:'أداء عالٍ',detail:'فحص أوسع عند توفر الموارد'}
 ]:[
  {id:'eco',title:'Eco',detail:'Lower background load'},
  {id:'balanced',title:'Balanced',detail:'Adapts to device pressure'},
  {id:'performance',title:'Performance',detail:'More parallel work when available'}
 ];
 return <section className="space-y-3 border-t border-stroke pt-5" aria-label={ar?'العقل المتكيف مع موارد الجهاز':'Adaptive local resource manager'}>
  <div className="flex items-center justify-between gap-3"><div><h3 className="flex items-center gap-2 text-sm font-semibold"><Cpu size={16}/>{ar?'العقل المتكيف مع الجهاز':'Adaptive device resources'}</h3><p className="mt-1 text-xs text-secondary">{ar?'برق يضبط حدود معالجة البيانات المحلية حسب الجهاز والضغط الحالي.':'BARQ adjusts local processing budgets to available resources.'}</p></div><Button size="sm" variant="secondary" icon={<RefreshCw size={14}/>} onClick={()=>void refresh()}>{ar?'تحديث':'Refresh'}</Button></div>
  <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">{modes.map(mode=><button key={mode.id} type="button" disabled={pending} onClick={()=>void setMode(mode.id)} className={`rounded-xl border p-3 text-start transition-colors ${data?.limits.mode===mode.id?'border-accent/60 bg-accent/10':'border-stroke bg-elevated hover:border-accent/30'}`} aria-pressed={data?.limits.mode===mode.id}>
   <strong className="text-sm">{mode.title}</strong><p className="mt-1 text-[11px] text-secondary">{mode.detail}</p></button>)}</div>
  {data&&<div className="rounded-xl border border-stroke bg-elevated p-3 sm:p-4">
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <div className="space-y-2"><div className="flex items-center justify-between text-xs"><span className="flex items-center gap-2"><Activity size={14}/>{ar?'ضغط المعالج':'CPU load'} · {data.hardware.logical_cpu_cores} {ar?'خيط':'threads'}</span><strong dir="ltr">{pct(load)}</strong></div><div className="h-1.5 overflow-hidden rounded-full bg-base"><div className="h-full rounded-full bg-accent/70 transition-all" style={{width:`${load??0}%`}}/></div></div>
      <div className="space-y-2"><div className="flex items-center justify-between text-xs"><span className="flex items-center gap-2"><HardDrive size={14}/>{ar?'الذاكرة المستخدمة':'RAM used'}</span><strong dir="ltr">{pct(usedPct)}</strong></div><div className="h-1.5 overflow-hidden rounded-full bg-base"><div className="h-full rounded-full bg-accent/70 transition-all" style={{width:`${usedPct??0}%`}}/></div><p className="text-[11px] text-secondary">{ar?'متاحة':'Available'}: {sizes(available)} / {sizes(ram)}</p></div>
    </div>
    <div className="mt-4 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
      <div className="rounded-lg bg-base/60 p-2">{ar?'عمليات الفحص المتزامنة':'Scan workers'}<strong className="mt-1 block text-base" dir="ltr">{data.limits.scan_workers}</strong></div>
      <div className="rounded-lg bg-base/60 p-2">{ar?'حد الملفات في الفحص':'File scan limit'}<strong className="mt-1 block text-base" dir="ltr">{data.limits.scan_max_files}</strong></div>
      <div className="col-span-2 rounded-lg bg-base/60 p-2 sm:col-span-1">{ar?'سياق التوجيه':'Routing history'}<strong className="mt-1 block text-base" dir="ltr">{data.limits.routing_history_messages}</strong></div>
    </div>
    <div className="mt-3 flex flex-wrap items-start gap-2 text-xs text-secondary"><Cpu size={14} className="mt-0.5 shrink-0"/><span>{data.hardware.gpus.length?data.hardware.gpus.map(g=>`${g.name} (${Math.round(g.vram_mb/1024)} GB VRAM)`).join(' · '):(ar?'لم يُرصد GPU عبر NVIDIA-SMI؛ تسريع النماذج يظل من مسؤولية مزود النموذج.':'No GPU detected through NVIDIA-SMI; model inference remains provider-controlled.')}</span></div>
  </div>}
  <div className="flex items-start gap-2 text-xs text-secondary"><ShieldCheck size={16} className="mt-0.5 shrink-0"/><span>{ar?'الفحص والجدولة محليان؛ لا تشغيل تلقائي لأوامر المشاريع، ولا تنزيل نماذج أو رفع كود للسحابة. الموارد لا تعني وعيًا ذاتيًا.':'Scheduling stays local. No automatic command execution, model downloads or source uploads.'}</span></div>
  {error&&<p className="text-xs text-danger" role="alert">{error}</p>}
 </section>;
}
