import {AnimatePresence,motion,useReducedMotion} from 'framer-motion';
import {cloneElement,isValidElement,useEffect,useRef,useState,type MouseEvent,type ReactElement,type ReactNode} from 'react';
import {motionTokens} from '../../lib/motion';
export type MenuItem={id:string;label:string;icon?:ReactNode;description?:string;danger?:boolean;disabled?:boolean;onClick:()=>void};
export function Dropdown({trigger,items,align='end',searchable=false,placeholder='Search...'}:{trigger:ReactNode;items:MenuItem[];align?:'start'|'end';searchable?:boolean;placeholder?:string}){
 const [open,setOpen]=useState(false),[filter,setFilter]=useState('');const root=useRef<HTMLDivElement>(null);const search=useRef<HTMLInputElement>(null);const menu=useRef<HTMLDivElement>(null);const reduced=useReducedMotion();
 useEffect(()=>{if(!open)return;const down=(e:PointerEvent)=>{if(root.current&&!root.current.contains(e.target as Node))setOpen(false)};
   const key=(e:KeyboardEvent)=>{if(e.key==='Escape')setOpen(false)};document.addEventListener('pointerdown',down);document.addEventListener('keydown',key);
   return()=>{document.removeEventListener('pointerdown',down);document.removeEventListener('keydown',key)}},[open]);
 useEffect(()=>{if(open){const id=window.requestAnimationFrame(()=>{if(searchable)search.current?.focus();else menu.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus()});return()=>window.cancelAnimationFrame(id)}},[open,searchable]);
 const visible=items.filter(i=>`${i.label} ${i.description||''}`.toLowerCase().includes(filter.toLowerCase()));
 // Preserve the native button's keyboard click. Wrapping it in an onKeyDown handler
 // caused Enter and Space to toggle the menu twice (keyboard activation + click).
 const triggerElement=isValidElement(trigger)?cloneElement(trigger as ReactElement<{onClick?:(e:MouseEvent<HTMLElement>)=>void; 'aria-haspopup'?:'menu';'aria-expanded'?:boolean}>,{
   'aria-haspopup':'menu','aria-expanded':open,
   onClick:(e:MouseEvent<HTMLElement>)=>{trigger.props && (trigger.props as {onClick?:(e:MouseEvent<HTMLElement>)=>void}).onClick?.(e);if(!e.defaultPrevented)setOpen(v=>!v)}
 }):<button type="button" aria-haspopup="menu" aria-expanded={open} onClick={()=>setOpen(v=>!v)}>{trigger}</button>;
 function onMenuKey(e:React.KeyboardEvent<HTMLDivElement>){
   const buttons=Array.from(menu.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')??[]);
   const index=buttons.indexOf(document.activeElement as HTMLButtonElement);
   if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();const step=e.key==='ArrowDown'?1:-1;buttons[(index+step+buttons.length)%buttons.length]?.focus()}
   if(e.key==='Home'){e.preventDefault();buttons[0]?.focus()}
   if(e.key==='End'){e.preventDefault();buttons.at(-1)?.focus()}
 }
 return <div className="relative inline-flex" ref={root}>
   {triggerElement}
   <AnimatePresence>{open&&<motion.div ref={menu} onKeyDown={onMenuKey} role="menu" aria-label="Options" initial={{opacity:0,y:reduced?0:-7,scale:.97}} animate={{opacity:1,y:0,scale:1}} exit={{opacity:0,y:reduced?0:-5,scale:.98}} transition={{duration:.17}}
      className={`absolute top-[calc(100%+8px)] z-50 min-w-[232px] max-w-[min(340px,90vw)] rounded-lg border border-stroke bg-surface p-1.5 shadow-float ${align==='end'?'end-0':'start-0'}`}>
      {searchable&&<input ref={search} className="ui-input mb-1.5 text-sm" placeholder={placeholder} aria-label={placeholder} value={filter} onChange={e=>setFilter(e.target.value)} />}
      <div className="max-h-72 overflow-y-auto">{visible.map((item,i)=><motion.button type="button" key={item.id} role="menuitem" disabled={item.disabled}
        initial={{opacity:0,x:reduced?0:-5}} animate={{opacity:1,x:0}} transition={{delay:reduced?0:i*motionTokens.duration.stagger,duration:.14}}
        onClick={()=>{setOpen(false);setFilter('');item.onClick()}}
        className={`group relative flex w-full items-center gap-2.5 rounded-sm px-3 py-2 text-start text-sm transition-colors hover:bg-elevated focus-visible:bg-elevated focus-visible:outline-none disabled:opacity-40 ${item.danger?'text-danger':'text-primary'}`}>
        <span className="pointer-events-none absolute inset-y-0 start-0 w-1 rounded-full bg-accent opacity-0 -translate-x-1 transition-all group-hover:translate-x-0 group-hover:opacity-100 rtl:translate-x-1 rtl:group-hover:translate-x-0"/>
        {item.icon&&<span aria-hidden className="text-muted">{item.icon}</span>}<span className="min-w-0 flex-1"><span className="block truncate">{item.label}</span>{item.description&&<span className="block truncate text-xs text-muted">{item.description}</span>}</span>
      </motion.button>)}{!visible.length&&<div className="px-3 py-5 text-center text-xs text-muted">{document.documentElement.lang==='ar'?'لا توجد نتائج':'No results'}</div>}</div>
   </motion.div>}</AnimatePresence>
 </div>
}
