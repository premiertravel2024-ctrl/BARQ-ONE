import {useEffect,useRef,useState,type ChangeEvent, type DragEvent,type KeyboardEvent} from 'react';
import {AnimatePresence,motion} from 'framer-motion';
import {ArrowUp,Paperclip,Square,FileUp} from 'lucide-react';
import {useApp,type UploadedAttachment} from '../../store';import {useT} from '../../i18n';
import {IconButton} from '../ui/IconButton';import {Button} from '../ui/Button';import {Attachments,readFiles} from './Attachments';import {ModelSelector} from './ModelSelector';import {stopGeneration,submitChat} from '../../lib/chat';
import {releaseAttachment} from '../../lib/attachmentRegistry';

const draftFiles=new Map<string,UploadedAttachment[]>();
const loadingDrafts=new Set<string>();
const draftEvents=new EventTarget();

export function Composer({draftId,prefill,onPrefillUsed}:{draftId:string;prefill?:string;onPrefillUsed?:()=>void}){
 const t=useT(),language=useApp(s=>s.language),streaming=useApp(s=>s.streaming),toast=useApp(s=>s.toast);
 const draftKey='barq-chat-draft:'+draftId;
 const [value,setText]=useState(()=>{try{return localStorage.getItem(draftKey)||''}catch{return ''}});
 const [files,setFiles]=useState(()=>draftFiles.get(draftId)||[]);
 const [drag,setDrag]=useState(false),[reading,setReading]=useState(()=>loadingDrafts.has(draftId));
 useEffect(()=>{
  const refresh=()=>{setFiles(draftFiles.get(draftId)||[]);setReading(loadingDrafts.has(draftId))};
  draftEvents.addEventListener(draftId,refresh);
  return()=>draftEvents.removeEventListener(draftId,refresh);
 },[draftId]);
 function setValue(next:string){
  setText(next);
  try{if(next)localStorage.setItem(draftKey,next);else localStorage.removeItem(draftKey)}catch{/* Storage can be unavailable. */}
 }
 function saveFiles(next:UploadedAttachment[]){
  if(next.length)draftFiles.set(draftId,next);
  else draftFiles.delete(draftId);
  draftEvents.dispatchEvent(new Event(draftId));
 }
 const textarea=useRef<HTMLTextAreaElement>(null),fileInput=useRef<HTMLInputElement>(null);
 useEffect(()=>{if(prefill){setValue(prefill);onPrefillUsed?.();textarea.current?.focus()}},[prefill,onPrefillUsed]);
 useEffect(()=>{
  const element=textarea.current;
  if(!element)return;
  const resize=()=>{
   element.style.height='auto';
   element.style.height=Math.min(element.scrollHeight,220)+'px';
  };
  resize();
  if(typeof ResizeObserver==='undefined')return;
  let width=element.clientWidth;
  const observer=new ResizeObserver(()=>{
   if(element.clientWidth===width)return;
   width=element.clientWidth;
   resize();
  });
  observer.observe(element);
  return()=>observer.disconnect();
 },[value]);
 useEffect(()=>{const viewport=window.visualViewport;const onResize=()=>{const keyboard=Math.max(0,window.innerHeight-(viewport?.height??window.innerHeight)-(viewport?.offsetTop??0));document.documentElement.style.setProperty('--keyboard-inset',`${keyboard}px`)};
  viewport?.addEventListener('resize',onResize);return()=>viewport?.removeEventListener('resize',onResize)},[]);
 async function addFiles(incoming:FileList|File[]){const list=Array.from(incoming);if(!list.length||loadingDrafts.has(draftId))return;
  const allowed=list.filter(f=>f.size<=10*1024*1024).slice(0,8-files.length);if(allowed.length!==list.length)toast('info','Some files skipped','Maximum 8 attachments, 10 MB each');
  if(!allowed.length)return;
  loadingDrafts.add(draftId);draftEvents.dispatchEvent(new Event(draftId));
  const previous=files;
  try{await readFiles(allowed,progress=>saveFiles([...previous,...progress]));}
  finally{loadingDrafts.delete(draftId);draftEvents.dispatchEvent(new Event(draftId));}
 }
 function onDrop(e:DragEvent){e.preventDefault();e.stopPropagation();setDrag(false);void addFiles(e.dataTransfer.files)}
 async function send(){if(streaming||loadingDrafts.has(draftId)||(!value.trim()&&!files.length))return;const text=value;const queued=files;setValue('');saveFiles([]);await submitChat(text,queued)}
 function key(e:KeyboardEvent<HTMLTextAreaElement>){if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();void send()}}
 return <div className="barq-composer relative z-10 mx-auto w-full max-w-[920px] px-3 pb-[calc(10px+env(safe-area-inset-bottom))] pt-1 md:px-6" style={{marginBottom:'var(--keyboard-inset,0px)'}}>
  <div dir={language==='ar'?'rtl':'ltr'} className={`barq-composer-surface input-halo relative grid grid-cols-[auto_minmax(0,1fr)] items-center rounded-[26px] border border-stroke bg-surface shadow-soft sm:grid-cols-[auto_minmax(0,1fr)_auto] transition-[border-color,box-shadow] duration-200 ${drag?'border-accent':''}`} onDragEnter={e=>{e.preventDefault();setDrag(true)}} onDragOver={e=>e.preventDefault()} onDragLeave={e=>{if(!e.currentTarget.contains(e.relatedTarget as Node))setDrag(false)}} onDrop={onDrop}>
    <AnimatePresence>{drag&&<motion.div initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} className="pointer-events-none absolute inset-0 z-20 flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-accent bg-elevated/95"><FileUp size={26} className="mb-2 text-accent"/><span className="text-sm font-semibold">{language==='ar'?'أفلت الملفات للإرفاق':'Drop files to attach'}</span></motion.div>}</AnimatePresence>
    {reading&&<p role="status" className="col-span-full px-3 pt-2 text-xs text-secondary">{language==='ar'?'جاري تجهيز المرفقات…':'Preparing attachments…'}</p>}
    {files.length>0&&<div className="barq-composer-attachments col-span-full border-b border-stroke px-3 pt-3"><Attachments files={files} onRemove={reading?undefined:id=>{releaseAttachment(id);saveFiles(files.filter(a=>a.id!==id))}}/></div>}
    <div className="barq-composer-context-tools flex min-w-0 shrink-0 items-center gap-1 ps-2 pe-1"><input ref={fileInput} aria-label={t('attach')} type="file" multiple className="hidden" accept="image/*,.pdf,.docx,.xlsx,.txt,.md,.json,.csv,.js,.jsx,.ts,.tsx,.py,.html,.css,.sql,.yaml,.yml,.log" onChange={(e:ChangeEvent<HTMLInputElement>)=>{if(e.target.files)void addFiles(e.target.files);e.currentTarget.value=''}}/>
     <IconButton label={t('attach')} icon={<Paperclip size={19}/>} onClick={()=>fileInput.current?.click()}/><ModelSelector/></div>
    <label htmlFor="chatComposer" className="sr-only">{t('prompt')}</label><textarea id="chatComposer" ref={textarea} rows={1} value={value} onChange={e=>setValue(e.target.value)} onKeyDown={key} placeholder={t('prompt')}
     className="block max-h-[220px] min-h-[44px] min-w-0 flex-1 resize-none overflow-y-auto bg-transparent px-4 py-[11px] text-base leading-[1.5] text-primary outline-none placeholder:text-muted" dir="auto"/>
    <div className="barq-composer-toolbar col-span-full flex w-full items-center justify-end gap-1 px-2 pb-1 sm:col-span-1 sm:w-auto sm:shrink-0 sm:gap-0 sm:pb-0 sm:ps-0 sm:pe-2">
     <div className="barq-composer-actions flex items-center gap-1"><span className={`hidden px-2 text-[11px] sm:inline ${value.length>12000?'text-warning':'text-muted'}`}>{value.length>9000?`${value.length.toLocaleString()} ${t('count')}`:''}</span>
      {streaming?<Button variant="danger" icon={<Square size={16}/>} onClick={stopGeneration} size="sm" aria-label={t('stop')}>{t('stop')}</Button>:
       <Button variant="primary" size="sm" icon={<ArrowUp size={19} className="transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5"/>} onClick={()=>void send()} disabled={reading||(!value.trim()&&!files.length)} aria-label={t('send')} className="barq-send-button !min-w-11 !px-3"><span className="hidden md:inline">{t('send')}</span></Button>}
     </div>
    </div>
  </div>
  <div className="barq-composer-hints hidden sm:flex" aria-hidden="true">
   <span><kbd dir="ltr" className="keycap">Enter</kbd> {language==='ar'?'إرسال':'Send'}</span>
   <span><kbd dir="ltr" className="keycap">Shift+Enter</kbd> {language==='ar'?'سطر جديد':'New line'}</span>
  </div>
 </div>
}
