import {useState} from 'react';
import {HardDrive,ShieldCheck} from 'lucide-react';
import {requestJSON} from '../../lib/backend';
import {Button} from '../ui/Button';

type AuditModel={id:string;enabled:boolean;allowlisted:boolean;free:boolean;data_use:string;remaining_today:number|null};
type AuditProvider={provider:string;enabled:boolean;key_present:boolean;free_status:string;billing_blocked:boolean;data_use:string;notes_ar:string;models:AuditModel[]};
type AuditResult={providers:AuditProvider[];warnings:Record<string,string>;guarantee_ar:string};
const families=[
 {tier:'ذاكرة 8 GB',description:'نموذج 7–8B متعدد اللغات؛ تأكد من اسم الوسم وحجمه قبل التنزيل'},
 {tier:'ذاكرة 16 GB',description:'نموذج 8B عربي جيد أو نموذج برمجة كمّي متوسط'},
 {tier:'VRAM ‏24 GB',description:'نموذج برمجة 20–30B بضغط مناسب لقدرات الجهاز'},
 {tier:'التمثيلات الدلالية',description:'BGE-M3 محليًا، إن كان الوسم متاحًا عندك: ollama pull bge-m3'},
];
export function FreeAudit(){
 const [audit,setAudit]=useState<AuditResult|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false);
 async function run(){setLoading(true);setError('');try{setAudit(await requestJSON<AuditResult>('/v1/free-audit'))}catch(e){setError(e instanceof Error?e.message:'فشل فحص المجانية')}finally{setLoading(false)}}
 return <section className="space-y-3 rounded-lg border border-stroke bg-elevated p-3" aria-label="التدقيق المجاني">
  <div className="flex items-center gap-2"><ShieldCheck size={18}/><h3 className="font-semibold">تدقيق المجانية والخصوصية</h3></div>
  <p className="text-xs text-secondary">فحص محلي فقط: لا يرسل أي طلب للسحابة ولا يعرض مفاتيحك.</p>
  <Button size="sm" variant="secondary" onClick={()=>void run()} disabled={loading}>{loading?'جاري الفحص':'افحص مجانية الموديلات'}</Button>
  {error&&<p role="alert" className="text-xs text-danger">{error}</p>}
  {audit&&<div className="space-y-3"><p className="text-xs text-secondary">{audit.guarantee_ar}</p>{audit.providers.map(p=><div key={p.provider} className="rounded border border-stroke p-2 text-xs">
   <div className="flex flex-wrap items-center gap-2 font-semibold"><span dir="ltr">{p.provider}</span><span className="text-muted">{p.billing_blocked?'محظور بسبب طلب دفع':p.free_status==='requires_payment_method'?'يحتاج وسيلة دفع — محظور':p.free_status==='unverified'?'غير مؤكد':p.enabled?'مسموح بشروط':'غير مفعل'}</span></div>
   <p className="mt-1 text-secondary">{p.notes_ar}</p>
   <p className="mt-1 text-muted">استخدام البيانات: {p.data_use==='may-train'?'قد تُستخدم للتدريب':p.data_use==='no-training'?'بدون تدريب معلن':'غير معروف'} · المفتاح: {p.key_present?'متوفر':'غير محفوظ'}</p>
   {p.models.filter(m=>m.enabled).map(m=><p key={m.id} dir="ltr" className="mt-1 break-all text-secondary">{m.allowlisted&&m.free?'✓':'✕'} {m.id} · {m.remaining_today==null?'quota ?':`${m.remaining_today} remaining (estimated)`}</p>)}
   {audit.warnings[p.provider]&&<p className="mt-1 text-secondary">{audit.warnings[p.provider]}</p>}
  </div>)}</div>}
  <div className="border-t border-stroke pt-3"><h4 className="mb-2 flex items-center gap-2 text-sm font-semibold"><HardDrive size={16}/> نماذج محلية مقترحة (لا تُنزَّل تلقائيًا)</h4>{families.map(x=><p key={x.tier} className="mb-2 text-xs text-secondary"><span className="font-semibold text-primary">{x.tier}: </span>{x.description}</p>)}<p className="text-xs text-muted">تأكد من الوسم الحقيقي من مكتبة Ollama قبل تنفيذ أي أمر pull. التنزيل يحتاج موافقتك.</p></div>
 </section>
}
