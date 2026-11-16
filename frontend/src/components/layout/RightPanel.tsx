import {useEffect,useState} from 'react';
import {AnimatePresence,motion,useReducedMotion} from 'framer-motion';
import {X,SlidersHorizontal} from 'lucide-react';import {useApp} from '../../store';import {useT} from '../../i18n';import {IconButton} from '../ui/IconButton';import {Switch} from '../ui/Switch';import {motionTokens} from '../../lib/motion';
type PerformanceData={measured_responses:number;ttft_seconds:{median:number|null;p95:number|null};total_seconds:{median:number|null;p95:number|null};fallback_responses:number};
function PerformanceMonitor({active}:{active:boolean}){
 const [data,setData]=useState<PerformanceData|null>(null),[error,setError]=useState('');
 const ar=useApp(s=>s.language)==='ar';
 useEffect(()=>{
  if(!active)return;
  let live=true;
  async function load(){try{const response=await fetch('/v1/performance',{cache:'no-store'});if(!response.ok)throw new Error(`HTTP ${response.status}`);
   const value=await response.json() as PerformanceData;if(live){setData(value);setError('')}}catch(e){if(live)setError(e instanceof Error?e.message:'Unavailable')}}
  void load();const timer=window.setInterval(()=>void load(),12000);
  return()=>{live=false;window.clearInterval(timer)};
 },[active]);
 const metric=(v:number|null|undefined)=>typeof v==='number'?`${v.toFixed(2)}s`:'—';
 return <section aria-label={ar?'مراقبة الأداء':'Performance Monitor'} className="rounded-lg border border-stroke bg-elevated p-3 text-sm">
  <h3 className="mb-3 font-semibold">{ar?'مراقبة سرعة الرد':'Performance Monitor'}</h3>
  <div className="grid grid-cols-2 gap-3 text-xs"><div><div className="text-muted">{ar?'بداية الرد (وسيط)':'First token (median)'}</div><div className="mt-1 font-mono text-primary">{metric(data?.ttft_seconds.median)}</div></div>
  <div><div className="text-muted">{ar?'بداية الرد (95%)':'First token (p95)'}</div><div className="mt-1 font-mono text-primary">{metric(data?.ttft_seconds.p95)}</div></div>
  <div><div className="text-muted">{ar?'ردود مقاسة':'Measured replies'}</div><div className="mt-1 font-mono text-primary">{data?.measured_responses??'—'}</div></div>
  <div><div className="text-muted">{ar?'تحويلات مزود':'Fallback replies'}</div><div className="mt-1 font-mono text-primary">{data?.fallback_responses??'—'}</div></div></div>
  {error&&<p className="mt-2 text-xs text-muted">{ar?'القياسات غير متاحة':'Metrics unavailable'}: {error}</p>}
 </section>
}
export function RightPanel(){const open=useApp(s=>s.rightOpen),setOpen=useApp(s=>s.setRightOpen),options=useApp(s=>s.options),setOptions=useApp(s=>s.setOptions),t=useT(),reduced=useReducedMotion();
 const inner=<div className="flex h-full flex-col"><header className="flex h-[68px] shrink-0 items-center justify-between border-b border-stroke px-4"><span className="flex items-center gap-2 text-sm font-bold"><SlidersHorizontal size={17} className="text-accent"/>{t('chatSettings')}</span><IconButton label={t('close')} icon={<X size={17}/>} onClick={()=>setOpen(false)}/></header>
  <div className="flex-1 space-y-7 overflow-y-auto p-5"><section><div className="mb-3 flex justify-between text-sm"><label htmlFor="temperature">{t('temperature')}</label><span className="font-mono text-muted">{options.temperature.toFixed(1)}</span></div><input id="temperature" className="w-full accent-[#E52235]" type="range" min="0" max="2" step="0.1" value={options.temperature} onChange={e=>setOptions({temperature:Number(e.target.value)})}/><p className="mt-1 text-xs text-muted">{useApp.getState().language==='ar'?'دقيق ← → إبداعي':'Focused ← → Creative'}</p></section>
   <section><label htmlFor="maxTokens" className="mb-2 block text-sm">{t('tokens')}</label><input id="maxTokens" type="number" className="ui-input" min={256} max={32768} step={256} value={options.maxTokens} onChange={e=>setOptions({maxTokens:Math.min(32768,Math.max(256,Number(e.target.value)||256))})}/></section>
   <section><label htmlFor="systemPrompt" className="mb-2 block text-sm">{t('systemPrompt')}</label><textarea id="systemPrompt" className="ui-input min-h-36 resize-y text-sm leading-relaxed" value={options.systemPrompt} onChange={e=>setOptions({systemPrompt:e.target.value})}/></section>
   <section className="flex items-center justify-between gap-3"><label htmlFor="localModeText" id="localModeText" className="text-sm">{t('localOnly')}<span className="mt-1 block text-xs text-muted">{useApp.getState().language==='ar'?'Ollama · بدون طلبات سحابية':'Ollama · no cloud requests'}</span></label><Switch checked={options.localOnly} onChange={localOnly=>setOptions({localOnly})} label={t('localOnly')}/></section>
   <PerformanceMonitor active={open}/>
  </div></div>;
 return <>
  <AnimatePresence initial={false}>{open&&<motion.aside initial={{width:0,opacity:0}} animate={{width:308,opacity:1}} exit={{width:0,opacity:0}} transition={reduced?{duration:.06}:motionTokens.spring.sidebar} className="hidden shrink-0 overflow-hidden border-s border-stroke bg-surface xl:block"><div className="h-full w-[308px]">{inner}</div></motion.aside>}</AnimatePresence>
  <AnimatePresence>{open&&<div className="fixed inset-0 z-50 xl:hidden"><motion.div className="absolute inset-0 bg-black/55" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} onClick={()=>setOpen(false)} aria-hidden/><motion.aside className="absolute inset-x-0 bottom-0 h-[min(76dvh,690px)] overflow-hidden rounded-t-xl border-t border-stroke bg-surface shadow-float" initial={{y:'100%'}} animate={{y:0}} exit={{y:'100%'}} transition={reduced?{duration:.08}:motionTokens.spring.sidebar}>{inner}</motion.aside></div>}</AnimatePresence>
 </>
}
