import {useEffect,useState} from 'react';
import {X} from 'lucide-react';

type VoiceCard={label:string;kind?:string;description?:string;extension?:string;url?:string};
/** Local ephemeral search results. Do NOT put file names/chat excerpts into
 * persisted messages or Gemini Live's initial history. No floating voice HUD.
 */
export function VoiceResultsStrip(){
 const [cards,setCards]=useState<VoiceCard[]>([]);
 useEffect(()=>{
  const handler=(event:Event)=>{
   const detail=(event as CustomEvent<{cards?:VoiceCard[]}>).detail;
   const next=Array.isArray(detail?.cards)?detail.cards:[];
   setCards(next.filter(c=>c&&typeof c.label==='string').slice(0,10));
  };
  const clear=()=>setCards([]);
  const onState=(e:Event)=>{if((e as CustomEvent<{active:boolean}>).detail?.active===false)clear()};
  window.addEventListener('barq-voice-local-cards',handler);
  window.addEventListener('barq-handsfree-stop',clear);
  window.addEventListener('barq-handsfree-state',onState);
  return ()=>{window.removeEventListener('barq-voice-local-cards',handler);window.removeEventListener('barq-handsfree-stop',clear);window.removeEventListener('barq-handsfree-state',onState)};
 },[]);
 if(!cards.length)return null;
 return <section className="mx-auto mb-2 w-[min(92%,860px)] rounded-xl border border-stroke bg-elevated/90 p-3 text-xs" aria-label="نتائج بحث برق الصوتي" dir="rtl">
  <div className="mb-2 flex items-center justify-between gap-2"><strong>نتائج بحث برق الصوتي — محلية داخل البرنامج</strong><button type="button" className="rounded p-1 text-secondary hover:text-primary" onClick={()=>setCards([])} aria-label="إغلاق نتائج الصوت"><X size={15}/></button></div>
  <div className="flex max-h-32 flex-col gap-1 overflow-y-auto">{cards.map((item,i)=><div key={`${i}-${item.label}`} className="flex gap-2 rounded-md border border-stroke/50 px-2 py-1"><span className="tabular-nums text-secondary">{i+1}.</span><span className="min-w-0 break-words">{item.label}</span>{item.extension&&<span className="text-muted">{item.extension}</span>}</div>)}</div>
  <p className="mt-2 text-secondary">قول «افتح التاني» أو «اقرأ الأول». أي فتح يحتاج صلاحيات برق المعتادة.</p>
 </section>;
}
