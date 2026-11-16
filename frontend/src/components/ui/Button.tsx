import {AnimatePresence,motion,useReducedMotion} from 'framer-motion';
import {Check,LoaderCircle} from 'lucide-react';
import {useEffect,useRef,useState,type ButtonHTMLAttributes,type CSSProperties,type MouseEvent, type ReactNode} from 'react';
import {motionTokens} from '../../lib/motion';

type Variant='primary'|'secondary'|'ghost'|'outline'|'danger'|'icon'|'pill';
type Size='sm'|'md'|'lg';
type Status='idle'|'loading'|'success'|'error';
export type ButtonProps=Omit<ButtonHTMLAttributes<HTMLButtonElement>,'onAnimationStart'|'onDrag'|'onDragStart'|'onDragEnd'> & {
  variant?:Variant;size?:Size;icon?:ReactNode;trailingIcon?:ReactNode;status?:Status;magnetic?:boolean;autoState?:boolean;
  onClick?:(e:MouseEvent<HTMLButtonElement>)=>void|Promise<unknown>;
};
const sizes:Record<Size,string>={sm:'min-h-9 px-3 text-sm gap-1.5',md:'min-h-10 px-4 text-sm gap-2',lg:'min-h-11 px-5 text-sm gap-2.5'};
const variants:Record<Variant,string>={
  primary:'text-white gradient-bg shadow-soft',
  secondary:'bg-elevated text-primary border border-stroke',
  ghost:'bg-transparent text-secondary hover:text-primary',
  outline:'bg-transparent text-primary border border-stroke',
  danger:'bg-danger/15 text-danger border border-danger/25',
  icon:'bg-transparent text-secondary hover:text-primary',
  pill:'bg-elevated text-primary border border-stroke rounded-full'
};
type Ripple={id:number;x:number;y:number;size:number};
export function Button({children,variant='secondary',size='md',icon,trailingIcon,status='idle',magnetic=false,autoState=false,onClick,disabled,className='',style,...rest}:ButtonProps){
  const reduced=useReducedMotion();const ref=useRef<HTMLButtonElement>(null);
  const [internal,setInternal]=useState<Status>('idle');const [ripples,setRipples]=useState<Ripple[]>([]);
  const [offset,setOffset]=useState({x:0,y:0});const [shineKey,setShineKey]=useState(0);
  const timers=useRef<ReturnType<typeof setTimeout>[]>([]);const seq=useRef(0);const [steadyWidth,setSteadyWidth]=useState<number|null>(null);
  useEffect(()=>()=>timers.current.forEach(clearTimeout),[]);
  const current=status!=='idle'?status:internal;
  const blocked=disabled||current==='loading';
  function schedule(fn:()=>void,time:number){timers.current.push(setTimeout(fn,time))}
  async function activate(e:MouseEvent<HTMLButtonElement>){
    if(blocked)return;
    if(!reduced){
      const b=e.currentTarget.getBoundingClientRect(),size=Math.max(b.width,b.height)*2.2;
      const id=++seq.current;setRipples(r=>[...r,{id,x:e.detail===0?b.width/2:e.clientX-b.left,y:e.detail===0?b.height/2:e.clientY-b.top,size}]);
      schedule(()=>setRipples(r=>r.filter(p=>p.id!==id)),motionTokens.duration.ripple*1000);
    }
    if(!onClick)return;
    try{
      const result=onClick(e);
      if(autoState && result && typeof (result as Promise<unknown>).then==='function'){
        setSteadyWidth(ref.current?.getBoundingClientRect().width??null);setInternal('loading');await result;setInternal('success');schedule(()=>{setInternal('idle');setSteadyWidth(null)},1500);
      }
    }catch(error){setInternal('error');schedule(()=>{setInternal('idle');setSteadyWidth(null)},1100);console.error('Button action failed',error)}
  }
  function onPointerMove(e:React.PointerEvent<HTMLButtonElement>){
    if(!magnetic||reduced||blocked||e.pointerType==='touch')return;
    const b=e.currentTarget.getBoundingClientRect();const x=(e.clientX-(b.left+b.width/2))/b.width*motionTokens.distance.magnetic*2;
    const y=(e.clientY-(b.top+b.height/2))/b.height*motionTokens.distance.magnetic*2;
    setOffset({x:Math.max(-6,Math.min(6,x)),y:Math.max(-6,Math.min(6,y))});
  }
  const iconOnly=variant==='icon';
  return <motion.button ref={ref} {...rest} type={rest.type||'button'}
    disabled={blocked} aria-busy={current==='loading'}
    onClick={activate} onPointerMove={onPointerMove} onPointerLeave={()=>setOffset({x:0,y:0})}
    onHoverStart={()=>{if(variant==='primary'&&!reduced)setShineKey(i=>i+1)}}
    whileHover={!blocked&&!reduced?{y:motionTokens.distance.lift,filter:'brightness(1.08)',scale:1.005}:undefined}
    whileTap={!blocked&&!reduced?{scale:.96,boxShadow:'0 1px 2px rgba(0,0,0,.10)'}:undefined}
    animate={current==='error'&&!reduced?{x:[0,-5,5,-4,4,0],backgroundColor:['rgba(239,68,68,.18)','rgba(239,68,68,.55)','rgba(239,68,68,.18)']}:
      current==='success'?{backgroundColor:['rgba(34,197,94,.7)','rgba(34,197,94,.7)','rgba(34,197,94,0)'],x:offset.x,y:offset.y}:{x:offset.x,y:offset.y}}
    transition={current==='error'?{duration:.3}:{...motionTokens.spring.press}}
    style={{...style,minWidth:steadyWidth??style?.minWidth,position:'relative',isolation:'isolate',overflow:'hidden',...(variant==='primary'?{backgroundSize:'220% 100%'}:{}),opacity:disabled?.45:1} as CSSProperties}
    className={`group inline-flex items-center justify-center whitespace-nowrap select-none font-semibold transition-[background-color,color,border-color,box-shadow,filter] duration-200 ease-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-2)] ${sizes[size]} ${variants[variant]} ${iconOnly?'!min-w-11 !px-2 !rounded-xl':'rounded-xl'} ${variant==='pill'?'!rounded-full':''} ${blocked?'cursor-not-allowed':'cursor-pointer'} ${className}`}>
    {variant==='primary'&&shineKey>0&&!reduced&&<motion.span key={shineKey} className="pointer-events-none absolute inset-y-[-40%] -left-[65%] w-[35%] rotate-[25deg] bg-gradient-to-r from-transparent via-white/25 to-transparent" initial={{x:0}} animate={{x:'480%'}} transition={{duration:motionTokens.duration.shine,ease:'easeInOut'}}/>}
    {!reduced&&ripples.map(r=><motion.span key={r.id} aria-hidden className="pointer-events-none absolute rounded-full bg-white/25" style={{width:r.size,height:r.size,left:r.x-r.size/2,top:r.y-r.size/2}} initial={{scale:0,opacity:.42}} animate={{scale:1,opacity:0}} transition={{duration:motionTokens.duration.ripple,ease:'easeOut'}}/>)}
    <span className="relative z-10 inline-flex items-center justify-center gap-inherit" style={{gap:iconOnly?0:8,minWidth:0}}>
      <AnimatePresence mode="wait" initial={false}>
        {current==='loading'?<motion.span key="load" initial={{opacity:0,scale:.8}} animate={{opacity:1,scale:1}} exit={{opacity:0,scale:.7}} className="inline-flex items-center justify-center" aria-label="Loading"><LoaderCircle size={18} className="animate-spin"/></motion.span>:
        current==='success'?<motion.svg key="check" aria-label="Success" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><motion.path d="M5 12l5 5L20 7" initial={{pathLength:0}} animate={{pathLength:1}} transition={{duration:motionTokens.duration.success}}/></motion.svg>:
        <motion.span key="normal" className="inline-flex items-center justify-center gap-2" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}}>
          {icon&&<span className="inline-flex shrink-0 transition-transform duration-200 group-hover:scale-110">{icon}</span>}
          {children}{trailingIcon&&<span className="inline-flex shrink-0">{trailingIcon}</span>}
        </motion.span>}
      </AnimatePresence>
    </span>
  </motion.button>;
}
export function Spinner(){return <LoaderCircle size={16} className="animate-spin"/>}
export function CheckIcon(){return <Check size={16}/>}
