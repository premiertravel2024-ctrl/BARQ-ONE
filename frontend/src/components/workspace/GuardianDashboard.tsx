import {useCallback,useEffect,useState} from 'react';
import {Activity,AlertTriangle,ArrowLeft,CheckCircle2,Code2,History,MonitorCog,Package,RefreshCcw,ShieldCheck,Wrench} from 'lucide-react';
import {requestJSON} from '../../lib/backend';
import {Button} from '../ui/Button';

type Category={id:string;title_ar:string;status:string;detail_ar:string};
type Finding={id:string;file:string;line:number;severity:string;title_ar:string;rule:string};
type Checkpoint={id:string;path:string;time:number;kind:string;restorable:boolean};
type GuardianReport={workspace_name:string;categories:Category[];security:{checked:number;summary:Record<string,number>;findings:Finding[];limit:number};dependencies:{manifests:string[];locks:string[];note_ar:string;suggested_checks:string[]};build:{checks:Array<{name:string;status:string}>;note_ar:string};checkpoints:Checkpoint[];score:null;score_label_ar:string;note_ar:string};
const badgeText:Record<string,string>={warning:'تحتاج مراجعة',reviewed:'تم الفحص',unknown:'لم يُختبر',not_applicable:'غير منطبق',needs_verification:'غير متحقق',pass:'جاهز في البيئة'};
const symbol:Record<string,typeof ShieldCheck>={code:Code2,dependencies:Package,tests:CheckCircle2,build:MonitorCog,recovery:History,runtime:Activity};
const errorText=(e:unknown)=>e instanceof Error?e.message:String(e);
export function GuardianDashboard({workspace,onFix,onOpen,onBack,onPlan,onRestore}: {
 workspace:string;onFix:(f:Finding)=>void;onOpen:(f:Finding)=>void;onBack:()=>void;onPlan:()=>void;onRestore:(id:string,path:string)=>void;
}){
 const [data,setData]=useState<GuardianReport|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [view,setView]=useState<'overview'|'findings'|'backups'|'build'|'team'|'runtime'>('overview');
 const [pid,setPid]=useState(''),[runtime,setRuntime]=useState('');
 const refresh=useCallback(async()=>{
  if(!workspace)return;setBusy(true);setError('');
  try{setData(await requestJSON<GuardianReport>(`/v1/studio/guardian/health?workspace=${encodeURIComponent(workspace)}`))}
  catch(e){setError(errorText(e))}finally{setBusy(false)}
 },[workspace]);
 useEffect(()=>{setData(null);setView('overview');setRuntime('')},[workspace]);
 return <section className="guardian-dashboard" dir="rtl" aria-label="مركز حماية المشروع">
   <header className="guardian-head">
     <div className="guardian-heading"><div className="guardian-emblem"><ShieldCheck size={21}/></div><div><h2>مركز مراقبة المشروع</h2><p>BARQ Guardian · الفحص محلي، والإصلاح بعد موافقتك</p></div></div>
     <div className="guardian-head-actions"><Button variant="secondary" size="sm" onClick={onBack} icon={<ArrowLeft size={14}/>}>المحرر</Button><Button variant="primary" size="sm" onClick={()=>void refresh()} disabled={busy||!workspace} icon={<RefreshCcw size={14}/>}>{busy?'جاري الفحص…':'افحص المشروع'}</Button></div>
   </header>
   <nav className="guardian-tabs" aria-label="أقسام المراقبة">{([
     ['overview','نظرة عامة'],['findings','المشكلات'],['backups','الاستعادة'],['build','البناء'],['team','فريق البرمجة'],['runtime','التشغيل']
   ] as const).map(([key,label])=><button key={key} type="button" className={view===key?'active':''} onClick={()=>setView(key)}>{label}</button>)}</nav>
   <div className="guardian-content">
     {!workspace?<div className="guardian-empty">افتح مجلد مشروع علشان يبدأ مركز المراقبة.</div>:
     error?<div className="guardian-error" role="alert">تعذّر فحص المشروع: {error}</div>:
     !data?<div className="guardian-empty"><ShieldCheck size={32}/><h3>مشروعك تحت سيطرتك</h3><p>اضغط «افحص المشروع» لمراجعة الكود والاعتماديات وجاهزية البناء. مفيش فحوصات سحابية أو تعديل تلقائي.</p></div>:
     <>
       {view==='overview'&&<><div className="guardian-banner"><div><strong>حالة المشروع: مراجعة غير مكتملة</strong><p>{data.score_label_ar}</p></div><span>آخر فحص: {new Date(Date.now()).toLocaleTimeString('ar-EG')}</span></div>
        <div className="guardian-grid">{data.categories.map(c=>{const Icon=symbol[c.id]||ShieldCheck;return <button className="guardian-tile" key={c.id} onClick={()=>setView(c.id==='recovery'?'backups':c.id==='build'?'build':c.id==='runtime'?'runtime':c.id==='code'?'findings':'overview')}>
          <div className="guardian-tile-header"><Icon size={19}/><span className={`guardian-status status-${c.status}`}>{badgeText[c.status]||c.status}</span></div><strong>{c.title_ar}</strong><p>{c.detail_ar}</p></button>})}</div>
        <div className="guardian-bottom-note"><AlertTriangle size={16}/><span>الفحص الثابت مش بديل لتشغيل الاختبارات أو فحص أحدث ثغرات المكتبات. لا تعتبر «لم يُختبر» نجاحًا.</span></div>
       </>}
       {view==='findings'&&<div className="guardian-section"><div className="guardian-section-head"><h3>أخطاء وتنبيهات الكود</h3><span>{data.security.findings.length} تنبيه من {data.security.checked} ملف</span></div>
         {data.security.findings.length===0?<div className="guardian-quiet">مفيش تنبيهات ضمن نطاق الفحص الحالي، لكن ده مش ضمان أمان كامل.</div>:<div className="guardian-findings">{data.security.findings.map(f=><div key={f.id} className="guardian-finding"><span className={`guardian-dot level-${f.severity}`}/><div className="guardian-finding-main"><strong>{f.title_ar}</strong><span dir="ltr">{f.file}:{f.line}</span></div><button onClick={()=>onOpen(f)}>افتح الملف</button><button className="guardian-fix" onClick={()=>onFix(f)}><Wrench size={13}/> اقترح إصلاح</button></div>)}</div>}
       </div>}
       {view==='backups'&&<div className="guardian-section"><div className="guardian-section-head"><h3>تاريخ التعديلات</h3><span>نقاط استعادة للتعديلات المحفوظة</span></div>
         {data.checkpoints.length===0?<div className="guardian-quiet">لسه مفيش نقاط استعادة. برق بينشئ نقطة قبل تطبيق التعديل.</div>:data.checkpoints.map(b=><div key={b.id} className="guardian-backup"><div><strong dir="ltr">{b.path}</strong><p>{new Date(b.time*1000).toLocaleString('ar-EG')}</p></div><Button variant="secondary" size="sm" onClick={()=>onRestore(b.id,b.path)}>استعادة بعد التأكيد</Button></div>)}
         <p className="guardian-note">الاستعادة متاحة للملفات التي عدّلها برق من خلال المحرر، وليست نسخة كاملة من المستودع.</p>
       </div>}
       {view==='build'&&<div className="guardian-section"><div className="guardian-section-head"><h3>جاهزية التطبيق والبناء</h3><span>فحص متطلبات فقط، بدون تنفيذ</span></div>
         {data.build.checks.map(c=><div className="guardian-build-row" key={c.name}><span dir="ltr">{c.name}</span><span className={`guardian-status status-${c.status}`}>{badgeText[c.status]||'لم يُختبر'}</span></div>)}
         <p className="guardian-note">{data.build.note_ar}</p>
         <h3>فحص المكتبات</h3><p className="guardian-note">{data.dependencies.note_ar}</p><p dir="ltr">{data.dependencies.manifests.join(' · ')||'لا توجد ملفات اعتماديات'}</p>
       </div>}
       {view==='team'&&<div className="guardian-section"><div className="guardian-section-head"><h3>فريق البرمجة المنسق</h3><span>مراحل مراجعة باعتمادك</span></div><div className="guardian-team-grid">{[
        ['المخطط','يفهم المهمة ويقسم خطواتها'],['المبرمج','يقترح تغييرات الكود'],['المراجع','يراجع الجودة والأمان'],['المختبر','يقارن النتيجة بالفحوصات']
       ].map(([name,description],i)=><div key={name} className="guardian-team-member"><span>{i+1}</span><strong>{name}</strong><p>{description}</p></div>)}</div>
       <p className="guardian-note">تنسيق الأدوار هنا خطة عمل؛ لا يعني تشغيل 4 موديلات في نفس اللحظة، ولا يجري استدعاءات مجانية تلقائيًا.</p><Button size="sm" variant="primary" onClick={onPlan}>حضّر طلب خطة من برق</Button></div>}
       {view==='runtime'&&<div className="guardian-section"><div className="guardian-section-head"><h3>مراقب عمليات المشروع</h3><span>قراءة واحدة بطلبك</span></div><p className="guardian-note">ادخل رقم PID لعملية تعمل من مجلد المشروع؛ القراءة لا تنهي العملية ولا تراقب الجهاز كله.</p>
         <div className="guardian-runtime-form"><input className="ui-input" dir="ltr" inputMode="numeric" placeholder="PID" value={pid} onChange={e=>setPid(e.target.value)} /><Button size="sm" disabled={!pid||!/^\d+$/.test(pid)} onClick={()=>void requestJSON<Record<string,unknown>>(`/v1/studio/guardian/runtime?workspace=${encodeURIComponent(workspace)}&pid=${encodeURIComponent(pid)}`).then(v=>setRuntime(JSON.stringify(v,null,2))).catch(e=>setRuntime(errorText(e)))}>قراءة الحالة</Button></div>
         {runtime&&<pre dir="ltr" className="guardian-runtime-result">{runtime}</pre>}</div>}
      </>}
   </div>
 </section>;
}
