/** Replace only this service module to use the real AI Router FastAPI backend. */
import type {ChatOptions,Message,UploadedAttachment} from '../store';
export type AIRequest={messages:Message[];model:string;options:ChatOptions;attachments?:UploadedAttachment[];signal:AbortSignal};
export type AIEvent={type:'thinking'|'reasoning'|'token'|'done';value:string};
const delay=(ms:number,signal:AbortSignal)=>new Promise<void>((resolve,reject)=>{
  if(signal.aborted){reject(new DOMException('Aborted','AbortError'));return}
  const timer=setTimeout(()=>{signal.removeEventListener('abort',onAbort);resolve()},ms);
  const onAbort=()=>{clearTimeout(timer);reject(new DOMException('Aborted','AbortError'))};
  signal.addEventListener('abort',onAbort,{once:true});
});
function answer(prompt:string,model:string):string{
  const arabic=/[\u0600-\u06FF]/.test(prompt);
  const coding=/\b(react|python|code|function|bug|component|app|program|typescript|debug)\b/i.test(prompt)||/كود|برمج|تطبيق|خطأ|مشكلة/.test(prompt);
  if(coding){return arabic?`أكيد. خلّينا ننظّم المهمة أولًا، وبعدها ننفّذها خطوة بخطوة.\n\n### خطة التنفيذ\n1. نفهم بنية المشروع ومتطلباته.\n2. نقسم الشغل لمكونات صغيرة وقابلة للاختبار.\n3. نكتب كود واضح ونراجع الأخطاء.\n\nمثال بسيط في TypeScript:\n\n\`\`\`typescript\ntype Result<T> = { data: T; success: boolean };\n\nexport function createResult<T>(data: T): Result<T> {\n  return { data, success: true };\n}\n\`\`\`\n\n> **ملاحظة:** دي معاينة لواجهة المحادثة ببيانات تجريبية. التنفيذ الحقيقي للأوامر يحتاج توصيل المحرك الخلفي.`:`Great. Here's a clean approach to the task.\n\n### Implementation plan\n1. Identify the existing modules and data flow.\n2. Make a focused, reviewable change.\n3. Add automated tests and validate edge cases.\n\n\`\`\`typescript\ninterface Result<T> {\n  success: boolean;\n  value: T;\n}\n\nexport function ok<T>(value: T): Result<T> {\n  return { success: true, value };\n}\n\`\`\`\n\n**Next step:** share the project details to make this solution specific.\n\n*Demo response from ${model==='auto'?'Auto':model}. No real model or tool has been called.*`}
  return arabic?`أهلًا بيك! \n\nأنا مساعدك داخل **BARQ**. تقدر تستخدم الواجهة للمحادثات، رفع الملفات، واختيار النموذج المناسب.\n\n- اختيار تلقائي أو يدوي للنموذج\n- عرض أكواد وجداول وملفات\n- إعدادات قابلة للتخصيص\n\n**تنبيه:** الرد الحالي تجريبي لعرض تجربة الاستخدام، ومش ناتج عن استدعاء نموذج حقيقي.`:`Absolutely — I'm here to help you think, write, and build with clarity.\n\nThis interface supports:\n- **Multi-model selection**, including automatic routing\n- Code blocks, tables and Markdown\n- Attachments, keyboard shortcuts and long conversations\n\n> This is a **simulated response** for interface development. No provider has been called.`;
}
export const aiService={
  async *stream({messages,model,signal}:AIRequest):AsyncGenerator<AIEvent>{
    const last=messages.filter(m=>m.role==='user').at(-1)?.content||'';
    yield {type:'thinking',value:''};
    await delay(380,signal);
    yield {type:'reasoning',value:'Preparing a structured answer…'};
    await delay(180,signal);
    const body=answer(last,model);
    const pieces=body.match(/\S+\s*/g)??[body];
    for(const piece of pieces){await delay(Math.max(13,Math.min(48,piece.length*2)),signal);yield {type:'token',value:piece}}
    yield {type:'done',value:''};
  }
};
