import {useCallback,useEffect,useLayoutEffect,useRef,useState} from 'react';
import type {PDFDocumentProxy} from 'pdfjs-dist';
import {ArrowRight,Bookmark,ChevronLeft,ChevronRight} from 'lucide-react';

export type ReadingEdition={id:string;title:string;format:'pdf'|'text';file?:File};
type Progress={page:number;marks:number[]};
function saved(id:string):Progress{
 try{
  const value=JSON.parse(localStorage.getItem('barq-reader:'+id)||'null');
  return {page:Number.isInteger(value?.page)&&value.page>=1?value.page:1,marks:Array.isArray(value?.marks)?value.marks.filter(Number.isInteger):[]};
 }catch{return {page:1,marks:[]};}
}

function PdfPage({pdf,page,width,height,onError}:{pdf:PDFDocumentProxy;page:number;width:number;height:number;onError:()=>void}){
 const canvas=useRef<HTMLCanvasElement>(null);
 useEffect(()=>{
  if(!canvas.current||width<1)return;
  const surface=canvas.current,context=surface.getContext('2d');
  if(!context)return;
  let cancelled=false;
  let cancel:(()=>void)|undefined;
  void pdf.getPage(page).then(docPage=>{
   if(cancelled)return;
   const native=docPage.getViewport({scale:1});
   const density=Math.min(window.devicePixelRatio||1,2);
   const view=docPage.getViewport({scale:Math.min(width/native.width,height/native.height)*density});
   surface.width=Math.ceil(view.width);
   surface.height=Math.ceil(view.height);
   const render=docPage.render({canvas:surface,canvasContext:context,viewport:view});
   cancel=()=>render.cancel();
   return render.promise;
  }).catch(()=>{if(!cancelled)onError();});
  return()=>{cancelled=true;cancel?.();};
 },[pdf,page,width,height,onError]);

 return <canvas ref={canvas} aria-label={'PDF '+page}/>;
}
export default function BookReader({book,ar,onClose}:{book:ReadingEdition;ar:boolean;onClose:()=>void}){
 const [progress,setProgress]=useState(()=>saved(book.id));
 const [pdf,setPdf]=useState<PDFDocumentProxy>();
 const [text,setText]=useState<string[]>();
 const [error,setError]=useState(false);
 const [retry,setRetry]=useState(0);
 const viewport=useRef<HTMLDivElement>(null);
 const content=useRef<HTMLDivElement>(null);
 const [width,setWidth]=useState(640);
 const [ratio,setRatio]=useState(1.414);
 const pdfWidth=Math.min(width,900);
 const pdfHeight=Math.ceil(pdfWidth*ratio);
 const pageStride=pdfHeight+12;
 const failRender=useCallback(()=>setError(true),[]);
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
  setPdf(undefined);setText(undefined);setError(false);
  void (async()=>{
   const response=book.file||await fetch('/v1/reading/books/'+encodeURIComponent(book.id),{signal:controller.signal});
   if(response instanceof Response&&!response.ok)throw new Error('Edition unavailable');
   if(book.format==='text'){
    const edition=await response.text();
    const parts=edition.match(/[\s\S]{1,6000}(?:\n|$)|[\s\S]{1,6000}/g)||[];
    if(!controller.signal.aborted)setText(parts);
    return;
   }
   const data=new Uint8Array(await response.arrayBuffer());
   const [{GlobalWorkerOptions,getDocument},{default:workerUrl}]=await Promise.all([
    import('pdfjs-dist'),import('pdfjs-dist/build/pdf.worker.min.mjs?url'),
   ]);
   if(controller.signal.aborted)return;
   GlobalWorkerOptions.workerSrc=workerUrl;
   const assets='/assets/pdfjs/';
   const loading=getDocument({data,isEvalSupported:false,useSystemFonts:true,
    cMapUrl:assets+'cmaps/',cMapPacked:true,standardFontDataUrl:assets+'standard_fonts/',
    wasmUrl:assets+'wasm/',iccUrl:assets+'iccs/'});
   destroy=()=>loading.destroy();
   const result=await loading.promise;
   const first=(await result.getPage(1)).getViewport({scale:1});
   if(!controller.signal.aborted){setRatio(first.height/first.width);setPdf(result);}
  })().catch(()=>{if(!controller.signal.aborted)setError(true);});
  return()=>{controller.abort();void destroy?.().catch(()=>{});};
 },[book,retry]);


 useLayoutEffect(()=>{
  if(pdf&&viewport.current)viewport.current.scrollTop=(Math.min(savedPage.current,pdf.numPages)-1)*pageStride;
 },[pdf,pageStride]);

 function notePage(){
  if(!viewport.current||!pdf)return;
  const next=Math.min(pdf.numPages,Math.floor((viewport.current.scrollTop+Math.min(45,viewport.current.clientHeight/4))/pageStride)+1);
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
  if(pdf&&viewport.current)viewport.current.scrollTop=(next-1)*pageStride;
  else content.current?.scrollIntoView({block:'start'});
 }
 return <section className="bs-document" aria-label={book.title}>
  <header className="bs-document-toolbar">
   <button type="button" onClick={onClose}><ArrowRight size={16}/>{ar?'رجوع للمكتبة':'Back to library'}</button>
   <h2 dir="auto">{book.title}</h2>
   {count>0&&<div className="bs-document-controls">
    <button type="button" disabled={page<=1} aria-label={ar?'الصفحة السابقة':'Previous page'} onClick={()=>go(page-1)}><ChevronRight size={18}/></button>
    <span dir="ltr">{page} / {count}</span>
    <button type="button" disabled={page>=count} aria-label={ar?'الصفحة التالية':'Next page'} onClick={()=>go(page+1)}><ChevronLeft size={18}/></button>
    <button type="button" aria-label={ar?'علّم الصفحة':'Bookmark page'} aria-pressed={progress.marks.includes(page)}
     onClick={()=>save({...progress,page,marks:progress.marks.includes(page)?progress.marks.filter(mark=>mark!==page):[...progress.marks,page]})}><Bookmark size={17}/></button>
    {!!progress.marks.length&&<select aria-label={ar?'الصفحات المعلّمة':'Bookmarked pages'} value="" onChange={event=>go(Number(event.target.value))}>
     <option value="" disabled>{ar?'العلامات':'Bookmarks'}</option>{progress.marks.filter(mark=>mark>0&&mark<=count).sort((a,b)=>a-b).map(mark=><option key={mark} value={mark}>{mark}</option>)}</select>}
   </div>}
  </header>
  <div className="bs-document-content" ref={content}>
   {error?<div role="alert">{ar?'تعذّر فتح النسخة. جرّب تاني.':'Could not open this edition.'} <button type="button" onClick={()=>setRetry(x=>x+1)}>{ar?'إعادة المحاولة':'Retry'}</button></div>:
    pdf?<div className="bs-pdf-scroll" ref={viewport} onScroll={notePage} tabIndex={0} aria-label={ar?'صفحات الكتاب':'Book pages'}>
     {Array.from({length:pdf.numPages},(_,index)=>{
      const number=index+1;
      return <div className="bs-pdf-page" key={number} style={{width:pdfWidth,height:pdfHeight}}>
       {Math.abs(number-page)<=2&&<PdfPage pdf={pdf} page={number} width={pdfWidth} height={pdfHeight} onError={failRender}/>}
      </div>;
     })}
     <div aria-hidden="true" style={{height:'max(0px, calc(var(--pdf-viewport) - '+pdfHeight+'px))'}}/>
    </div>:text?<article dir="auto">{text[page-1]}</article>:
     <p role="status">{ar?'جاري تحميل الكتاب…':'Loading book…'}</p>}
  </div>
 </section>;
}
