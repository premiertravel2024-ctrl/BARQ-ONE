import {motion,useReducedMotion} from 'framer-motion';
import {motionTokens} from '../../lib/motion';
import {useApp} from '../../store';
type Props={checked:boolean;onChange:(v:boolean)=>void;label:string;disabled?:boolean};
export function Switch({checked,onChange,label,disabled}:Props){const reduced=useReducedMotion(),rtl=useApp(s=>s.language==='ar');return <button type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled} onClick={()=>onChange(!checked)}
  className={`relative h-7 w-12 rounded-full border border-stroke focus-ring transition-colors ${disabled?'opacity-45 cursor-not-allowed':''}`} style={{background:checked?'var(--accent-1)':'var(--bg-elevated)'}}>
  <motion.span className="absolute top-[3px] h-5 w-5 rounded-full bg-white shadow-sm" style={{insetInlineStart:3}} animate={{x:checked?(rtl?-20:20):0,scaleX:checked?[1.12,1]:[1.12,1]}} transition={reduced?{duration:.08}:motionTokens.spring.toggle}/>
</button>}
