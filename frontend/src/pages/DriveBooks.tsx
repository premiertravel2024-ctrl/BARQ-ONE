import {EditableCover} from './EditableCover';
import {useEffect,useRef,useState,type ChangeEvent} from 'react';
import {BookOpen,FolderOpen} from 'lucide-react';
import type {ReadingEdition} from './BookReader';
import {Modal} from '../components/ui/Modal';
import {ArrowLeft,Settings2,Layers} from 'lucide-react';

export type DriveBook={edition:ReadingEdition;cover?:File;coverId?:string;group:string;issueNumber?:number;sortPosition?:number;seriesId?:string;manualSeries?:boolean;reviewReason?:string};
let pickedBooks:DriveBook[]|undefined;
export function pickedDriveBooks(){return pickedBooks;}

const maxPdf=64*1024*1024;

export function scanDriveFolder(files:File[]):DriveBook[]{
 const images=new Map(files.filter(file=>/\.(png|jpe?g|webp)$/i.test(file.name))
  .map(file=>[file.webkitRelativePath.toLowerCase(),file]));
 const books=files.filter(file=>/\.pdf$/i.test(file.name)&&file.size>0&&file.size<=maxPdf);
 const folderCounts=new Map<string,number>();
 for(const file of books){
  const folder=file.webkitRelativePath.slice(0,-file.name.length);
  folderCounts.set(folder,(folderCounts.get(folder)||0)+1);
 }
 return books.map<DriveBook>(file=>{
  const path=file.webkitRelativePath;
  const folder=path.slice(0,-file.name.length);
  const title=file.name.replace(/\.pdf$/i,'');
  const imageNames=['jpg','jpeg','png','webp'].map(ext=>title+'.'+ext);
  if(folderCounts.get(folder)===1)imageNames.push('cover.jpg','cover.jpeg','cover.png','cover.webp');
  return {
   edition:{id:'drive:'+path,title,format:'pdf',file},
   cover:imageNames.map(name=>images.get((folder+name).toLowerCase())).find(Boolean),
   group:folder.split('/').slice(1,-1).join(' / '),
  };
 }).sort((a,b)=>a.edition.title.localeCompare(b.edition.title,undefined,{numeric:true}));
}

function DriveCover({book}:{book:DriveBook}){
 const {cover,coverId,edition}=book;
 const [src,setSrc]=useState('');
 const frame=useRef<HTMLDivElement>(null);
 useEffect(()=>{
  if(coverId){
   setSrc('/v1/reading/drive/media/'+encodeURIComponent(coverId));
   return;
  }
  if(cover){
   const url=URL.createObjectURL(cover);
   setSrc(url);
   return()=>URL.revokeObjectURL(url);
  }
  setSrc('');
  const element=frame.current;
  if(!element||!edition.file)return;
  const file=edition.file;
  let cancelled=false;
  let destroy:(()=>Promise<void>)|undefined;
  const observer=new IntersectionObserver(entries=>{
   if(cancelled||!entries.some(entry=>entry.isIntersecting))return;
   observer.disconnect();
   void (async()=>{
    const [{GlobalWorkerOptions,getDocument},{default:workerUrl},data]=await Promise.all([
     import('pdfjs-dist/legacy/build/pdf.mjs'),import('pdfjs-dist/legacy/build/pdf.worker.min.mjs?url'),file.arrayBuffer(),
    ]);
    if(cancelled)return;
    GlobalWorkerOptions.workerSrc=workerUrl;
    const task=getDocument({data:new Uint8Array(data),isEvalSupported:false,disableFontFace:true,useSystemFonts:true,
     cMapUrl:'/assets/pdfjs/cmaps/',cMapPacked:true,standardFontDataUrl:'/assets/pdfjs/standard_fonts/'});
    destroy=()=>task.destroy();
    const pdf=await task.promise;
    const page=await pdf.getPage(1);
    const viewport=page.getViewport({scale:180/Math.max(1,page.getViewport({scale:1}).width)});
    const canvas=document.createElement('canvas');
    canvas.width=Math.ceil(viewport.width);
    canvas.height=Math.ceil(viewport.height);
    const canvasContext=canvas.getContext('2d');
    if(!canvasContext)return;
    await page.render({canvas,canvasContext,viewport}).promise;
    if(!cancelled)setSrc(canvas.toDataURL('image/jpeg',.8));
   })().catch(()=>{}).finally(()=>{const cleanup=destroy;destroy=undefined;void cleanup?.().catch(()=>{});});
  });
  observer.observe(element);
  return ()=>{
   cancelled=true;
   observer.disconnect();
   const cleanup=destroy;destroy=undefined;void cleanup?.().catch(()=>{});
  };
 },[cover,coverId,edition.file,edition.driveId]);
 return <div className="bs-real-cover" aria-hidden="true" ref={frame}>
  {src?<img src={src} alt="" onError={()=>setSrc('')}/>:<><BookOpen size={24}/><strong>{edition.title}</strong></>}
 </div>;
}

export function DriveFolderButton({ar,onSelect}:{ar:boolean;onSelect?:(books:DriveBook[])=>void}){
 const picker=useRef<HTMLInputElement|null>(null);
 function choose(event:ChangeEvent<HTMLInputElement>){
  const files=Array.from(event.currentTarget.files||[]);
  event.currentTarget.value='';
  if(files.length){pickedBooks=scanDriveFolder(files);onSelect?.(pickedBooks);}
 }
 return <>
  <input hidden type="file" multiple ref={element=>{picker.current=element;element?.setAttribute('webkitdirectory','');}} onChange={choose}/>
  <button className="bs-muted-btn" type="button" onClick={()=>picker.current?.click()}
   title={ar?'اختار فولدر المكتبة من Google Drive for desktop':'Choose the library folder from Google Drive for desktop'}>
   <FolderOpen size={16}/>{ar?'فولدر Google Drive':'Google Drive folder'}</button>
 </>;
}

export function DriveBooks({books,ar,onOpen,heading=true,collectionLabel}:{
 books:DriveBook[];ar:boolean;onOpen:(edition:ReadingEdition)=>void;heading?:boolean;collectionLabel?:string;
}){
 const [selectedGroup,setSelectedGroup]=useState<string>();
 const groups=new Map<string,DriveBook[]>();
 const singles:DriveBook[]=[];
 const sortBooks=(a:DriveBook,b:DriveBook)=>(a.sortPosition??0)-(b.sortPosition??0)||
  (a.issueNumber??Infinity)-(b.issueNumber??Infinity)||
  a.edition.title.localeCompare(b.edition.title,undefined,{numeric:true});
 for(const book of books){
  const key=book.seriesId||(book.manualSeries?'':book.group);
  if(key)groups.set(key,[...(groups.get(key)||[]),book]);
  else singles.push(book);
 }
 const collected:Array<{key:string;title:string;items:DriveBook[];seriesId?:string}>=[];
 for(const [key,items] of groups) {
  if(items.length===1&&!items[0].seriesId)singles.push(items[0]);
  else collected.push({key,title:items[0].group.split(' / ').slice(-1)[0]||items[0].group,items:[...items].sort(sortBooks),seriesId:items[0].seriesId});
 }
 const current=collected.find(group=>group.key===selectedGroup);
 function bookCard(item:DriveBook){
  return <article className="bs-real-card bs-published-card" key={item.edition.id}>
   <EditableCover id={item.edition.id} title={item.edition.title} ar={ar}><DriveCover book={item}/></EditableCover>
   <div className="bs-real-copy">
    {item.issueNumber&&<span>{ar?'العدد':'Issue'} {item.issueNumber}</span>}
    <h3 dir="auto">{item.edition.title}</h3>
    <button className="bs-series-open" type="button" onClick={()=>onOpen(item.edition)}>
     {ar?'اقرأ':'Read'} <ArrowLeft size={14}/>
    </button>
   </div>
  </article>;
 }
 function manage(seriesId?:string) {
  window.dispatchEvent(new CustomEvent('barq:library-manage',{detail:seriesId||null}));
 }
 return <section className="bs-drive-section" aria-label={collectionLabel||(ar?'الروايات':'Books')}>
  {heading&&<h2>{collectionLabel||(ar?'رواياتي':'My books')}</h2>}
  {books.length===0?<p role="status">{ar?'مفيش روايات في الفولدر.':'No books in this folder.'}</p>:<>
   {collected.map(group=><article className="bs-real-card bs-published-card bs-series-grid-card" key={group.key}>
    <EditableCover id={'library-series:'+(group.seriesId||group.key)} title={group.title} ar={ar}>
     <DriveCover book={group.items.find(item=>item.coverId||item.cover)||group.items[0]}/>
    </EditableCover>
    <div className="bs-real-copy">
     <span className="bs-series-chip"><Layers size={13}/>{ar?'سلسلة روايات':'Book series'} · {group.items.length} {ar?'عدد':'issues'}</span>
     <h3 dir="auto">{group.title}</h3>
     <p>{ar?'الأعداد مرتبة وجاهزة للقراءة':'Issues organized and ready to read'}</p>
     <div className="bs-published-actions">
      <button className="bs-series-open" type="button" onClick={()=>setSelectedGroup(group.key)}>
       {ar?'عرض الأعداد':'View issues'} <ArrowLeft size={14}/>
      </button>
      <button className="bs-series-open" type="button" onClick={()=>onOpen(group.items[0].edition)}>
       {ar?'ابدأ':'Start'}
      </button>
      <button className="bs-library-manage-shortcut" type="button" title={ar?'تعديل السلسلة':'Edit series'}
       aria-label={(ar?'إدارة':'Manage')+' '+group.title} onClick={()=>manage(group.seriesId)}>
       <Settings2 size={15}/>
      </button>
     </div>
    </div>
   </article>)}
   {singles.map(bookCard)}
  </>}
  <Modal open={!!current} onClose={()=>setSelectedGroup(undefined)} title={current?.title||''} wide bodyClassName="bs-series-scroll">
   {current&&<div className="bs-series-books-view" dir={ar?'rtl':'ltr'}>
    <div className="bs-series-overview">
     <span>{current.items.length} {ar?'عدد في السلسلة':'issues in series'}</span>
     <button className="bs-muted-btn" type="button" onClick={()=>manage(current.seriesId)}>
      <Settings2 size={15}/>{ar?'إدارة الأعداد':'Manage issues'}
     </button>
    </div>
    <div className="bs-series-modal-grid">{current.items.map(bookCard)}</div>
   </div>}
  </Modal>
 </section>;
}
