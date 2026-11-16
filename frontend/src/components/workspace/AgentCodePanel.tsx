import {useEffect,useRef} from 'react';
import {Button} from '../ui/Button';
export type LiveDraft={id:string;attempt:number;workspace:string;status:'waiting'|'streaming'|'ready'|'interrupted';model:string;path:string;code:string;partial_edit:boolean;validated:boolean};

export function AgentCodePanel({draft,onReview,onStop,canReview}:{draft:LiveDraft;onReview:()=>void;onStop:()=>void;canReview:boolean}){
 const scroll=useRef<HTMLDivElement>(null);
 useEffect(()=>{if(draft.status==='streaming'&&scroll.current)scroll.current.scrollTop=scroll.current.scrollHeight},[draft.code,draft.status]);
 return <section className="studio-live-code" dir="rtl" aria-label="كود مهمة برق المباشر">
  <header className="studio-live-header"><strong>{draft.status==='streaming'?'برق بيولّد التعديل دلوقتي':draft.status==='ready'?'التعديل جاهز للمراجعة':draft.status==='interrupted'?'التوليد اتوقف؛ المسودة غير معتمدة':'جاري تجهيز الخطوة التالية'}</strong><span dir="ltr">{draft.model}</span></header>
  <div className="studio-live-filebar"><span dir="ltr">{draft.path||'في انتظار تحديد الملف'}</span><span>{draft.partial_edit?'جزء مقترح للاستبدال داخل الملف':'محتوى ملف مقترح'}</span></div>
  <div className="studio-live-canvas" ref={scroll} dir="ltr"><pre data-testid="agent-live-code"><code>{draft.code}</code></pre>{!draft.code&&<p dir="rtl">الكود هيظهر هنا أول ما النموذج يرسله. الملفات لسه ما اتغيرتش.</p>}</div>
  <footer className="studio-live-actions"><span className="studio-live-note">مسودة من النموذج — التنفيذ والحفظ بعد مراجعتك وموافقتك.</span><div className="flex gap-2">{draft.status==='streaming'&&<Button size="sm" variant="secondary" onClick={onStop}>إيقاف التوليد</Button>}<Button size="sm" variant="primary" disabled={!draft.validated||!canReview} onClick={onReview}>مراجعة الخطوة الحالية</Button></div></footer>
 </section>;
}
