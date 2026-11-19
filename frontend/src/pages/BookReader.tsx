import {useEffect,useRef,useState} from 'react';
import {Virtuoso,type VirtuosoHandle} from 'react-virtuoso';
import {ReadingSound} from './ReadingSound';
import type {PDFDocumentProxy} from 'pdfjs-dist';
import {ArrowRight,Bookmark,ChevronLeft,ChevronRight,Minus,Plus} from 'lucide-react';

export type ReadingEdition={id:string;title:string;format:'pdf'|'text';file?:File;driveId?:string};
type Progress={page:number;marks:number[]};
function saved(id:string):Progress{
 try{
  const value=JSON.parse(localStorage.getItem('barq-reader:'+id)||'null');
  return {page:Number.isInteger(value?.page)&&value.page>=1?value.page:1,marks:Array.isArray(value?.marks)?value.marks.filter(Number.isInteger):[]};
 }catch{return {page:1,marks:[]};}
}

function PdfPage({pdf,page,width,estimate,ar}:{pdf:PDFDocumentProxy;page:number;width:number;estimate:number;ar:boolean}){
 const canvas=useRef<HTMLCanvasElement>(null);
 const [ratio,setRatio]=useState<number>();
 const height=Math.max(1,Math.ceil(width*(ratio??estimate)));
 const [failed,setFailed]=useState(false);
 const [attempt,setAttempt]=useState(0);
 useEffect(()=>{
  if(!canvas.current||width<1)return;
  const surface=canvas.current,context=surface.getContext('2d');
  if(!context)return;
  let cancelled=false;
  let cancel:(()=>void)|undefined;
  void pdf.getPage(page).then(docPage=>{
   if(cancelled)return;
   const native=docPage.getViewport({scale:1});
   const pageRatio=native.height/native.width;
   setRatio(pageRatio);
   const renderHeight=width*pageRatio;
   const density=Math.min(window.devicePixelRatio||1,2,8192/Math.max(width,renderHeight),
    Math.sqrt(12_000_000/(width*renderHeight)));
   const view=docPage.getViewport({scale:width/native.width*density});
   surface.width=Math.ceil(view.width);
   surface.height=Math.ceil(view.height);
   const render=docPage.render({canvas:surface,canvasContext:context,viewport:view});
   cancel=()=>render.cancel();
   return render.promise;
  }).catch(()=>{if(!cancelled)setFailed(true);});
  return()=>{cancelled=true;cancel?.();};
 },[pdf,page,width,attempt]);

 return <div className="bs-pdf-page" style={{width,height}}><canvas ref={canvas} hidden={failed} aria-label={'PDF '+page}/>{failed&&
  <button type="button" onClick={()=>{setFailed(false);setAttempt(previous=>previous+1);}}>
   {ar?'إعادة تحميل الصفحة':'Reload page'} {page}
  </button>}</div>;
}
export default function BookReader({book,ar,onClose}:{book:ReadingEdition;ar:boolean;onClose:()=>void}){
 const [progress,setProgress]=useState(()=>saved(book.id));
 const [pdf,setPdf]=useState<PDFDocumentProxy>();
 const [text,setText]=useState<string[]>();
 const [error,setError]=useState<'source'|'pdf'|'password'>();
 const [retry,setRetry]=useState(0);
 const [zoom,setZoom]=useState(100);
 const [paper,setPaper]=useState<'default'|'warm'|'night'>('default');
 const [pageInput,setPageInput]=useState<string|null>(null);
 const viewport=useRef<VirtuosoHandle>(null);
 const content=useRef<HTMLDivElement>(null);
 const [width,setWidth]=useState(640);
 const [ratio,setRatio]=useState(1.414);
 const pdfWidth=Math.max(1,Math.floor((width-18)*zoom/100));
 const initialPage=useRef(progress.page);
 const savedPage=useRef(progress.page);
 const count=pdf?.numPages||text?.length||0;
 const page=Math.min(progress.page,count||1);

 useEffect(()=>{
  const element=content.current;
  if(!element)return;
  const observer=new ResizeObserver(([entry])=>setWidth(entry.contentRect.width));
  observer.observe(element);
  return()=>observer.disconnect();
 },[]);
 useEffect(()=>{
  const controller=new AbortController();
  let destroy:(()=>Promise<void>)|undefined;
  let stage:'source'|'pdf'='source';
  setPdf(undefined);setText(undefined);setError(undefined);
  void (async()=>{
   const driveUrl=book.driveId?'/v1/reading/drive/media/'+encodeURIComponent(book.driveId):undefined;
   const response=driveUrl?undefined:book.file||await fetch('/v1/reading/books/'+encodeURIComponent(book.id),{signal:controller.signal});
   if(response instanceof Response&&!response.ok)throw new Error('Edition unavailable');
   if(book.format==='text'){
    if(!response)throw new Error('Edition unavailable');
    const edition=(await response.text()).replace(/\r\n/g,'\n');
    if(!edition.trim()||edition.trimStart().startsWith('<'))throw new Error('Expected text edition');
    const parts=edition.match(/[\s\S]{1,6000}(?:\n|$)|[\s\S]{1,6000}/g)||[];
    if(!controller.signal.aborted)setText(parts);
    return;
   }
   stage='pdf';
   const [{GlobalWorkerOptions,getDocument},{default:workerUrl}]=await Promise.all([
    import('pdfjs-dist/legacy/build/pdf.mjs'),import('pdfjs-dist/legacy/build/pdf.worker.min.mjs?url'),
   ]);
   if(controller.signal.aborted)return;
   GlobalWorkerOptions.workerSrc=workerUrl;
   const assets='/assets/pdfjs/';
   // Use PDF glyph outlines so the browser cannot reshape joined Arabic glyphs.
   const input=driveUrl?{url:driveUrl,rangeChunkSize:256*1024}:{data:new Uint8Array(await response!.arrayBuffer())};
   if(controller.signal.aborted)return;
   const loading=getDocument({...input,isEvalSupported:false,disableFontFace:true,useSystemFonts:true,
    cMapUrl:assets+'cmaps/',cMapPacked:true,standardFontDataUrl:assets+'standard_fonts/',
    wasmUrl:assets+'wasm/',iccUrl:assets+'iccs/'});
   destroy=()=>loading.destroy();
   const result=await loading.promise;
   const first=(await result.getPage(1)).getViewport({scale:1});
   if(!controller.signal.aborted){setRatio(first.height/first.width);setPdf(result);}
  })().catch((failure:unknown)=>{
   if(!controller.signal.aborted)setError(failure instanceof Error&&failure.name==='PasswordException'?'password':stage);
  });
  return()=>{controller.abort();void destroy?.().catch(()=>{});};
 },[book,retry]);


 function notePage(index:number){
  const next=index+1;
  if(next===savedPage.current)return;
  savedPage.current=next;
  setProgress(previous=>({...previous,page:next}));
 }
 useEffect(()=>{
  try{localStorage.setItem('barq-reader:'+book.id,JSON.stringify(progress));}catch{/* The reader stays usable. */}
 },[book.id,progress]);
 function save(next:Progress){
  setProgress(next);
  savedPage.current=next.page;
 }
 function go(next:number){
  save({...progress,page:next});
  if(pdf&&viewport.current)viewport.current.scrollToIndex({index:next-1,align:'start'});
  else content.current?.scrollIntoView({block:'start'});
 }
 return <section className="bs-document" data-paper={paper} aria-label={book.title}>
  <header className="bs-document-toolbar">
   <div className="bs-document-heading">
    <button type="button" aria-label={ar?'رجوع للمكتبة':'Back to library'} title={ar?'رجوع للمكتبة':'Back to library'} onClick={onClose}><ArrowRight size={18}/></button>
    <h2 dir="auto" title={book.title}>{book.title}</h2>
    <ReadingSound ar={ar}/>
   </div>
   <div className="bs-document-actions">
   {count>0&&<div className="bs-document-controls">
    <button type="button" disabled={page<=1} aria-label={ar?'الصفحة السابقة':'Previous page'} onClick={()=>go(page-1)}><ChevronRight size={18}/></button>
    <form className="bs-page-jump" onSubmit={event=>{
     event.preventDefault();
     if(pageInput?.trim()){
      const target=Number(pageInput);
      if(Number.isInteger(target))go(Math.max(1,Math.min(count,target)));
     }
     setPageInput(null);
    }} dir="ltr">
     <input type="number" min={1} max={count} inputMode="numeric" aria-label={ar?'انتقل إلى صفحة':'Go to page'}
      value={pageInput??page} onFocus={event=>event.currentTarget.select()} onChange={event=>setPageInput(event.target.value)}
      onBlur={()=>setPageInput(null)}/>
     <span aria-live="off">/ {count}</span>
    </form>
    <button type="button" disabled={page>=count} aria-label={ar?'الصفحة التالية':'Next page'} onClick={()=>go(page+1)}><ChevronLeft size={18}/></button>
    <button type="button" aria-label={ar?'علّم الصفحة':'Bookmark page'} aria-pressed={progress.marks.includes(page)}
     onClick={()=>save({...progress,page,marks:progress.marks.includes(page)?progress.marks.filter(mark=>mark!==page):[...progress.marks,page]})}><Bookmark size={17}/></button>
    {!!progress.marks.length&&<select aria-label={ar?'الصفحات المعلّمة':'Bookmarked pages'} value="" onChange={event=>go(Number(event.target.value))}>
     <option value="" disabled>{ar?'العلامات':'Bookmarks'}</option>{progress.marks.filter(mark=>mark>0&&mark<=count).sort((a,b)=>a-b).map(mark=><option key={mark} value={mark}>{mark}</option>)}</select>}
   </div>}
   {count>0&&<div className="bs-reader-display">
    <button type="button" aria-label={ar?'تصغير القراءة':'Zoom out'} disabled={zoom<=80} onClick={()=>setZoom(zoom-20)}><Minus size={15}/></button>
    <button type="button" className="bs-zoom-level" aria-label={ar?'إعادة حجم القراءة':'Reset zoom'} onClick={()=>setZoom(100)}>{zoom}%</button>
    <button type="button" aria-label={ar?'تكبير القراءة':'Zoom in'} disabled={zoom>=160} onClick={()=>setZoom(zoom+20)}><Plus size={15}/></button>
    <select aria-label={ar?'ألوان القراءة':'Reading colors'} value={paper} onChange={event=>setPaper(event.target.value as typeof paper)}>
     <option value="default">{ar?'عادي':'Default'}</option>
     <option value="warm">{ar?'ورق دافئ':'Warm paper'}</option>
     <option value="night">{ar?'ليلي':'Night'}</option>
    </select>
   </div>}
   </div>
   {count>0&&<progress className="bs-reader-progress" value={page} max={count} aria-label={ar?'تقدّم القراءة':'Reading progress'}/>}
  </header>
  <div className="bs-document-content" ref={content}>
   {error?<div className="bs-reader-error" role="alert">
    <p>{error==='password'?(ar?'ملف الـPDF محمي بكلمة سر.':'This PDF is password-protected.'):
     error==='pdf'?(ar?'تعذّر قراءة ملف الـPDF. افتح نسخة سليمة أو جرّب تاني.':'Could not read the PDF. Open another copy or retry.'):
      (ar?'تعذّر تحميل الكتاب من المصدر. جرّب تاني بعد رجوع الاتصال.':'The book source is unavailable. Retry when connected.')}</p>
    <button type="button" onClick={()=>setRetry(x=>x+1)}>{ar?'إعادة المحاولة':'Retry'}</button></div>:
    pdf?<Virtuoso className="bs-pdf-scroll" ref={viewport} dir="ltr" tabIndex={0}
     aria-label={ar?'صفحات الكتاب':'Book pages'} totalCount={pdf.numPages}
     initialTopMostItemIndex={Math.min(initialPage.current,pdf.numPages)-1}
     defaultItemHeight={Math.ceil(pdfWidth*ratio)+12}
     rangeChanged={({startIndex})=>notePage(startIndex)}
     itemContent={index=><div className="bs-pdf-item" style={index===pdf.numPages-1?{minHeight:'var(--pdf-viewport)'}:undefined}>
      <PdfPage pdf={pdf} page={index+1} width={pdfWidth} estimate={ratio} ar={ar}/>
     </div>}/>:text?<article dir="auto" style={{fontSize:`${1.05*zoom/100}rem`}}>{text[page-1]}</article>:
     <p role="status">{ar?'جاري تحميل الكتاب…':'Loading book…'}</p>}
  </div>
 </section>;
}
