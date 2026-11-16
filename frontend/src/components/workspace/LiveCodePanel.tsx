import {useEffect,useMemo,useRef,useState} from 'react';
import {Check,Clipboard,Code2,FileDiff,LoaderCircle,ShieldCheck} from 'lucide-react';
import {generatedBlocks} from '../../lib/studioStream';
import {Button} from '../ui/Button';

type Props={answer:string;streaming:boolean;proposed?:{path:string;content:string}|null;target:string;onTarget:(next:string)=>void;onReview:(content:string,path:string)=>void;onPreview:(content:string,path:string)=>void;onOpenEditor:()=>void;onStop:()=>void};
export function LiveCodePanel({answer,streaming,proposed,target,onTarget,onReview,onPreview,onOpenEditor,onStop}:Props){
 const blocks=useMemo(()=>generatedBlocks(answer),[answer]);const [selected,setSelected]=useState(0);
 const block=blocks[Math.min(selected,blocks.length-1)];const code=proposed?.content||block?.content||'';
 const scrollRef=useRef<HTMLDivElement>(null);
 useEffect(()=>{if(streaming&&scrollRef.current){const el=scrollRef.current;el.scrollTop=el.scrollHeight}},[code,streaming]);
 const targetPath=proposed?.path||target||block?.filename||'';
 return <section className="studio-live-code" dir="rtl" aria-label="الكود الجاري توليده">
  <header className="studio-live-header"><div className="flex items-center gap-2"><Code2 size={18} className="text-accent"/><strong>{proposed?'الكود المقترح من خطة برق':'برق بيكتب الكود'}</strong><span className={`studio-live-state ${streaming?'running':'ready'}`}>{streaming?<><LoaderCircle size={13} className="animate-spin"/> بيتكتب دلوقتي</>:<><Check size={13}/> {proposed?'بانتظار الموافقة':blocks.length?'جاهز للمراجعة':'في انتظار كود'}</>}</span></div>
    <div className="flex gap-1"><button type="button" className="studio-icon" onClick={onOpenEditor} title="الرجوع للمحرر">المحرر</button>{streaming&&<button type="button" className="studio-icon" onClick={onStop} title="إيقاف التوليد">إيقاف</button>}</div></header>
  {!proposed&&blocks.length>1&&<nav className="studio-generated-files" aria-label="الملفات المقترحة">{blocks.map((item,i)=><button key={i} className={selected===i?'active':''} onClick={()=>setSelected(i)} dir="ltr">{item.filename||`Code ${i+1}`}</button>)}</nav>}
  <div className="studio-live-filebar"><label htmlFor="barq-code-target">الملف المستهدف</label><input id="barq-code-target" dir="ltr" value={proposed?.path||target} readOnly={!!proposed} placeholder={block?.filename||'src/components/example.tsx'} onChange={e=>onTarget(e.target.value)} aria-label="مسار الملف المقترح داخل المشروع"/><span dir="ltr">{proposed?.path.split('.').at(-1)||block?.language||'code'}</span></div>
  <div ref={scrollRef} className="studio-live-canvas" dir="ltr">
    {code?<pre data-testid="live-code" aria-live="off"><code>{code}</code>{streaming&&!proposed&&!block?.complete&&<span className="studio-stream-caret" aria-hidden="true"/>}</pre>:
     <div dir="rtl" className="studio-live-placeholder"><Code2 size={30}/><p>{streaming?'برق بيجهز الرد... أول ما يبدأ يولّد الكود هيظهر هنا فورًا.':'اطلب من برق في الشات الأساسي إنشاء أو تعديل البرنامج؛ الكود الحقيقي هيظهر هنا عند تجهيزه.'}</p></div>}
  </div>
  <footer className="studio-live-actions"><span className="studio-live-note"><ShieldCheck size={15}/> {proposed?'دي مسودة حقيقية من خطة برق؛ وافق على الخطوة من الشات الأساسي.':'معاينة فقط — مفيش كتابة على ملفات المشروع من غير موافقتك.'}</span>
    <div className="flex flex-wrap gap-2"><Button size="sm" variant="secondary" disabled={!code} onClick={()=>void navigator.clipboard.writeText(code)} icon={<Clipboard size={14}/>}>نسخ</Button><Button size="sm" variant="secondary" disabled={!code||!targetPath.trim()} onClick={()=>onPreview(code,targetPath)} icon={<Code2 size={14}/>}>شوف الشكل</Button><Button size="sm" variant="primary" disabled={!code||streaming||!!proposed||!targetPath.trim()} onClick={()=>onReview(code,targetPath)} icon={<FileDiff size={14}/>}>مراجعة التعديل</Button></div>
  </footer>
 </section>;
}
