import {useCallback,useEffect,useRef,useState,type ReactNode} from 'react';
import {BookOpen,ImagePlus,Pencil,RotateCcw,Trash2} from 'lucide-react';
import {Modal} from '../components/ui/Modal';

type CoverState='original'|'custom'|'hidden';

async function coverJpeg(file:File){
 if(!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>12*1024*1024)throw new Error('Invalid image');
 const image=await createImageBitmap(file);
 try{
  const scale=Math.min(1,800/Math.max(image.width,image.height));
  const canvas=document.createElement('canvas');
  canvas.width=Math.max(1,Math.round(image.width*scale));
  canvas.height=Math.max(1,Math.round(image.height*scale));
  const context=canvas.getContext('2d');
  if(!context)throw new Error('Image decoding unavailable');
  context.fillStyle='#191d24';
  context.fillRect(0,0,canvas.width,canvas.height);
  context.drawImage(image,0,0,canvas.width,canvas.height);
  return await new Promise<Blob>((resolve,reject)=>canvas.toBlob(
   blob=>blob?resolve(blob):reject(new Error('Could not save image')),'image/jpeg',.9));
 }finally{image.close();}
}

export function EditableCover({id,title,ar,children}:{id:string;title:string;ar:boolean;children:ReactNode}){
 const root='/v1/reading/covers/';
 const key=encodeURIComponent(id);
 const endpoint=root+'image/'+key;
 const [state,setState]=useState<CoverState>('original');
 const [revision,setRevision]=useState(0);
 const [open,setOpen]=useState(false);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const picker=useRef<HTMLInputElement>(null);
 const close=useCallback(()=>setOpen(false),[]);
 const edit=ar?'تعديل الغلاف':'Edit cover';
 useEffect(()=>{
  const controller=new AbortController();
  const refresh=()=>void fetch(root+'state/'+key,{cache:'no-store',signal:controller.signal}).then(async response=>{
   if(response.ok){
    const next=(await response.json()).state as CoverState;
    if(!controller.signal.aborted){setState(next);setRevision(value=>value+1);}
   }
  }).catch(()=>{});
  refresh();
  window.addEventListener('barq:covers-synced',refresh);
  return()=>{controller.abort();window.removeEventListener('barq:covers-synced',refresh);};
 },[key]);

 async function update(action:'upload'|'hide'|'restore',file?:File){
  setBusy(true);setError('');
  try{
   const body=action==='upload'&&file?await coverJpeg(file):undefined;
   const response=await fetch(action==='hide'?root+'hide/'+key:endpoint,{
    method:action==='upload'?'PUT':action==='hide'?'POST':'DELETE',
    headers:body?{'Content-Type':'image/jpeg'}:undefined,body,
   });
   if(!response.ok)throw new Error('Could not change cover');
   setState((await response.json()).state as CoverState);
   setRevision(value=>value+1);
   window.dispatchEvent(new Event('barq:drive-sync'));
   setOpen(false);
  }catch{
   setError(action==='upload'?(ar?'تعذّر حفظ الصورة. اختار JPG أو PNG أو WebP بحجم أقل من ١٢ ميجابايت.':
    'Could not save the image. Choose JPG, PNG or WebP under 12 MB.'):(ar?'تعذّر تعديل الغلاف.':'Could not update the cover.'));
  }finally{setBusy(false);}
 }

 return <div className="bs-editable-cover">
  {state==='original'?children:<div className="bs-real-cover" aria-hidden="true">
   {state==='custom'?<img src={endpoint+'?v='+revision} alt="" loading="lazy" decoding="async"/>:
    <><BookOpen size={24}/><strong>{title}</strong></>}
  </div>}
  <button className="bs-cover-edit" type="button" aria-label={edit+' · '+title} title={edit} onClick={()=>{setError('');setOpen(true);}}>
   <Pencil size={12} strokeWidth={2.25}/>
  </button>
  {open&&<Modal open onClose={close} title={edit}>
   <div className="bs-cover-options" dir={ar?'rtl':'ltr'}>
    <strong dir="auto">{title}</strong>
    <input ref={picker} hidden type="file" accept="image/jpeg,image/png,image/webp" onChange={event=>{
     const file=event.currentTarget.files?.[0];
     event.currentTarget.value='';
     if(file)void update('upload',file);
    }}/>
    <button className="bs-muted-btn" type="button" disabled={busy} onClick={()=>picker.current?.click()}>
     <ImagePlus size={16}/>{state==='custom'?(ar?'غيّر الصورة':'Replace image'):(ar?'اختار صورة':'Choose image')}
    </button>
    {state!=='hidden'&&<button className="bs-muted-btn" type="button" disabled={busy} onClick={()=>void update('hide')}>
     <Trash2 size={16}/>{ar?'احذف الغلاف من العرض':'Remove displayed cover'}
    </button>}
    {state!=='original'&&<button className="bs-muted-btn" type="button" disabled={busy} onClick={()=>void update('restore')}>
     <RotateCcw size={16}/>{ar?'رجّع الغلاف الأصلي':'Restore original cover'}
    </button>}
    {error&&<p className="bs-alert" role="alert">{error}</p>}
   </div>
  </Modal>}
 </div>;
}
