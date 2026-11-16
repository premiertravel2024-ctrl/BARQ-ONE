import {useEffect,useMemo,useState} from 'react';
import {ExternalLink,Monitor,RefreshCcw,Smartphone,Tablet} from 'lucide-react';
import {Button} from '../ui/Button';

type Device='desktop'|'tablet'|'mobile';

function buildPreviewDoc(path:string, content:string){
 const lower=(path||'').toLowerCase();
 const trimmed=(content||'').trim();
 const looksHtml=/<html[\s>]|<!doctype html>|<body[\s>]|<head[\s>]|<style[\s>]|<div[\s>]|<form[\s>]/i.test(trimmed);
 if(!trimmed) return {supported:false,doc:'',reason:'مفيش محتوى للمعاينة دلوقتي.'};
 if(lower.endsWith('.html')||looksHtml){
  const doc=/<html[\s>]|<!doctype html>/i.test(trimmed)
   ? trimmed
   : `<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/></head><body>${trimmed}</body></html>`;
  return {supported:true,doc,reason:''};
 }
 if(lower.endsWith('.css')){
  const doc=`<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/><style>
  body{margin:0;background:#f4f4f4;font-family:Arial,sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;padding:24px;box-sizing:border-box}
  ${trimmed}
  </style></head><body><main class="barq-preview-sample"><div class="card"><h1>معاينة CSS</h1><p>ده مثال مباشر علشان تشوف تأثير التنسيقات.</p><button>زر تجريبي</button></div></main></body></html>`;
  return {supported:true,doc,reason:''};
 }
 if(lower.endsWith('.md')){
  const escaped=trimmed.replace(/[&<>]/g,s=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[s]||s));
  const doc=`<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/><style>body{font-family:Arial,sans-serif;background:#0f1115;color:#f2f4f8;padding:24px}pre{white-space:pre-wrap;line-height:1.8;background:#15181e;padding:18px;border-radius:12px;border:1px solid rgba(255,255,255,.08)}</style></head><body><pre>${escaped}</pre></body></html>`;
  return {supported:true,doc,reason:''};
 }
 return {supported:false,doc:'',reason:'المعاينة المباشرة متاحة حاليًا بشكل أفضل لملفات HTML/CSS والمخرجات البصرية الشبيهة بها. لملفات TSX/JSX تقدر تراجع الكود ثم تشغّله من المشروع.'};
}

export function PreviewPanel({path,content,title='المعاينة الحية'}:{path:string;content:string;title?:string}){
 const [key,setKey]=useState(0);
 const [device,setDevice]=useState<Device>('desktop');
 const [serverDraft,setServerDraft]=useState('http://127.0.0.1:5173');
 const [serverUrl,setServerUrl]=useState('');
 const serverValid=/^http:\/\/(?:127\.0\.0\.1|localhost)(?::[0-9]{2,5})?(?:\/[^\s]*)?$/i.test(serverDraft) && (()=>{try{return new URL(serverDraft).origin!==window.location.origin}catch{return false}})();
 const showServer=Boolean(serverUrl);
 useEffect(()=>{setKey(v=>v+1)},[path,content]);
 const preview=useMemo(()=>buildPreviewDoc(path,content),[path,content]);
 const widths:Record<Device,string>={desktop:'100%',tablet:'820px',mobile:'390px'};
 const openExternal=()=>{
  if(showServer){window.open(serverUrl,'_blank','noopener,noreferrer');return;}
  if(!preview.supported) return;
  const blob=new Blob([preview.doc],{type:'text/html'});
  const url=URL.createObjectURL(blob);
  window.open(url,'_blank','noopener,noreferrer');
  window.setTimeout(()=>URL.revokeObjectURL(url),60_000);
 };
 return <section className="studio-preview" dir="rtl" aria-label="المعاينة الحية">
   <header className="studio-preview-header">
     <div className="flex min-w-0 items-center gap-2"><strong>{title}</strong>{path&&<span className="studio-preview-path" dir="ltr">{path}</span>}</div>
     <div className="flex flex-wrap items-center gap-2">
       <div className="studio-preview-devices">
         <button type="button" className={device==='desktop'?'active':''} onClick={()=>setDevice('desktop')} title="Desktop"><Monitor size={14}/></button>
         <button type="button" className={device==='tablet'?'active':''} onClick={()=>setDevice('tablet')} title="Tablet"><Tablet size={14}/></button>
         <button type="button" className={device==='mobile'?'active':''} onClick={()=>setDevice('mobile')} title="Mobile"><Smartphone size={14}/></button>
       </div>
       <button type="button" className="studio-icon" onClick={()=>setKey(v=>v+1)} title="تحديث المعاينة"><RefreshCcw size={15}/></button>
       <Button size="sm" variant="secondary" disabled={!preview.supported&&!showServer} icon={<ExternalLink size={14}/>} onClick={openExternal}>فتح لوحدها</Button>
     </div>
   </header>
   <form className="studio-preview-server" onSubmit={e=>{e.preventDefault();if(serverValid){setServerUrl(serverDraft);setKey(v=>v+1)}}}>
     <span>مشروع React/Vite شغال محليًا؟</span>
     <input dir="ltr" aria-label="عنوان خادم المعاينة المحلي" value={serverDraft} onChange={e=>setServerDraft(e.target.value)} placeholder="http://127.0.0.1:5173" />
     <button type="submit" disabled={!serverValid}>عرض المشروع</button>{showServer&&<button type="button" onClick={()=>setServerUrl('')}>العودة لمعاينة الملف</button>}
   </form>
   {!preview.supported&&!showServer ? (
    <div className="studio-preview-empty"><Monitor size={28}/><p>{preview.reason}</p></div>
   ) : (
    <div className="studio-preview-stage"><div className={`studio-preview-frame-wrap ${device}`} style={{width:widths[device]}}>{showServer?<iframe key={key} title="معاينة مشروع محلي" className="studio-preview-frame" sandbox="allow-scripts allow-forms allow-modals allow-same-origin" src={serverUrl}/>:<iframe key={key} title="BARQ preview" className="studio-preview-frame" sandbox="allow-scripts allow-forms allow-modals" srcDoc={preview.doc}/>}</div></div>
   )}
  </section>;
}
