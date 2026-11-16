import type {MissionProgress} from '../../store';
import {toolLabels} from '../../lib/approvals';

const states:Record<string,string>={pending:'لسه متنفذش',ready_to_test:'ملفاته محفوظة؛ محتاج اختبار',tests_passed:'اختباراته المرتبطة نجحت',test_failed:'اختباره فشل'};
export function MissionBoard({progress}:{progress:MissionProgress}){
 const requirements=progress.requirements||[],checks=progress.checks||[];
 if(!requirements.length&&!progress.planning_required)return null;
 const next=progress.files.find(f=>!['written','verified'].includes(f.status));
 return <details className="mission-board" open aria-label="خطة المشروع ونتائج التحقق" dir="rtl">
  <summary>خطة المشروع · {requirements.length} متطلب <span>{requirements.filter(r=>r.status==='tests_passed').length} باختبارات مرتبطة ناجحة</span></summary>
  <div className="mission-board-body">
   {progress.planning_required&&<p>خطة الملفات والمتطلبات لسه محتاجة الاعتماد؛ توليد الملفات هيبدأ بعدها.</p>}
   <p className="text-secondary">{next?`الملف التالي: ${next.path}`:'الملفات محفوظة؛ راجع أدلة الاختبار والتشغيل أدناه.'}</p>
   {requirements.map(req=><details key={req.id} className="mission-requirement">
    <summary><strong>{req.id} · {req.title}</strong><span data-status={req.status}>{states[req.status]||req.status}</span></summary>
    <p>{req.acceptance}</p><p dir="ltr">{req.files.join(' · ')}</p><p dir="ltr">{req.tests.length?req.tests.join('\n'):'Manual verification required'}</p>
   </details>)}
   {progress.interface_review&&<details className="mission-requirement"><summary>مراجعة UI · {progress.interface_review.issues.length} مشكلة · {progress.interface_review.warnings.length} تنبيه</summary>
    <p>فحص ثابت لـ {progress.interface_review.checked_files} ملف. تجربة الشكل والكيبورد وتغيير حجم النافذة لسه محتاجة تحقق فعلي.</p>
    {[...progress.interface_review.issues,...progress.interface_review.warnings].map((item,index)=><p key={index}><b dir="ltr">{item.path}:{item.line}</b> · {item.message}</p>)}
   </details>}
   {!!checks.length&&<div className="mission-checks">{checks.map(check=><span key={check.name}>{toolLabels[check.name]||check.name}: {check.status==='passed'?'نجح':check.status==='failed'?'فشل':'نتيجة قديمة؛ الملفات اتغيرت'}</span>)}</div>}
   {next?.recovery&&<p className="text-warning">{next.recovery.action}</p>}
   <p className="text-secondary">نجاح الاختبارات المرتبطة مش إثبات إن كل تفاصيل المتطلب أو تجربة الواجهة اتراجعت.</p>
  </div>
 </details>;
}
