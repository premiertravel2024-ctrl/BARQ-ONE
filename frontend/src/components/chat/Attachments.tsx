import {useState} from 'react';
import {registerAttachment} from '../../lib/attachmentRegistry';
import {File,Image as ImageIcon,X,FileCode2,FileText} from 'lucide-react';
import {useApp,type UploadedAttachment,uid} from '../../store';import {IconButton} from '../ui/IconButton';import {Modal} from '../ui/Modal';
export function Attachments({files,onRemove,compact=false}:{files:UploadedAttachment[];onRemove?:(id:string)=>void;compact?:boolean}){
 const [lightbox,setLightbox]=useState<string|null>(null);
 return <><div className="flex flex-wrap gap-2">{files.map(a=><div key={a.id} className={`relative flex items-center gap-2 rounded-md border border-stroke bg-elevated ${compact?'px-2 py-1':'px-2.5 py-2'} max-w-[220px]`}>
  {a.url&&a.type.startsWith('image/')?<button onClick={()=>setLightbox(a.url||null)} aria-label={`View ${a.name}`} className="focus-ring overflow-hidden rounded-sm"><img alt={a.name} src={a.url} className="h-10 w-10 object-cover"/></button>:a.type.startsWith('image/')?<ImageIcon size={19} className="shrink-0 text-accent"/>:a.type.includes('code')?<FileCode2 size={19} className="shrink-0 text-muted"/>:a.type.includes('text')?<FileText size={19} className="shrink-0 text-muted"/>:<File size={19} className="shrink-0 text-muted"/>}
  <span className="min-w-0 flex-1"><span className="block truncate text-xs font-medium" title={a.name}>{a.name}</span><span className="text-[10px] text-muted">{(a.size/1024).toFixed(0)} KB</span></span>
  {onRemove&&<IconButton label={`Remove ${a.name}`} icon={<X size={13}/>} className="!min-h-7 !min-w-7" onClick={()=>onRemove(a.id)}/>}<svg className="pointer-events-none absolute -inset-[2px] h-[calc(100%+4px)] w-[calc(100%+4px)]" aria-hidden><rect x="1" y="1" width="99%" height="97%" rx="12" fill="none" stroke="var(--accent-2)" strokeWidth="1" pathLength="100" strokeDasharray={`${a.progress} ${100-a.progress}`} opacity={a.progress<100?.7:0}/></svg>
 </div>)}</div><Modal title="Image preview" open={!!lightbox} onClose={()=>setLightbox(null)} wide>{lightbox&&<img src={lightbox} alt="Attached image" className="max-h-[70vh] w-full object-contain"/>}</Modal></>
}
export async function readFiles(files:FileList|File[],onProgress:(a:UploadedAttachment[])=>void):Promise<UploadedAttachment[]>{
 const list=Array.from(files).slice(0,8);
 const prepared:UploadedAttachment[]=list.map(f=>({id:uid(),name:f.name,size:f.size,type:f.type||'application/octet-stream',progress:12}));
 onProgress(prepared);
 await Promise.all(prepared.map(async(a,i)=>{
  const file=list[i];registerAttachment(a.id,file);if(file.type.startsWith('image/')&&file.size<1_500_000){
   a.url=await new Promise<string|undefined>(resolve=>{const reader=new FileReader();reader.onload=()=>resolve(typeof reader.result==='string'?reader.result:undefined);reader.onerror=()=>resolve(undefined);reader.readAsDataURL(file)})
  }
  a.progress=100;onProgress([...prepared]);
 }));return prepared;
}
export function useAttachmentToast(){return useApp(s=>s.toast)}
