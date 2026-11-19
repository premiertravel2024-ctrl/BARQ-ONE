import {EditableCover} from './EditableCover';
import {useEffect,useRef,useState,type ChangeEvent} from 'react';
import {BookOpen,FolderOpen} from 'lucide-react';
import type {ReadingEdition} from './BookReader';

export type DriveBook={edition:ReadingEdition;cover?:File;coverId?:string;group:string};
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

export function DriveBooks({books,ar,onOpen,heading=true,collectionLabel}:{books:DriveBook[];ar:boolean;onOpen:(edition:ReadingEdition)=>void;heading?:boolean;collectionLabel?:string}){
 const groups=new Map<string,DriveBook[]>();
 for(const book of books){
  const key=book.group||'';
  groups.set(key,[...(groups.get(key)||[]),book]);
 }
 function cards(items:DriveBook[]){
  return <div className="bs-real-grid">{items.map(book=><article className="bs-real-card bs-published-card" key={book.edition.id}>
   <EditableCover id={book.edition.id} title={book.edition.title} ar={ar}><DriveCover book={book}/></EditableCover>
   <div className="bs-real-copy"><h3 dir="auto">{book.edition.title}</h3>
    <button className="bs-series-open" type="button" onClick={()=>onOpen(book.edition)}>{ar?'اقرأ':'Read'}</button>
   </div>
  </article>)}</div>;
 }
 return <section className="bs-drive-section" aria-label={collectionLabel||(ar?'الروايات':'Books')}>
  {heading&&<h2>{collectionLabel||(ar?'رواياتي':'My books')}</h2>}
  {books.length===0?<p role="status">{ar?'مفيش ملفات PDF متاحة في الفولدر (الحد 64 ميجابايت للملف).':'No readable PDFs in this folder (64 MB limit per file).'}</p>:
   Array.from(groups,([title,items])=>title&&items.length>1?
    <details open={!heading} className="bs-drive-group" key={title}><summary dir="auto">{title} · {items.length}</summary>{cards(items)}</details>:
    <div key={title}>{cards(items)}</div>)}
 </section>;
}
