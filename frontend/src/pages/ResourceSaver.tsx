import {useEffect,useMemo,useState} from 'react';
import {Activity,RotateCcw,PauseCircle,ShieldAlert} from 'lucide-react';
import {requestJSON} from '../lib/backend';
import {useApp} from '../store';

type Process={pid:number;name:string;publisher:string|null;ram_mb:number|null;cpu_percent:number|null;uptime_seconds:number|null;classification:'safe'|'keep'|'critical';reason:string;paused:boolean};
type Snapshot={status:string;mode:string;processes:Process[];paused:{pid:number;name:string}[];auto_modes_enabled:boolean;note?:string};
const modes=[['gaming','وضع الألعاب','Gaming'],['focus','وضع التركيز','Focus'],['battery','توفير البطارية','Battery Saver'],['movie','وضع الأفلام','Movie Mode']] as const;

export function ResourceSaver(){
 const ar=useApp(s=>s.language)==='ar';
 const [data,setData]=useState<Snapshot|null>(null);
 const [selected,setSelected]=useState<number[]>([]);
 const [mode,setMode]=useState('gaming');
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [last,setLast]=useState<number|null>(null);
 useEffect(()=>{
  let live=true;
  async function refresh(){
   try{
    const reply=await requestJSON<Snapshot>('/v1/resource-saver/processes');
    if(!live)return;
    setData(reply);setLast(Date.now());setError('');
   }catch(e){if(live)setError(e instanceof Error?e.message:String(e))}
  }
  void refresh();
  const timer=window.setInterval(()=>void refresh(),2600);
  return()=>{live=false;window.clearInterval(timer)};
 },[]);
 const allowed=new Set((data?.processes||[]).filter(x=>x.classification==='safe').map(x=>x.pid));
 const valid=selected.filter(x=>allowed.has(x));
 const totalRam=useMemo(()=>data?.processes.reduce((sum,p)=>sum+(p.ram_mb||0),0),[data]);
 async function action(kind:'apply'|'restore'){
  if(busy)return;
  if(kind==='apply'){
   if(!valid.length){setError(ar?'اختار برنامج آمن للإيقاف المؤقت الأول.':'Select a safe optional program first.');return;}
   const names=(data?.processes||[]).filter(x=>valid.includes(x.pid)).map(x=>x.name).join('، ');
   if(!window.confirm((ar?'هتوقف البرامج دي مؤقتًا لمدة دقيقتين، ومن غير حذف أو إنهاء: ':'Pause these apps for two minutes (no killing): ')+names))return;
  }
  setBusy(true);setError('');
  try{
   await requestJSON(kind==='apply'?'/v1/resource-saver/mode':'/v1/resource-saver/restore',{
    method:'POST',body:JSON.stringify(kind==='apply'?{mode,pids:valid,seconds:120,confirmed:true}:{})
   });
   const next=await requestJSON<Snapshot>('/v1/resource-saver/processes');
   setData(next);setSelected([]);
  }catch(e){setError(e instanceof Error?e.message:String(e))}
  finally{setBusy(false)}
 }
 return <div className="barq-media" dir={ar?'rtl':'ltr'}>
  <header className="barq-media-head"><div><h2>{ar?'توفير الموارد':'Resource Saver'}</h2><p>{ar?'مراقبة البرامج والإيقاف المؤقت القابل للاسترجاع، من غير حذف أو إنهاء إجباري.':'Monitor and temporarily pause approved optional apps without deleting them.'}</p></div>
   <span className="barq-chip"><ShieldAlert size={15}/>{ar?'العمليات المحمية لا يمكن إيقافها':'Critical processes protected'}</span></header>
  {error&&<p className="barq-media-error" role="alert">{error}</p>}
  <div className="barq-media-metrics">
   <div><span>{ar?'البرامج المرصودة':'Processes'}</span><strong>{data?.processes.length??'—'}</strong></div>
   <div><span>{ar?'استهلاك الذاكرة المعروض':'Displayed RAM'}</span><strong>{totalRam!=null?totalRam.toFixed(0)+' MB':'—'}</strong></div>
   <div><span>{ar?'الموقوفة مؤقتًا':'Temporarily paused'}</span><strong>{data?.paused.length??'—'}</strong></div>
  </div>
  <div className="barq-media-toolbar">
   <label>{ar?'الوضع':'Mode'} <select value={mode} onChange={e=>setMode(e.target.value)}>{modes.map(([key,arabic,english])=><option key={key} value={key}>{ar?arabic:english}</option>)}</select></label>
   <button type="button" disabled={busy||!valid.length} onClick={()=>void action('apply')}><PauseCircle size={16}/>{ar?'إيقاف مؤقت بعد الموافقة':'Pause selected with approval'}</button>
   <button type="button" disabled={busy||!data?.paused.length} onClick={()=>void action('restore')}><RotateCcw size={16}/>{ar?'استعادة الكل':'Restore All'}</button>
  </div>
  <p className="barq-muted">{ar?'كل إيقاف مدته دقيقتان كحد أقصى في الواجهة، ويُستعاد عند انتهاء المدة أو خروج برق الطبيعي. أول قراءة CPU ممكن تكون غير متاحة لحد العينة التالية.':'Each pause is auto-restored after two minutes or normal BARQ exit. CPU readings need a second sample.'}</p>
  <div className="barq-media-tablewrap">
   <table className="barq-media-table">
    <thead><tr><th>{ar?'تحديد':'Select'}</th><th>{ar?'البرنامج':'Program'}</th><th>RAM</th><th>CPU</th><th>{ar?'مدة التشغيل':'Uptime'}</th><th>{ar?'التصنيف والسبب':'Safety classification'}</th></tr></thead>
    <tbody>{(data?.processes||[]).map(p=><tr key={p.pid}>
      <td><input type="checkbox" aria-label={p.name} disabled={p.classification!=='safe'||p.paused||busy} checked={selected.includes(p.pid)} onChange={e=>setSelected(v=>e.target.checked?[...v,p.pid]:v.filter(id=>id!==p.pid))}/></td>
      <td><strong dir="auto">{p.name}</strong><small>PID {p.pid}</small></td>
      <td>{p.ram_mb===null?'—':p.ram_mb.toFixed(1)+' MB'}</td>
      <td>{p.cpu_percent===null?'—':p.cpu_percent.toFixed(1)+' %'}</td>
      <td>{p.uptime_seconds===null?'—':Math.round(p.uptime_seconds/60)+' min'}</td>
      <td><span className={'barq-process-status '+p.classification}>{p.paused?(ar?'متوقف مؤقتًا':'Paused'):p.classification==='safe'?(ar?'قابل للإيقاف بموافقة':'Safe with approval'):p.classification==='critical'?(ar?'محمي':'Protected'):(ar?'احتفظ به':'Keep')}</span><small dir="auto">{p.reason}</small></td>
    </tr>)}</tbody>
   </table>
   {!data&&<p className="barq-muted">{ar?'جاري قراءة العمليات من ويندوز…':'Loading real process measurements…'}</p>}
  </div>
  <p className="barq-muted"><Activity size={13} style={{display:'inline'}}/> {last?new Date(last).toLocaleTimeString():'—'} · {ar?'الناشر غير متاح في العينة الحالية؛ لن نعرض بيانات مُختلقة.':'Publisher is unavailable from the current sample; no fabricated values.'}</p>
 </div>
}
