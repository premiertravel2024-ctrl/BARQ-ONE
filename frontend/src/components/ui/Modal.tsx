import {AnimatePresence,motion,useReducedMotion} from 'framer-motion';
import {createPortal} from 'react-dom';
import {useEffect,useRef,type ReactNode} from 'react';
import {X} from 'lucide-react';
import {IconButton} from './IconButton';
import {motionTokens} from '../../lib/motion';
export function Modal({open,onClose,title,children,footer,wide=false,dialogClassName='',bodyClassName=''}:{open:boolean;onClose:()=>void;title:string;children:ReactNode;footer?:ReactNode;wide?:boolean;dialogClassName?:string;bodyClassName?:string}){
 const ref=useRef<HTMLDivElement>(null),closeRef=useRef<HTMLButtonElement|null>(null),reduced=useReducedMotion();
 useEffect(()=>{if(!open)return;const previous=document.activeElement as HTMLElement|null;const old=document.body.style.overflow;document.body.style.overflow='hidden';closeRef.current?.focus();
   const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){onClose();return}if(e.key==='Tab'&&ref.current){const focus=Array.from(ref.current.querySelectorAll<HTMLElement>('button:not(:disabled),[href],input:not(:disabled),textarea:not(:disabled),select:not(:disabled),[tabindex]:not([tabindex="-1"])'));if(!focus.length)return;
     const first=focus[0],last=focus[focus.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}}};document.addEventListener('keydown',key);
   return()=>{document.body.style.overflow=old;document.removeEventListener('keydown',key);previous?.focus()}},[open,onClose]);
 return createPortal(<AnimatePresence>{open&&<motion.div className="fixed inset-0 z-[70] flex items-center justify-center p-4" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}}>
  <motion.div className="absolute inset-0 bg-[#080a10]/65 backdrop-blur-[5px]" onClick={onClose} aria-hidden/>
  <motion.div ref={ref} role="dialog" aria-modal="true" aria-label={title} initial={{opacity:0,scale:reduced?1:.96,y:reduced?0:8}} animate={{opacity:1,scale:1,y:0}} exit={{opacity:0,scale:reduced?1:.97,y:6}} transition={{duration:motionTokens.duration.modal}}
    className={`relative z-10 flex w-full flex-col overflow-hidden rounded-lg border border-stroke bg-surface shadow-float ${wide?'max-w-3xl':'max-w-lg'} max-h-[min(88dvh,850px)] ${dialogClassName}`}>
    <header className="flex shrink-0 items-center justify-between gap-3 border-b border-stroke px-5 py-4"><h2 className="text-lg font-semibold">{title}</h2><span ref={node=>{closeRef.current=node?.querySelector('button')??null}}><IconButton label={document.documentElement.lang==='ar'?'إغلاق':'Close'} icon={<X size={18}/>} onClick={onClose}/></span></header>
    <div className={`min-h-0 flex-1 overflow-y-auto p-5 ${bodyClassName}`}>{children}</div>
    {footer&&<footer className="flex justify-end gap-2 border-t border-stroke p-4">{footer}</footer>}
  </motion.div>
 </motion.div>}</AnimatePresence>,document.body)
}
