import {Activity,ArrowLeft,CheckCircle2,ClipboardCheck,Code2,FileCode2,FolderOpen,LayoutDashboard,RefreshCcw,ShieldCheck,TestTube2,TriangleAlert} from 'lucide-react';
import type {AgentTask} from '../../store';
import type {UiAudit} from './uiAudit';

type Props={
 mission?:AgentTask;projectName:string;workspaceReady:boolean;hasPendingApproval:boolean;
 audit:UiAudit|null;auditBusy:boolean;auditError:string;
 onAudit:()=>void;onChat:()=>void;onPlan:()=>void;onPickFolder:()=>void;
 onOpenFile:(path:string)=>void;onEditor:()=>void;onDiagnostics:()=>void;onContinue:()=>void;
};
const humanStatus:Record<string,string>={workspace_needed:'اختيار مشروع',plan_ready:'في انتظار موافقتك',running:'جاري التنفيذ',paused:'متوقفة مؤقتًا',done:'انتهت الخطوة المسجلة',failed:'تحتاج إصلاحًا',cancelled:'ملغاة'};
const fileStatus:Record<string,string>={verified:'تم التحقق',written:'حُفظ على القرص',writing:'بانتظار الموافقة',needs_attention:'تحتاج إصلاحًا',pending:'لم تبدأ'};
const reqStatus:Record<string,string>={pending:'لم يبدأ',ready_to_test:'جاهز للاختبار',tests_passed:'اختبار مرتبط ناجح',test_failed:'فشل اختبار مرتبط'};

export function WorkCenter({mission,projectName,workspaceReady,hasPendingApproval,audit,auditBusy,auditError,onAudit,onChat,onPlan,onPickFolder,onOpenFile,onEditor,onDiagnostics,onContinue}:Props){
 const progress=mission?.missionProgress;
 const all=progress?.files||[];
 const saved=all.filter(f=>f.status==='written'||f.status==='verified').length;
 const requirements=progress?.requirements||[];
 const passed=requirements.filter(r=>r.status==='tests_passed').length;
 const checks=progress?.checks||[];
 const failed=checks.filter(c=>c.status==='failed').length;
 const steps=[
  {title:'فهم الطلب',detail:mission?.goal?'الطلب مسجل':'في انتظار أمر واضح',ready:!!mission?.goal},
  {title:'التخطيط',detail:requirements.length?`${requirements.length} متطلب مسجل`:progress?.planning_required?'الخطة تحتاج موافقة':'راجع الخطة من المحادثة',ready:!!progress&&!progress.planning_required},
  {title:'بناء الملفات',detail:all.length?`${saved} من ${all.length} ملف محفوظ`:'لم تُسجل ملفات للمهمة',ready:all.length>0&&saved===all.length},
  {title:'الاختبار',detail:checks.length?`${checks.filter(c=>c.status==='passed').length} اختبارات ناجحة${failed?`، ${failed} فاشلة`:''}`:'لا توجد نتائج اختبار مسجلة',ready:checks.length>0&&checks.every(c=>c.status==='passed')},
  {title:'التحقق النهائي',detail:'لا يثبت نجاح الاختبارات جودة الشكل أو كل المتطلبات',ready:false},
 ];
 return <section className="barq-work-center" dir="rtl" aria-label="مركز تنفيذ مهام برق">
  <div className="barq-work-head">
   <div className="barq-work-kicker"><LayoutDashboard size={15}/> مركز العمل <span>BARQ WORKSPACE</span></div>
   <h2>{mission?'تنفيذ المشروع ومتابعة النتائج':'من الفكرة إلى برنامج قابل للمراجعة'}</h2>{mission?.goal&&<details className="barq-work-goal"><summary>عرض طلب المشروع الأصلي</summary><p>{mission.goal}</p></details>}
   <p>{mission?'تابع خطوات المهمة والملفات والاختبارات الفعلية. كل نتيجة موثقة بحالتها، من غير ادعاء نجاح غير مثبت.':'اطلب من برق إنشاء برنامج أو تحسين مشروع، وتابع التخطيط والتنفيذ والاختبار من هنا، أو افتح ملفات مشروعك الحالي.'}</p>
   <div className="barq-work-actions">
    <button type="button" className="primary" onClick={mission?onChat:onPlan}>{mission?(hasPendingApproval?'مراجعة الخطوة والموافقة':'الرجوع إلى متابعة المحادثة'):'ابدأ بمهمة برمجية'} <ArrowLeft size={16}/></button>
    {workspaceReady?<button onClick={onEditor}><Code2 size={16}/> فتح محرر الملفات</button>:<button onClick={onPickFolder}><FolderOpen size={16}/> اختيار مجلد المشروع</button>}
    {mission&&<button type="button" onClick={onContinue}><ClipboardCheck size={16}/> جهّز طلب متابعة للمهمة</button>}
    <button onClick={onAudit} disabled={!workspaceReady||auditBusy}><ShieldCheck size={16}/>{auditBusy?'فحص الواجهات...':'فحص جودة الـUI'}</button>
   </div>
   <div className="barq-work-context"><span className="barq-work-state" data-state={mission?.status||'idle'}><Activity size={13}/>{mission?humanStatus[mission.status]||mission.status:'جاهز لاستقبال مهمة'}</span><span className="barq-work-project" dir="ltr" title={projectName}>{projectName||'لم يتم فتح مشروع'}</span>{progress&&<span>{progress.calls_used} / {progress.call_budget} محاولة نموذج مسجلة</span>}</div>
  </div>

  <div className="barq-work-grid">
   <section className="barq-work-card" aria-labelledby="barq-stages-heading">
    <div className="barq-work-card-title"><h3 id="barq-stages-heading">مراحل التنفيذ</h3><span>الحالة الفعلية</span></div>
    <ol className="barq-work-steps">{steps.map((step,i)=><li key={step.title} data-ready={step.ready}>
      <span className="barq-work-step-number">{step.ready?<CheckCircle2 size={16}/>:String(i+1).padStart(2,'0')}</span>
      <div><strong>{step.title}</strong><p>{step.detail}</p></div>
    </li>)}</ol>
    {mission?.summary&&<p className="barq-work-notice"><ClipboardCheck size={16}/>{mission.summary}</p>}
   </section>
   <section className="barq-work-card" aria-labelledby="barq-files-heading">
    <div className="barq-work-card-title"><h3 id="barq-files-heading">ملفات المهمة</h3><span>{saved} / {all.length} محفوظة</span></div>
    {all.length?<div className="barq-work-files">{all.map(f=><button key={f.path} type="button" disabled={!['written','verified'].includes(f.status)} onClick={()=>onOpenFile(f.path)} title={f.last_error||f.path}>
      <FileCode2 size={16}/><span className="barq-work-filename" dir="ltr">{f.path}</span><span className="barq-work-file-status" data-status={f.status}>{fileStatus[f.status]||f.status}</span>
    </button>)}</div>:<div className="barq-work-empty"><FileCode2 size={23}/><p>لسه مفيش ملفات مسجلة للمهمة الحالية.</p><button onClick={onEditor}>استعرض ملفات المشروع</button></div>}
    <div className="barq-work-card-footer"><button onClick={onDiagnostics} disabled={!workspaceReady}><TestTube2 size={15}/> فحص المصدر واكتشاف الاختبارات</button></div>
   </section>
   <section className="barq-work-card" aria-labelledby="barq-tests-heading">
    <div className="barq-work-card-title"><h3 id="barq-tests-heading">المتطلبات والتحقق</h3><span>{passed}/{requirements.length} باختبارات مرتبطة ناجحة</span></div>
    {requirements.length?<div className="barq-work-requirements">{requirements.map(req=><details key={req.id}><summary><span>{req.title}</span><small data-status={req.status}>{reqStatus[req.status]||req.status}</small></summary><p>{req.acceptance}</p><p dir="ltr">{req.tests.length?req.tests.join(' · '):'Requires manual verification'}</p></details>)}</div>:<p className="barq-work-muted">لما برق يحدد متطلبات المشروع، هتظهر هنا مع طريقة اختبار كل متطلب.</p>}
    {!!checks.length&&<div className="barq-work-checks">{checks.map((c,i)=><span key={`${c.name}-${i}`} data-status={c.status}>{c.name}: {c.status==='passed'?'نجح':c.status==='failed'?'فشل':'يحتاج إعادة اختبار'}</span>)}</div>}
    {!!mission?.evidence&&<details className="barq-work-evidence"><summary>عرض دليل التنفيذ المسجل</summary><pre dir="auto">{mission.evidence}</pre></details>}
   </section>
   <section className="barq-work-card" aria-labelledby="barq-audit-heading">
    <div className="barq-work-card-title"><h3 id="barq-audit-heading">مراجعة جودة الواجهات</h3><span>{audit?`${audit.checked_files} ملف فُحص`:'فحص اختياري'}</span></div>
    {auditError&&<p role="alert" className="barq-work-alert"><TriangleAlert size={16}/>{auditError}</p>}
    {!audit?<p className="barq-work-muted">فحص ساكن للـHTML وTSX وCSS: حالات التركيز، التسميات، الاستجابة وأخطاء يمكن رصدها من المصدر. مش بديل عن تشغيل التطبيق واختبار شكله.</p>:<>
      <div className="barq-work-observations">{Object.entries(audit.observations).map(([key,val])=><span key={key}>{({'responsive_files':'استجابة','rtl_files':'RTL','labelled_controls':'تسميات','focus_styles':'تركيز الكيبورد','loading_states':'تحميل','error_states':'معالجة الأخطاء'} as Record<string,string>)[key]||key}: <b>{val.count}</b></span>)}</div>
      {audit.findings.length?<div className="barq-work-findings">{audit.findings.slice(0,16).map((f,i)=><div key={`${f.file}-${f.line}-${i}`}><TriangleAlert size={14}/><div><strong>{f.message}</strong><span dir="ltr">{f.file}:{f.line}</span></div></div>)}</div>:<p className="barq-work-muted">مافيش مؤشرات مُسجلة ضمن حدود الفحص الساكن، وده مش ضمان لجودة الشكل.</p>}
      {audit.truncated&&<p className="barq-work-alert">المراجعة جزئية بسبب حد عدد الملفات.</p>}
    </>}
    <div className="barq-work-card-footer"><button onClick={onAudit} disabled={!workspaceReady||auditBusy}><RefreshCcw size={15}/> {audit?'إعادة الفحص':'ابدأ فحص الواجهة'}</button></div>
    <p className="barq-work-disclaimer">الفحص البصري والاختبارات التفاعلية لسه مطلوبين على Windows وفي المتصفح.</p>
   </section>
  </div>
 </section>;
}
