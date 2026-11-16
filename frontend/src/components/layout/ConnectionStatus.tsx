import {useEffect,useState} from 'react';
import {Activity,RefreshCw} from 'lucide-react';
import {useApp} from '../../store';
import type {RouterProvider} from '../../lib/backend';
import {IconButton} from '../ui/IconButton';

type Connectivity={mode:string;cloud_connection:string;ollama:{enabled:boolean;reachable:boolean;models:string[];message:string}};
export function ConnectionStatus({providers,onModels}:{providers:RouterProvider[];onModels:()=>void}){
 const language=useApp(s=>s.language),streaming=useApp(s=>s.streaming),selected=useApp(s=>s.selectedModel),localOnly=useApp(s=>s.options.localOnly),[connectivity,setConnectivity]=useState<Connectivity|null>(null),[refreshing,setRefreshing]=useState(false);
 const load=async(force=false)=>{if(force)setRefreshing(true);try{const result=await fetch(`/v1/router/connectivity${force?'?refresh=true':''}`,{cache:'no-store'});if(result.ok)setConnectivity(await result.json() as Connectivity);else setConnectivity(null)}catch{setConnectivity(null)}finally{setRefreshing(false)}};
 useEffect(()=>{void load();const timer=setInterval(()=>void load(),15000);return()=>clearInterval(timer)},[]);
 const local=connectivity?.ollama.reachable&&!!connectivity.ollama.models.length;
 const cloudKeys=providers.filter(p=>p.enabled&&p.kind!=='local'&&p.configured);
 const verifiedCloud=cloudKeys.filter(p=>p.verified);
 const autoLocal=!!local&&selected==='auto'&&!localOnly&&connectivity?.mode==='auto';
 const preferLocal=localOnly||selected.startsWith('ollama/')||connectivity?.mode==='local'||connectivity?.cloud_connection==='suspected_offline';
 const enabled=preferLocal?(local?'local':'unavailable'):verifiedCloud.length?'verified':cloudKeys.length?'configured':local?'local':'unavailable';
 const text=autoLocal?(language==='ar'?'تخطيط محلي · سحابي احتياطي':'Local planning · cloud backup'):enabled==='local'?(connectivity?.cloud_connection==='suspected_offline'?(language==='ar'?'بدون إنترنت · Ollama':'Offline · Ollama'):(language==='ar'?'محلي · Ollama جاهز':'Local · Ollama ready')):enabled==='verified'?(language==='ar'?`سحابي · ${verifiedCloud.length} مُتحقَّق`:`Cloud · ${verifiedCloud.length} verified`):enabled==='configured'?(language==='ar'?`سحابي · ${cloudKeys.length} مفتاح غير مختبَر`:`Cloud · ${cloudKeys.length} configured (unchecked)`):(language==='ar'?'لا يوجد موديل جاهز':'No ready model');
 const statusColor=enabled==='local'||enabled==='verified'?'bg-success':enabled==='configured'?'bg-warning':'bg-danger';
 return <div className="status-wrap relative flex max-w-full items-center gap-1">
  <button type="button" className="focus-ring inline-flex items-center gap-2 rounded-full border border-stroke bg-elevated px-3 py-2 text-xs text-secondary" onClick={onModels} aria-label={language==='ar'?'افتح إعدادات النماذج':'Open model settings'} title={providers.map(p=>`${p.name}: ${p.kind==='local'?(p.ready?'Ready':p.status_message||'Not ready'):(p.verified?'API verified':p.status_message||'Needs API key')} (${p.remaining_today??'?'})`).join('\n')}><span className={`h-2 w-2 shrink-0 rounded-full ${statusColor}`}/><span className="hidden max-w-44 truncate sm:inline">{streaming?(language==='ar'?'جاري التوليد':'Generating'):text}</span><Activity size={15}/></button>
  <IconButton size="sm" className="!min-h-9 !min-w-9" label={language==='ar'?'تحديث حالة النماذج':'Refresh model status'} icon={<RefreshCw size={16} className={refreshing?'animate-spin':''}/>} onClick={()=>void load(true)} disabled={refreshing}/>
 </div>
}
