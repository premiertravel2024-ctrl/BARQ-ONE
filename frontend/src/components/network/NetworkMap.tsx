import {useEffect,useState} from 'react';
import {Activity,AlertTriangle,CheckCircle2,WifiOff} from 'lucide-react';

type Node={id:string;provider:string;enabled:boolean;configured:boolean;health:'green'|'amber'|'red';local:boolean;remaining_today:number|null};
type Span={stage:string;ts:number;model?:string;reason?:string;duration_ms?:number};
type Trace={id:string;created:number;status:string;model:string|null;steps:Span[]};
type MapData={models:Node[];traces:Trace[];metrics:{requests:number;completed:number;latency_ms:Record<string,{p50:number|null;p95:number|null}>}};
const names:Record<string,string>={intake:'استقبال',triage:'فهم المهمة',route:'اختيار المسار',privacy:'فحص الخصوصية',model_call:'استدعاء النموذج',verify:'فحص الرد',final:'اكتمل',error:'تعذّر'};
export function NetworkMap({active=true}:{active?:boolean}){
 const [data,setData]=useState<MapData|null>(null);const [selected,setSelected]=useState<string>('');const [error,setError]=useState('');
 useEffect(()=>{if(!active)return;let current=true;
  async function load(){try{const response=await fetch('/v1/brain/network/map',{cache:'no-store'});if(!response.ok)throw new Error(String(response.status));const value=await response.json() as MapData;
   if(current){setData(value);setError('')}}catch(e){if(current)setError(e instanceof Error?e.message:'غير متاح')}}
  void load();const timer=setInterval(()=>void load(),9000);return()=>{current=false;clearInterval(timer)};
 },[active]);
 const traces=data?.traces||[];const trace=traces.find(t=>t.id===selected)||traces[0];
 const entries=(data?.models||[]).slice(0,20);const cols=2;const rows=Math.ceil(entries.length/cols);const height=Math.max(150,rows*66+30);const selectedModel=trace?.model;
 return <section dir="rtl" className="space-y-4" aria-label="خريطة شبكة موديلات برق">
  <div className="flex items-center gap-2 text-sm font-semibold"><Activity size={17} className="text-accent"/>شبكة الأوامر والموديلات <span className="ms-auto text-xs text-muted">تحديث تلقائي</span></div>
  <p className="text-xs text-secondary">بيانات محلية فعلية من محرك برق. الأصفر معناه نموذج لم يتم التأكد من عمله بعد، والأحمر يعني نموذج متوقف مؤقتًا. الحصص تقديرية حسب الإعدادات مش رصيد مؤكد من المزود.</p>
  {error&&<p className="flex items-center gap-2 text-xs text-danger"><WifiOff size={15}/>{error}</p>}
  {!data&&<p className="text-xs text-muted">بقرأ حالة الشبكة…</p>}
  {data&&<>
   <div className="rounded-lg border border-stroke bg-elevated/50 p-2">
    <div className="mb-2 flex items-center gap-2 text-xs text-secondary"><span className="rounded-md border border-accent/30 bg-accent/10 px-2 py-1 text-accent">BARQ Brain</span><span>→</span><span>تقييم المهام</span><span>→</span><span>الموديلات</span></div>
    <div className="relative w-full overflow-hidden rounded-md bg-[#0f1115]" style={{height}}>
     <svg className="absolute inset-0 h-full w-full" viewBox={`0 0 660 ${height}`} preserveAspectRatio="none" aria-hidden="true">
      {entries.map((item,index)=>{const col=index%cols,row=Math.floor(index/cols),x=120+col*300,y=35+row*66;return <path key={item.id} d={`M 24 ${height/2} C 80 ${height/2}, 70 ${y}, ${x} ${y}`} fill="none" stroke={item.id===selectedModel?'#E8263E':'#414650'} strokeWidth={item.id===selectedModel?2.4:1} strokeOpacity={item.id===selectedModel?1:.55}/>})}
      <circle cx="24" cy={height/2} r="8" fill="#E8263E"/>
     </svg>
     {entries.map((item,index)=>{const col=index%cols,row=Math.floor(index/cols);return <div key={item.id} className={`absolute flex h-12 items-center gap-2 overflow-hidden rounded-md border px-2 text-xs ${item.id===selectedModel?'border-accent bg-[#36161f]':'border-[#343943] bg-[#1c2028]'}`} style={{left:`${18+col*44}%`,top:22+row*66,width:'38%'}} title={item.id}>
      <span className={`h-2 w-2 shrink-0 rounded-full ${item.health==='green'?'bg-green-500':item.health==='amber'?'bg-amber-400':'bg-red-500'}`}/>
      <div className="min-w-0"><div dir="ltr" className="truncate font-mono text-[10px] text-primary">{item.id}</div><div className="truncate text-[10px] text-secondary">{item.local?'على جهازك':'سحابي'} · {item.remaining_today===null?'الحصة غير معلنة':`${item.remaining_today} متبقٍ بالإعدادات`}</div></div>
     </div>})}
    </div>
   </div>
   <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-3"><div className="rounded-md bg-elevated p-2">الطلبات المسجّلة <strong className="block text-base">{data.metrics.requests}</strong></div><div className="rounded-md bg-elevated p-2">اكتملت <strong className="block text-base">{data.metrics.completed}</strong></div><div className="rounded-md bg-elevated p-2">الموديلات المعرفة <strong className="block text-base">{data.models.length}</strong></div></div>
   <h4 className="text-sm font-semibold">آخر مسارات التنفيذ</h4>
   {traces.length===0?<p className="text-xs text-muted">لسه مفيش طلبات اتنفذت على الشبكة الجديدة.</p>:<div className="flex flex-wrap gap-2">{traces.slice(0,8).map(t=><button key={t.id} onClick={()=>setSelected(t.id)} className={`rounded-md border px-2 py-1 text-xs ${trace?.id===t.id?'border-accent text-accent':'border-stroke text-secondary'}`} title={t.id}>{new Date(t.created*1000).toLocaleTimeString('ar-EG')} · {t.status==='done'?'اكتمل':t.status==='error'?'تعذّر':'جارٍ'}</button>)}</div>}
   {trace&&<div className="space-y-2 rounded-lg border border-stroke p-3 text-xs"><h5 className="flex items-center gap-2 font-semibold">{trace.status==='done'?<CheckCircle2 size={15} className="text-green-500"/>:<AlertTriangle size={15} className="text-amber-500"/>}تفاصيل الطلب <span dir="ltr" className="ms-auto font-mono text-muted">{trace.id.slice(0,10)}</span></h5>{trace.steps.map((s,i)=><div key={i} className="flex flex-wrap items-center justify-between gap-2 border-b border-stroke/70 py-1"><span>{names[s.stage]||s.stage}{s.model?` · ${s.model}`:''}</span><span className="text-muted">{s.duration_ms===undefined?'':`${s.duration_ms} ms`}</span></div>)}{trace.steps.length===0&&<p className="text-muted">مفيش خطوات مسجّلة</p>}</div>}
  </>}
 </section>;
}
