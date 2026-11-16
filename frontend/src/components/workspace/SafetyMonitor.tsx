import {AlertCircle,CheckCircle2,ShieldAlert,ShieldCheck,ScanSearch} from 'lucide-react';
import {Button} from '../ui/Button';

export type SafetyFinding={id:string;file:string;line:number;rule:string;severity:'critical'|'high'|'medium'|'low';category:'security'|'error';title_ar:string;advice_ar:string};
export type SafetyReport={file?:string;checked?:number;findings:SafetyFinding[];summary:Record<string,number>;note_ar:string;supported?:boolean};

const severityText:Record<SafetyFinding['severity'],string>={critical:'حرج',high:'مرتفع',medium:'متوسط',low:'منخفض'};
export function SafetyMonitor({report,scanning,projectScanning,onProjectScan,onFix,onOpen,workspace,source,onSource}:{
 report:SafetyReport|null;scanning:boolean;projectScanning:boolean;
 onProjectScan:()=>void;onFix:(f:SafetyFinding)=>void;onOpen:(f:SafetyFinding)=>void;
 workspace:boolean;source:string;onSource:(s:string)=>void;
}){
 const findings=report?.findings||[];
 const count=findings.length;
 return <section dir="rtl" className="studio-safety" aria-label="مراقب أخطاء وأمان الكود">
  <div className="studio-safety-header">
   <div className="flex items-center gap-2"><ShieldCheck size={18} className="text-accent"/><strong>مراقب الكود والأمان</strong><span className="studio-safety-count">{scanning?'بيفحص…':`${count} تنبيه`}</span></div>
   <div className="flex flex-wrap gap-2"><Button size="sm" variant="secondary" disabled={!workspace||projectScanning} icon={<ScanSearch size={14}/>} onClick={onProjectScan}>{projectScanning?'بيفحص المشروع…':'فحص المشروع كله'}</Button></div>
  </div>
  <p className="studio-safety-intro">فحص محلي من غير إنترنت، من غير تشغيل كود أو تعديل ملفات السورس. التنبيهات مؤشرات محتاجة مراجعة.</p>
  <div className="studio-safety-source"><span>المصدر:</span><select aria-label="مصدر الفحص" value={source} onChange={e=>onSource(e.target.value)}><option value="draft">المحرر / كتابة برق</option><option value="project">نتائج المشروع</option></select>
   {report?.checked!==undefined&&<span>{report.checked} ملف اتفحص</span>}
  </div>
  <div className="studio-safety-summary">
   {(['critical','high','medium','low'] as const).map(severity=><div key={severity} className={`studio-safety-stat ${severity}`}><strong>{report?.summary?.[severity]||0}</strong><span>{severityText[severity]}</span></div>)}
  </div>
  {count===0?<div className="studio-safety-clean"><CheckCircle2 size={22}/><p>{report?'الفحص الحالي ماطلعش تنبيهات. ده مش ضمان إن الكود خالي من الثغرات.':'افتح ملف كود أو اطلب من برق يكتب كود، ونتيجة الفحص هتظهر هنا.'}</p></div>:
    <div className="studio-safety-list" role="list">{findings.map(f=><article role="listitem" key={f.id} className={`studio-safety-finding severity-${f.severity}`}>
      <div className="flex items-center gap-2"><AlertCircle size={15}/><strong>{f.title_ar}</strong><span className="studio-safety-level">{severityText[f.severity]}</span></div>
      <button className="studio-safety-path" dir="ltr" title="افتح الملف عند السطر" onClick={()=>onOpen(f)}>{f.file}:{f.line}</button>
      <p>{f.advice_ar}</p>
      <div className="studio-safety-finding-actions"><button type="button" onClick={()=>onOpen(f)}>افتح السطر</button><button type="button" onClick={()=>onFix(f)}><ShieldAlert size={13}/> اطلب إصلاحًا من برق</button></div>
    </article>)}</div>}
  <div className="studio-safety-footer"><ShieldCheck size={14}/> عرض الكود على الموديل مش هيتم تلقائيًا؛ التعديلات تفضل محتاجة مراجعتك وموافقتك.</div>
 </section>;
}
