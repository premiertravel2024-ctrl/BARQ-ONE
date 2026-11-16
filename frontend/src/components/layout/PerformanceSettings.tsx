import {useEffect,useState} from 'react';
import {Activity,RefreshCw} from 'lucide-react';
import {Button} from '../ui/Button';
import {useApp} from '../../store';
import {AdaptiveBrainSettings} from './AdaptiveBrainSettings';
type Stats={measured_responses:number;ttft_seconds:{median:number|null;p95:number|null};total_seconds:{median:number|null;p95:number|null};fallback_responses:number};
export function PerformanceSettings({active}:{active:boolean}){
 const language=useApp(s=>s.language),[data,setData]=useState<Stats|null>(null),[error,setError]=useState('');
 const reload=async()=>{try{const r=await fetch('/v1/performance',{cache:'no-store'});if(!r.ok)throw new Error(`HTTP ${r.status}`);setData(await r.json() as Stats);setError('')}catch(e){setError(e instanceof Error?e.message:'Unavailable')}};
 useEffect(()=>{if(!active)return;void reload();const timer=setInterval(()=>void reload(),12000);return()=>clearInterval(timer)},[active]);
 const metric=(n:number|null|undefined)=>typeof n==='number'?`${n.toFixed(2)}s`:'—';
 return <section className="space-y-4" aria-label={language==='ar'?'مراقبة الأداء':'Performance Monitor'}><div className="flex justify-between gap-2"><h3 className="flex items-center gap-2 text-sm font-semibold"><Activity size={17}/>{language==='ar'?'سرعة الاستجابة':'Response performance'}</h3><Button size="sm" variant="secondary" icon={<RefreshCw size={15}/>} onClick={()=>void reload()}>{language==='ar'?'تحديث':'Refresh'}</Button></div><div className="grid grid-cols-2 gap-3">{[[language==='ar'?'بداية الرد (وسيط)':'First token (median)',metric(data?.ttft_seconds.median)],[language==='ar'?'بداية الرد (95%)':'First token (p95)',metric(data?.ttft_seconds.p95)],[language==='ar'?'الردود المقاسة':'Measured replies',String(data?.measured_responses??'—')],[language==='ar'?'التحويلات':'Fallback replies',String(data?.fallback_responses??'—')]].map(([label,value])=><div key={label} className="rounded-xl border border-stroke bg-elevated p-3"><p className="text-xs text-secondary">{label}</p><p className="mt-2 text-lg font-semibold" dir="ltr">{value}</p></div>)}</div><p className="text-xs text-secondary">{language==='ar'?'القياسات تعتمد على ردود فعلية سابقة؛ مش اختبار سرعة مباشر للمزودين.':'Metrics are from past completed requests, not a live provider speed test.'}</p>{error&&<p role="alert" className="text-xs text-danger">{error}</p>}<AdaptiveBrainSettings active={active}/></section>
}
