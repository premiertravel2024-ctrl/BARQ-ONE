import {AnimatePresence,motion,useReducedMotion} from 'framer-motion';
import {useCallback,useEffect,useRef,useState,type ReactNode} from 'react';
import {createPortal} from 'react-dom';
import {motionTokens} from '../../lib/motion';
type Props={label:string;children:ReactNode;side?:'top'|'bottom';delay?:number};
export function Tooltip({label,children,side='top',delay=300}:Props){
  const host=useRef<HTMLSpanElement>(null);
  const timer=useRef<ReturnType<typeof setTimeout>|null>(null);
  const pointerInside=useRef(false);
  const focusedByKeyboard=useRef(false);
  const [visible,setVisible]=useState(false);
  const [placement,setPlacement]=useState<'top'|'bottom'>('top');
  const [at,setAt]=useState({left:0,top:0});
  const reduced=useReducedMotion();
  const hide=useCallback(()=>{
    if(timer.current!==null){clearTimeout(timer.current);timer.current=null;}
    setVisible(false);
  },[]);
  const reposition=useCallback(()=>{
    const b=host.current?.getBoundingClientRect();if(!b)return;
    const width=Math.min(260,Math.max(76,label.length*7+20));
    const left=Math.max(width/2+8,Math.min(window.innerWidth-width/2-8,b.left+b.width/2));
    const above=b.top>=46,below=window.innerHeight-b.bottom>=46;
    const resolved=side==='top'?(above?'top':'bottom'):(below?'bottom':'top');
    setPlacement(resolved);setAt({left,top:resolved==='top'?b.top-9:b.bottom+9});
  },[label,side]);
  const show=useCallback(()=>{
    if(timer.current!==null)clearTimeout(timer.current);
    timer.current=setTimeout(()=>{
      timer.current=null;
      if(!pointerInside.current&&!focusedByKeyboard.current)return;
      if(!host.current?.isConnected)return;
      reposition();setVisible(true);
    },Math.max(0,delay));
  },[delay,reposition]);
  useEffect(()=>{
    const dismissed=()=>{pointerInside.current=false;focusedByKeyboard.current=false;hide();};
    const onPointerMove=(event:PointerEvent)=>{
      if(!pointerInside.current||!host.current)return;
      const b=host.current.getBoundingClientRect();
      if(event.clientX<b.left||event.clientX>b.right||event.clientY<b.top||event.clientY>b.bottom){
        pointerInside.current=false;
        if(!focusedByKeyboard.current)hide();
      }
    };
    const onKey=(event:KeyboardEvent)=>{if(event.key==='Escape')dismissed();};
    window.addEventListener('blur',dismissed);
    window.addEventListener('scroll',dismissed,true);
    window.addEventListener('resize',dismissed);
    document.addEventListener('pointerdown',dismissed,true);
    document.addEventListener('pointermove',onPointerMove,true);
    document.addEventListener('keydown',onKey);
    return()=>{
      if(timer.current!==null)clearTimeout(timer.current);
      window.removeEventListener('blur',dismissed);
      window.removeEventListener('scroll',dismissed,true);
      window.removeEventListener('resize',dismissed);
      document.removeEventListener('pointerdown',dismissed,true);
      document.removeEventListener('pointermove',onPointerMove,true);
      document.removeEventListener('keydown',onKey);
    };
  },[hide]);
  return <span ref={host} className="inline-flex shrink-0"
    onPointerEnter={()=>{pointerInside.current=true;show();}}
    onPointerLeave={()=>{pointerInside.current=false;if(!focusedByKeyboard.current)hide();}}
    onFocusCapture={e=>{if(e.target instanceof HTMLElement&&e.target.matches(':focus-visible')){focusedByKeyboard.current=true;show();}}}
    onBlurCapture={e=>{if(!e.currentTarget.contains(e.relatedTarget as Node|null)){focusedByKeyboard.current=false;if(!pointerInside.current)hide();}}}>
    {children}
    {createPortal(<AnimatePresence>{visible&&<motion.span role="tooltip" className="pointer-events-none fixed z-[100] rounded-lg border border-stroke bg-elevated px-2.5 py-1.5 text-xs text-primary shadow-float" style={{left:at.left,top:at.top,translate:'-50% 0',whiteSpace:'nowrap',maxWidth:260}}
      initial={{opacity:0,y:reduced?0:placement==='top'?4:-4,scale:.98}}
      animate={{opacity:1,y:placement==='top'?'-100%':0,scale:1}}
      exit={{opacity:0}} transition={{duration:motionTokens.duration.tooltip}}>{label}</motion.span>}</AnimatePresence>,document.body)}
  </span>;
}
