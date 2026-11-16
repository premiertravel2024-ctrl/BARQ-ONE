type Blueprint={summary:string;files:Array<{path:string;purpose:string;depends_on:string[]}>;requirements:Array<{id:string;title:string;acceptance:string;tests:string[]}>};
export function BlueprintReview({value}:{value:unknown}){
 const plan=value as Blueprint|undefined;
 if(!plan||!Array.isArray(plan.files)||!Array.isArray(plan.requirements))return null;
 return <section aria-label="مراجعة خطة المشروع" className="max-h-80 space-y-3 overflow-auto text-sm" dir="rtl">
  <p>{plan.summary}</p>
  <strong>المتطلبات وطريقة التحقق</strong>
  {plan.requirements.map(req=><div key={req.id} className="rounded-lg border border-stroke p-3"><strong>{req.id} · {req.title}</strong><p className="mt-1 text-secondary">{req.acceptance}</p><p dir="ltr" className="mt-2 break-all font-mono text-xs">{req.tests.join(' · ')||'Manual verification required'}</p></div>)}
  <details><summary>الملفات وترتيب التنفيذ · {plan.files.length}</summary>{plan.files.map(file=><div key={file.path} className="mt-2 border-t border-stroke pt-2"><strong dir="ltr">{file.path}</strong><p className="text-secondary">{file.purpose}</p>{file.depends_on.length>0&&<p dir="ltr" className="text-xs text-secondary">{file.depends_on.join(' ← ')}</p>}</div>)}</details>
 </section>;
}
