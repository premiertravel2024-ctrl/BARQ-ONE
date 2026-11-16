import type {Message} from '../store';
export function pendingApproval(messages:Message[]){
 const message=[...messages].reverse().find(item=>item.role==='assistant'&&item.agentTask);
 const task=message?.agentTask;if(!message||!task||task.status!=='plan_ready')return null;
 if(task.pendingEdit)return {messageId:message.id,kind:'save' as const,token:task.pendingEdit.approval_id,task,key:'save:'+task.pendingEdit.approval_id};
 if(task.plan?.plan.steps.length)return {messageId:message.id,kind:'execute' as const,token:task.plan.plan_id,task,key:'execute:'+task.plan.plan_id};
 return null;
}
export const toolLabels:Record<string,string>={project_directory:'إنشاء مجلد من خطة المشروع',project_plan:'اعتماد خطة الملفات والمتطلبات والاختبارات',project_acceptance:'تشغيل اختبارات المتطلبات المحددة',project_smoke:'اختبار بدء تشغيل التطبيق بدون واجهة',project_bootstrap:'إنشاء ملفات مشروع جديد',project_build:'بناء نسخة تشغيل من المشروع',
 workspace_read:'قراءة ملف من المشروع',workspace_list:'عرض ملفات المشروع',project_map:'فحص بنية المشروع',project_diagnostics:'تشخيص المشروع',
 code_search:'البحث في الكود',code_outline:'فحص بنية الملف',code_check:'فحص صحة الكود',code_replace:'تجهيز تعديل لمراجعته قبل الحفظ',
 workspace_edit:'تجهيز محتوى ملف للمراجعة',prepare_test_environment:'تجهيز بيئة المشروع وتنزيل pytest من الإنترنت',run_tests:'تشغيل اختبارات المشروع',git_status:'فحص حالة Git',git_diff:'عرض التغييرات',git_log:'عرض سجل Git',
 rea_analyze:'تشغيل أداة تحليل REA',mcp_call:'تشغيل الأداة المتصلة المحددة'};

/** BARQ's user-requested, project-scoped automation.
 * Inspecting source and preparing plans never requires repeated clicks.
 * Writing is confined to mission-tracked files/directories. Commands that
 * run arbitrary code, install packages, publish data or access external
 * accounts still require an explicit review; no OS/UAC bypass is attempted.
 * This is enforced in addition to the backend's own path and token checks.
 */
export function safeMissionAutopilot(candidate:ReturnType<typeof pendingApproval>):boolean{
 if(!candidate?.task.autopilot || candidate.task.kind!=='coding')return false;
 if(candidate.kind==='execute'){
  const steps=candidate.task.plan?.plan.steps||[];
  if(steps.length!==1)return false;
  const {tool}=steps[0];
  if(['workspace_list','project_map','project_diagnostics','code_search',
      'code_outline','code_check','workspace_read','git_status','git_diff',
      'git_log','project_plan'].includes(tool))return true;
 }
 const files=candidate.task.missionProgress?.files||[];
 if(!files.length)return false;
 const prefix=files[0].path.split('/')[0];
 if(!prefix||prefix==='.'||prefix==='..'||!files.every(x=>x.path.startsWith(prefix+'/')))return false;
 const isManaged=(p:string)=>files.some(x=>x.path===p);
 const isSafeRelative=(p:string)=>p.startsWith(prefix+'/')&&!p.split('/').some(x=>x==='..'||x==='.'||x==='')&&!/^[A-Za-z]:|^\\/.test(p);
 if(candidate.kind==='save')return isManaged(candidate.task.pendingEdit?.path||'');
 const steps=candidate.task.plan?.plan.steps||[];
 if(steps.length!==1)return false;
 const {tool,args}=steps[0];
 const path=typeof args.path==='string'?args.path:'';
 // Replacing existing code is an executable transformation, not a harmless
 // file preview; require review even when its path is tracked by the mission.
 if(tool==='workspace_edit')return isManaged(path);
 if(tool==='project_directory')return isSafeRelative(path);
 return false;
}
