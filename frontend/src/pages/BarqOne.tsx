import {useEffect,useState} from 'react';
import {Thermometer,MemoryStick,HardDrive,Activity,AudioLines,Cpu,Download,LayoutDashboard,LibraryBig,MessageSquare,Radio,Search,Settings2,Star,Terminal,Timer,Workflow,CircleDot,Package,Image,Shield,Headphones} from 'lucide-react';
import {requestJSON,type RouterProvider} from '../lib/backend';
import {useApp} from '../store';
import {getHandsFreeState} from '../components/chat/HandsFreeVoice';
import {Hologram} from '../components/chat/Hologram';
import {Modal} from '../components/ui/Modal';
import './barqOne.css';
import './barqMedia.css';
import {ResourceSaver} from './ResourceSaver';
import {Wallpapers} from './Wallpapers';
import {WatchTogether} from './WatchTogether';

export const sections=[
 ['center','مركز الأوامر','Command Center',LayoutDashboard],
 ['chat','المحادثة','BARQ Chat',MessageSquare],
 ['voice','المساعد الصوتي','Voice Assistant',Radio],
 ['mission','المهام','Mission Control',Workflow],
 ['library','مكتبة OpenHub','OpenHub Library',LibraryBig],
 ['installed','البرامج المثبّتة','Installed Software',Download],
 ['tools','النماذج والأدوات','AI Models & Tools',Cpu],
 ['monitor','مراقبة النظام','System Monitor',Activity],
 ['resources','توفير الموارد','Resource Saver',Shield],
 ['wallpapers','الخلفيات الحية','Live Wallpapers',Image],
 ['watch','غرفة المشاهدة','Watch Together',Radio],
 ['music','غرفة الموسيقى','Music Room',Headphones],
 ['automation','الأتمتة','Automation',Timer],
 ['settings','الإعدادات','Settings',Settings2],
] as const;
export type OnePage=typeof sections[number][0];
type Item={id:string;name:string;category:string;url:string;package:string|null;setup?:boolean;description_ar?:string;description_en?:string};
type Job={id:string;item:string;action:string;status:string;detail:string};
type Inventory={packages:Record<string,string>;setups?:Record<string,string>;checked:boolean};
type Catalog={items:Item[];winget:boolean;can_setup?:boolean;can_sensors?:boolean};
type Metadata={description?:string;license?:string;latest?:string;archived?:boolean};
type Monitor={hardware:{cpu_load_percent?:number;ram_total_bytes?:number;ram_available_bytes?:number};sensors?:{cpu_c?:number;gpu_c?:number;gpu_load_percent?:number};disk_percent?:number;processes?:Array<{name:string;rss:number}>};
const categoryLabels:Record<string,string>={AI:'ذكاء اصطناعي',Control:'التحكم',Windows:'ويندوز',Developer:'تطوير',Downloads:'تنزيلات',Multimedia:'وسائط',Design:'تصميم',Networking:'شبكات',Security:'أمان',Monitoring:'مراقبة',Productivity:'إنتاجية'};
function useVoice(){
 const [voice,setVoice]=useState(getHandsFreeState);
 useEffect(()=>{
  const listener=()=>setVoice(getHandsFreeState());
  window.addEventListener('barq-handsfree-state',listener);
  return()=>window.removeEventListener('barq-handsfree-state',listener);
 },[]);
 return voice;
}
function favorites(){
 try{const data:unknown=JSON.parse(localStorage.getItem('barq-openhub-favorites')||'[]');return Array.isArray(data)?data.filter((item):item is string=>typeof item==='string'):[];}
 catch{return [];}
}
const jobLabels:Record<string,string>={queued:'في الطابور',running:'قيد التنفيذ',verified:'تم التحقق',failed:'تعذّر التنفيذ',interrupted:'انقطع',needs_review:'يحتاج مراجعة'};
function jobLabel(job:Job,ar:boolean){
 if(job.status==='verified')return ['source','download'].includes(job.action)?(ar?'تم التحميل فقط':'Downloaded only'):(ar?'تم التثبيت والتحقق':'Installation verified');
 return ar?jobLabels[job.status]||job.status:job.status;
}
function OpenHub({mode}:{mode:'library'|'installed'|'tools'}){
 const ar=useApp(s=>s.language)==='ar';
 const [catalog,setCatalog]=useState<Catalog>();
 const [inventory,setInventory]=useState<Inventory>({packages:{},checked:false});
 const [jobs,setJobs]=useState<Job[]>([]);
 const [query,setQuery]=useState('');
 const [category,setCategory]=useState('');
 const [onlyFavorites,setOnlyFavorites]=useState(false);
 const [stars,setStars]=useState(favorites);
 const [selected,setSelected]=useState<string[]>([]);
 const [detail,setDetail]=useState<Item>();
 const [metadata,setMetadata]=useState<Metadata>();
 const [metadataError,setMetadataError]=useState(false);
 const [approval,setApproval]=useState<'install'|'upgrade'|'download'|'source'|'setup'>();
 const [busy,setBusy]=useState(false);
 const [autoTools,setAutoTools]=useState<boolean>();
 const [error,setError]=useState('');
 useEffect(()=>{
  let live=true;
  const poll=()=>{if(document.hidden)return;void Promise.all([
   requestJSON<{jobs:Job[]}>('/v1/openhub/jobs'),requestJSON<Inventory>('/v1/openhub/installed'),
  ]).then(([history,installed])=>{if(live){setJobs(history.jobs);setInventory(installed);}}).catch(()=>{});};
  void requestJSON<Catalog>('/v1/openhub/catalog').then(data=>{if(live)setCatalog(data);})
   .catch(()=>{if(live)setError(ar?'تعذّر تحميل OpenHub.':'OpenHub could not load.');});
  if(mode==='tools')void requestJSON<{enabled:boolean}>('/v1/openhub/auto-tools').then(r=>{if(live)setAutoTools(r.enabled)}).catch(()=>{});
  poll();const timer=window.setInterval(poll,2500);
  return()=>{live=false;window.clearInterval(timer);};
 },[ar,mode]);
 useEffect(()=>{setSelected([]);setCategory('');},[mode]);
 useEffect(()=>{
  if(!detail)return;
  const controller=new AbortController();
  setMetadata(undefined);setMetadataError(false);
  void requestJSON<Metadata>('/v1/openhub/details?item='+encodeURIComponent(detail.id),{signal:controller.signal})
   .then(setMetadata).catch(()=>{if(!controller.signal.aborted)setMetadataError(true);});
  return()=>controller.abort();
 },[detail]);
 const version=(item:Item)=>item.package?inventory.packages[item.package.toLowerCase()]:inventory.setups?.[item.id];
 const items=(catalog?.items||[]).filter(item=>mode==='installed'?version(item)!==undefined:mode==='tools'?['AI','Control','Monitoring'].includes(item.category):true);
 const categories=[...new Set(items.map(item=>item.category))];
 const shown=items.filter(item=>(!category||item.category===category)&&(!onlyFavorites||stars.includes(item.id))&&
  (item.name+' '+item.id+' '+(item.description_ar||'')+' '+(item.description_en||'')).toLowerCase().includes(query.trim().toLowerCase()));
 const chosen=items.filter(item=>selected.includes(item.id));
 function star(id:string){
  const next=stars.includes(id)?stars.filter(x=>x!==id):[...stars,id];setStars(next);
  try{localStorage.setItem('barq-openhub-favorites',JSON.stringify(next));}catch{/* Private browsing. */}
 }
 async function refresh(){
  setBusy(true);setError('');
  try{setInventory(await requestJSON<Inventory>('/v1/openhub/installed/refresh',{method:'POST'}));}
  catch{setError(ar?'تعذّر تحديث قائمة WinGet.':'WinGet inventory refresh failed.');}
  finally{setBusy(false);}
 }
 async function enqueue(action=approval,items=chosen){
  if(!action||!items.length)return;
  setBusy(true);setError('');
  try{
   await requestJSON('/v1/openhub/jobs',{method:'POST',body:JSON.stringify({items:items.map(i=>i.id),action,confirmed:true})});
   setSelected([]);setApproval(undefined);
   setJobs((await requestJSON<{jobs:Job[]}>('/v1/openhub/jobs')).jobs);
  }catch(e){setError(e instanceof Error?e.message:String(e));setApproval(undefined);}
  finally{setBusy(false);}
 }
 return <>
  <div className="one-toolbar">
   <label><Search size={17}/><input aria-label={ar?'البحث في OpenHub':'Search OpenHub'} placeholder={ar?'ابحث بالاسم أو المستودع':'Search by name or repository'} value={query} onChange={e=>setQuery(e.target.value)}/></label>
   <select aria-label={ar?'الفئة':'Category'} value={category} onChange={e=>setCategory(e.target.value)}>
    <option value="">{ar?'كل الفئات':'All categories'}</option>
    {categories.map(c=><option key={c} value={c}>{ar?categoryLabels[c]:c}</option>)}
   </select>
   <button type="button" aria-pressed={onlyFavorites} onClick={()=>setOnlyFavorites(!onlyFavorites)}><Star size={16}/>{ar?'المفضلة':'Favorites'}</button>
   {mode==='tools'&&autoTools!==undefined&&<label className="one-auto-tools"><input type="checkbox" checked={autoTools} disabled={busy} onChange={async e=>{
    setBusy(true);setError('');
    try{const r=await requestJSON<{enabled:boolean}>('/v1/openhub/auto-tools',{method:'POST',body:JSON.stringify({enabled:e.target.checked})});setAutoTools(r.enabled);}
    catch{setError(ar?'تعذّر حفظ إعداد أدوات البناء.':'Could not save automatic tools setting.');}finally{setBusy(false);}
   }}/>{ar?'تجهيز أدوات البناء المعتمدة تلقائيًا':'Set up tools automatically for approved builds'}</label>}
   <button type="button" disabled={!catalog?.winget||busy} onClick={()=>void refresh()}>{ar?'فحص البرامج المثبّتة':'Scan installed software'}</button>
   {!!chosen.length&&mode!=='installed'&&<button type="button" disabled={busy} onClick={()=>setApproval('download')}><Download size={16}/>{ar?'تنزيل المحدد':'Download selection'} ({chosen.length})</button>}
   {!!chosen.length&&<button type="button" disabled={busy} onClick={()=>setApproval(mode==='installed'?'upgrade':'install')}><Download size={16}/>{mode==='installed'?(ar?'تحديث المحدد':'Upgrade selection'):(ar?'تثبيت المحدد':'Install selection')} ({chosen.length})</button>}
  </div>
  {error&&<p className="one-error" role="alert">{error}</p>}
  {catalog&&!catalog.winget&&<p className="one-muted">{ar?'التثبيت من OpenHub يحتاج WinGet على Windows.':'OpenHub installation requires WinGet on Windows.'}</p>}
  {catalog&&mode==='installed'&&!inventory.checked&&<p className="one-muted">{ar?'اضغط فحص لعرض الإصدارات المسجّلة في WinGet.':'Scan to see versions registered with WinGet.'}</p>}
  {catalog&&mode!=='installed'&&!shown.length&&<p className="one-muted">{ar?'مفيش نتائج مطابقة.':'No matching entries.'}</p>}
  <div className="one-catalog">
   {shown.map(item=><article key={item.id} className="one-surface one-tool">
     <div className="one-tool-heading"><Terminal size={17}/><button type="button" aria-pressed={stars.includes(item.id)} aria-label={ar?'المفضلة '+item.name:'Favorite '+item.name} onClick={()=>star(item.id)}><Star size={17} fill={stars.includes(item.id)?'currentColor':'none'}/></button></div>
     <h2 dir="auto">{item.name}</h2>
     <p className="one-tool-description" dir={ar?'rtl':'ltr'}>{(ar?item.description_ar:item.description_en)||(ar?'أداة مفتوحة المصدر. افتح التفاصيل لمعرفة معلومات المستودع.':'Open-source project. See details for repository information.')}</p>
     <p className="one-muted one-tool-meta">{ar?categoryLabels[item.category]:item.category} · {version(item)||(item.package?'WinGet':ar?'المصدر الرسمي':'Upstream source')}</p>
     <div className="one-tool-actions"><button type="button" className="one-download" disabled={busy} onClick={()=>void enqueue(item.setup?'setup':item.package?'install':'source',[item])}><Download size={15}/>{item.setup||item.package?(ar?'تنزيل وتثبيت':'Download & install'):(ar?'المصدر فقط':'Source only')}</button><button type="button" onClick={()=>setDetail(item)}>{ar?'التفاصيل':'Details'}</button>
     {item.package&&catalog?.winget&&(mode==='installed'||version(item)===undefined)&&<label><input type="checkbox" checked={selected.includes(item.id)} disabled={selected.length>=10&&!selected.includes(item.id)} onChange={e=>setSelected(e.target.checked?[...selected,item.id]:selected.filter(id=>id!==item.id))}/>{ar?'اختيار':'Select'}</label>}</div>
    </article>)}
  </div>
  {mode==='installed'&&!!jobs.length&&<section className="one-surface one-job-list"><h2>{ar?'طابور التثبيت والسجل':'Queue and installation history'}</h2>
   {jobs.map(job=><div key={job.id} className="one-line"><span dir="auto">{catalog?.items.find(i=>i.id===job.item)?.name||job.item}</span><span data-status={job.status}>{jobLabel(job,ar)}</span><div className="one-job-detail">{['source','download'].includes(job.action)&&catalog?.items.some(i=>i.id===job.item&&(i.setup||i.package))&&<button type="button" disabled={busy} onClick={()=>{const item=catalog.items.find(i=>i.id===job.item)!;void enqueue(item.setup?'setup':'install',[item]);}}>{ar?'تثبيت الأداة الآن':'Install tool now'}</button>}<small dir="auto">{job.detail}</small>
    {job.status==='verified'&&job.action==='source'&&<a href={'/v1/openhub/jobs/'+job.id+'/file'} download>{ar?'حفظ ZIP':'Save ZIP'}</a>}
    {job.status==='verified'&&job.action==='download'&&<button type="button" onClick={()=>void requestJSON('/v1/openhub/jobs/'+job.id+'/folder',{method:'POST'}).catch(()=>setError(ar?'تعذّر فتح المجلد.':'Could not open folder.'))}>{ar?'فتح المجلد':'Open folder'}</button>}
   </div></div>)}
  </section>}
  <Modal open={!!detail} title={detail?.name||''} onClose={()=>setDetail(undefined)}>
   {detail&&<p className="one-tool-description one-details-summary" dir={ar?'rtl':'ltr'}>{ar?detail.description_ar:detail.description_en}</p>}
   {metadata?.description&&<p dir="auto">{metadata.description}</p>}
   {metadataError&&<p role="status">{ar?'تعذّر التحقق من بيانات المستودع حاليًا.':'Upstream metadata could not be verified.'}</p>}
   {!metadata&&!metadataError&&<p role="status">{ar?'براجع المستودع الرسمي…':'Checking upstream metadata…'}</p>}
   {metadata&&<dl className="one-details"><dt>{ar?'الترخيص':'License'}</dt><dd>{metadata.license&&metadata.license!=='NOASSERTION'?metadata.license:'—'}</dd>
   <dt>{ar?'آخر إصدار منشور':'Latest published release'}</dt><dd>{metadata.latest||'—'}</dd></dl>}
   {detail&&<div className="one-detail-actions"><button className="one-confirm" type="button" disabled={busy} onClick={()=>void enqueue('source',[detail])}><Download size={15}/>{ar?'تنزيل ZIP للمصدر':'Download source ZIP'}</button>
    {detail.setup&&(catalog?.can_setup||catalog?.can_sensors&&detail.id==='librehardwaremonitor/librehardwaremonitor')&&<button className="one-confirm" type="button" disabled={busy} onClick={()=>{setSelected([detail.id]);setDetail(undefined);setApproval('setup')}}>{ar?'تجهيز الأداة':'Set up tool'}</button>}
    {detail.package&&catalog?.winget&&<button className="one-confirm" type="button" disabled={busy} onClick={()=>{setSelected([detail.id]);setDetail(undefined);setApproval(version(detail)?'upgrade':'install')}}>{version(detail)?(ar?'تحديث':'Upgrade'):(ar?'تثبيت من OpenHub':'Install from OpenHub')}</button>}
   </div>}
  </Modal>
  <Modal open={!!approval} title={ar?'مراجعة طلب OpenHub':'Review OpenHub request'} onClose={()=>{if(!busy)setApproval(undefined);}}
   footer={<button className="one-confirm" type="button" disabled={busy} onClick={()=>void enqueue()}>{ar?'تأكيد':'Confirm'}</button>}>
   <p>{approval==='setup'?(ar?'تجهيز الأداة والتحقق من تثبيتها':'Set up the tool and verify installation'):approval==='upgrade'?(ar?'تحديث الحزم المحددة عبر WinGet':'Upgrade the selected WinGet packages'):approval==='download'?(ar?'تنزيل حزم التثبيت من WinGet':'Download the selected WinGet installers'):(ar?'تثبيت الحزم المحددة عبر WinGet':'Install the selected WinGet packages')}</p>
   <ul>{chosen.map(item=><li key={item.id} dir="auto">{item.name}{item.package?' · '+item.package:''}</li>)}</ul>
  </Modal>
 </>;
}

function ProviderList({providers,onSettings}:{providers:RouterProvider[];onSettings:()=>void}){
 const ar=useApp(s=>s.language)==='ar';
 return <section className="one-surface">
  <div className="one-section-head"><h2>{ar?'مزودو النماذج':'Model providers'}</h2><button type="button" onClick={onSettings}>{ar?'الإعدادات':'Settings'}</button></div>
  <div className="one-provider-list">{providers.map(provider=><div className="one-line" key={provider.name}>
   <span>{provider.name}</span><span data-status={provider.ready?'verified':undefined}>{provider.ready?(ar?'جاهز':'Ready'):provider.configured?(ar?'مُعدّ':'Configured'):(ar?'غير مُعدّ':'Unconfigured')}</span>
  </div>)}</div>
 </section>;
}

function RuntimeTools(){
 const ar=useApp(s=>s.language)==='ar';
 const [tools,setTools]=useState<Array<{name:string;detected:boolean}>>();
 const [error,setError]=useState(false);
 async function inspect(signal?:AbortSignal){
  setError(false);
  try{const data=await requestJSON<{tools:Array<{name:string;detected:boolean}>}>('/v1/openhub/runtime',{signal});if(!signal?.aborted)setTools(data.tools);}
  catch{if(!signal?.aborted)setError(true);}
 }
 useEffect(()=>{const controller=new AbortController();void inspect(controller.signal);return()=>controller.abort();},[]);
 return <section className="one-surface">
  <div className="one-section-head"><h2>{ar?'أدوات الجهاز':'Detected tools'}</h2><button type="button" onClick={()=>void inspect()}>{ar?'إعادة الفحص':'Scan again'}</button></div>
  {error&&<p role="alert">{ar?'تعذّر فحص الأدوات.':'Tool detection unavailable.'}</p>}
  {tools?.map(tool=><div className="one-line" key={tool.name}><span>{tool.name}</span>
   <span>{tool.detected?(ar?'تم العثور عليها':'Detected'):(ar?'غير مكتشفة':'Undetected')}</span></div>)}
 </section>;
}

function MonitorPanel({full=false}:{full?:boolean}){
 const ar=useApp(s=>s.language)==='ar';
 const [data,setData]=useState<Monitor>();
 const [history,setHistory]=useState<Monitor[]>([]);
 const [error,setError]=useState(false);
 const [notice,setNotice]=useState('');
 const [busy,setBusy]=useState(false);
 const [updated,setUpdated]=useState<Date>();
 async function action(path:string,body?:object){
  setBusy(true);setNotice('');
  try{
   const response=await requestJSON<{message?:string}>(path,{method:'POST',...(body?{body:JSON.stringify(body)}:{})});
   setNotice(response.message||(ar?'طلب التجهيز في الطابور. تابع النتيجة في البرامج المثبّتة.':'Setup queued. Check installation history.'));
  }catch(e){setNotice(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
 }
 useEffect(()=>{
  let stopped=false,pending=false;
  const controller=new AbortController();
  const poll=()=>{
   if(stopped||pending||document.hidden)return;pending=true;
   void requestJSON<Monitor>('/v1/openhub/monitor',{signal:controller.signal})
    .then(value=>{if(!stopped){setData(value);setHistory(old=>[...old.slice(-29),value]);setUpdated(new Date());setError(false);}})
    .catch(()=>{if(!stopped)setError(true);}).finally(()=>{pending=false;});
  };
  poll();const timer=window.setInterval(poll,7000);
  return()=>{stopped=true;controller.abort();window.clearInterval(timer);};
 },[]);
 const memory=(v?:Monitor)=>{
  const total=v?.hardware?.ram_total_bytes,available=v?.hardware?.ram_available_bytes;
  return typeof total==='number'&&total>0&&typeof available==='number'?100*(total-available)/total:undefined;
 };
 const metrics:Array<{label:string;unit:string;read:(v?:Monitor)=>number|undefined;icon:typeof Cpu}>=[
  {label:ar?'المعالج':'CPU',unit:'%',read:v=>v?.hardware?.cpu_load_percent,icon:Cpu},
  {label:ar?'حرارة المعالج':'CPU temperature',unit:'°C',read:v=>v?.sensors?.cpu_c,icon:Thermometer},
  {label:ar?'كارت الشاشة':'GPU',unit:'%',read:v=>v?.sensors?.gpu_load_percent,icon:Activity},
  {label:ar?'حرارة كارت الشاشة':'GPU temperature',unit:'°C',read:v=>v?.sensors?.gpu_c,icon:Thermometer},
  {label:ar?'الذاكرة':'Memory',unit:'%',read:memory,icon:MemoryStick},
  {label:ar?'مساحة القرص المستخدمة':'Disk space used',unit:'%',read:v=>v?.disk_percent,icon:HardDrive},
 ];
 return <section className="one-surface one-telemetry" dir={ar?'rtl':'ltr'}>
  <div className="one-section-head"><div><p className="one-eyebrow">BARQ / SYSTEM VITALS</p><h2>{ar?'نبض الجهاز':'System vitals'}</h2></div>
   <span className="one-telemetry-status" data-stale={error}>{error?(ar?'انقطع التحديث':'Update unavailable'):updated?(ar?'قراءات مباشرة':'Live readings'):(ar?'جاري قراءة الجهاز…':'Reading sensors…')}</span></div>
  <div className="one-vitals-grid">
   {metrics.map(({label,unit,read,icon:Icon})=>{
    const value=read(data),valid=!error&&typeof value==='number'&&Number.isFinite(value);
    const values=history.map(read);
    // Missing samples split the trace; no fabricated values or line across a gap.
    const points=values.map((v,i)=>typeof v==='number'&&Number.isFinite(v)?`${i===0||typeof values[i-1]!=='number'?'M':'L'}${i*240/29},${48-Math.min(125,Math.max(0,v))*44/125}`:'').join(' ');
    return <article className="one-vital" key={label}>
     <div><span>{label}</span><Icon size={17}/></div>
     <strong dir="ltr">{valid?Math.round(value):'—'}<small>{unit}</small></strong>
     <svg viewBox="0 0 240 52" preserveAspectRatio="none" aria-hidden="true"><path d={error?'':points}/></svg>
     <p>{valid?(unit==='°C'?(ar?'قراءة الحساس':'Sensor reading'):(ar?'القراءة الحالية':'Current reading')):(ar?'القراءة غير متاحة':'Reading unavailable')}</p>
    </article>;
   })}
  </div>
  <div className="one-telemetry-foot"><span>{updated?(ar?'آخر تحديث: ':'Updated: ')+updated.toLocaleTimeString(ar?'ar-EG':'en-US'):'—'}</span><span>{ar?'آخر ٣٠ قراءة • تحديث كل ٧ ثوانٍ':'Last 30 samples • every 7 seconds'}</span></div>
  {!error&&data&&data.sensors?.cpu_c==null&&<div className="one-sensor-help">
   <div><strong>{ar?'وصّل حساسات الحرارة':'Connect temperature sensors'}</strong><p>{ar?'لو LibreHardwareMonitor بيعرض CPU Package عندك، افتح Options > Remote Web Server > Run مرة واحدة وخليه شغال. برق هيستخدم نفس القراءة محليًا وبسرعة، من غير إعادة تثبيت أو طلب صلاحية كل مرة.':'If LibreHardwareMonitor already shows CPU Package, enable Options > Remote Web Server > Run once. BARQ reads that local sensor feed without restarting a hardware driver for every answer.'}</p></div>
   <button type="button" disabled={busy} onClick={()=>void action('/v1/openhub/jobs',{items:['librehardwaremonitor/librehardwaremonitor'],action:'setup',confirmed:true})}>{ar?'تجهيز الحساسات':'Set up sensors'}</button>
   <button type="button" disabled={busy} onClick={()=>void action('/v1/openhub/monitor/elevate')}>{ar?'تشغيل الحساسات بصلاحية مسؤول':'Run sensors as administrator'}</button>
  </div>}
  {notice&&<p role="status" dir="auto" className="one-muted">{notice}</p>}
  {full&&<div className="one-monitor-extra">
   <button type="button" disabled={busy} onClick={()=>void action('/v1/openhub/monitor/fps')}>{ar?'قياس FPS':'Measure FPS'}</button>
   {!!data?.processes?.length&&<div><h2>{ar?'البرامج الأكثر استخدامًا للذاكرة':'Processes using the most memory'}</h2>
    {data.processes.map((process,index)=><div key={process.name+index} className="one-line"><span>{process.name}</span><span dir="ltr">{Math.round(process.rss/1048576)} MB</span></div>)}</div>}
  </div>}
 </section>;
}

function Mission(){
 const ar=useApp(s=>s.language)==='ar';
 const messages=useApp(s=>s.chats.find(chat=>chat.id===s.activeId)?.messages);
 const voice=useVoice();
 const missions=(messages||[]).filter(m=>m.agentTask).slice(-8).reverse();
 return <section className="one-surface"><h2>{ar?'المهام الأخيرة في المحادثة':'Recent missions in this chat'}</h2>
  {voice.task&&<p dir="auto" role="status">{voice.task.message}</p>}
  {missions.length?missions.map(m=><div className="one-line" key={m.id}><span dir="auto">{m.agentTask?.goal}</span><span data-status={m.agentTask?.status}>{m.agentTask?.status}</span></div>)
   :<p className="one-muted">{ar?'لسه مفيش مهام مسجلة في المحادثة دي.':'No missions recorded in this chat yet.'}</p>}
 </section>;
}

function OverviewSignals({providers,onTools}:{providers:RouterProvider[];onTools:()=>void}){
 const ar=useApp(s=>s.language)==='ar',voice=useVoice();
 const [jobs,setJobs]=useState<Job[]>([]);
 const [metrics,setMetrics]=useState<{measured_responses:number;fallback_responses:number;total_seconds:{median:number|null}}>();
 useEffect(()=>{
  let live=true;
  function poll(){
   if(document.hidden)return;
   void requestJSON<{jobs:Job[]}>('/v1/openhub/jobs').then(r=>{if(live)setJobs(r.jobs)}).catch(()=>{});
   void requestJSON<NonNullable<typeof metrics>>('/v1/performance').then(r=>{if(live)setMetrics(r)}).catch(()=>{});
  }
  poll();const interval=setInterval(poll,5000);return()=>{live=false;clearInterval(interval);};
 },[]);
 const signal=[{name:ar?'جاهزية المزودين':'Provider readiness',count:providers.filter(p=>p.ready).length,total:providers.length},{name:ar?'التنزيلات النشطة':'Active downloads',count:jobs.filter(j=>j.status==='queued'||j.status==='running').length,total:jobs.length}];
 return <>
  <aside className="one-surface one-signals" dir={ar?'rtl':'ltr'}>
   <div className="one-section-head"><h2>{ar?'حالة التشغيل':'Operations status'}</h2><Activity size={15}/></div>
   <div className="one-live-indicator"><CircleDot size={13}/>{voice.active?(ar?'الجلسة الصوتية متصلة':'Voice session connected'):(ar?'الجلسة الصوتية متوقفة':'Voice session idle')}</div>
   {signal.map(({name,count,total})=><div className="one-signal" key={name}><div><span>{name}</span><strong dir="ltr">{total?count+' / '+total:'—'}</strong></div><progress max={total||1} value={count} aria-label={name}/></div>)}
   <div className="one-section-head"><h2>{ar?'آخر عمليات الأدوات':'Recent tool jobs'}</h2><button type="button" onClick={onTools}><Package size={15}/></button></div>
   {jobs.length?jobs.slice(0,3).map(j=><div className="one-line" key={j.id}><span dir="auto">{j.item.split('/').at(-1)}</span><span data-status={j.status}>{jobLabel(j,ar)}</span></div>):<p className="one-muted">{ar?'الطابور فاضي':'Queue is empty'}</p>}
  </aside>
  <div className="one-kpi-group" dir={ar?'rtl':'ltr'}>
   <section className="one-surface"><h2>{ar?'الردود المقاسة':'Measured replies'}</h2><strong>{metrics?.measured_responses??'—'}</strong></section>
   <section className="one-surface"><h2>{ar?'زمن الرد الوسيط':'Median response time'}</h2><strong dir="ltr">{metrics?.total_seconds.median==null?'—':metrics.total_seconds.median.toFixed(2)+' s'}</strong></section>
   <section className="one-surface"><h2>{ar?'الردود اللي احتاجت مزوّد بديل':'Fallback replies'}</h2><strong>{metrics?.fallback_responses??'—'}</strong></section>
  </div>
 </>;
}

type Props={page:Exclude<OnePage,'chat'|'settings'>;providers:RouterProvider[];onVoice:()=>void;
 onNavigate:(page:OnePage)=>void;onModels:()=>void;onAssistantSettings:()=>void;onQuick:(command:string)=>void};
export function BarqOne({page,providers,onVoice,onNavigate,onModels,onAssistantSettings,onQuick}:Props){
 const ar=useApp(s=>s.language)==='ar';
 const title=sections.find(([key])=>key===page);
 return <section className="one-page">
  <header className="one-page-head"><div><h1>{title?.[ar?1:2]}</h1></div>
   {page==='center'&&<button type="button" onClick={()=>onNavigate('voice')}><AudioLines size={17}/>{ar?'المساعد الصوتي':'Voice assistant'}</button>}</header>
  {page==='center'&&<>
   <div className="one-quick-ribbon" aria-label={ar?'أوامر سريعة':'Quick commands'}>
    {(ar?['افتح كروم','حرارة المعالج وكارت الشاشة','اقرأ النافذة الحالية']:['Open Chrome','CPU and GPU temperature','Read the current screen']).map(command=><button type="button" key={command} onClick={()=>onQuick(command)}><Terminal size={14}/>{command}</button>)}
   </div>
   <div className="one-dashboard" dir="ltr">
    <MonitorPanel/>
    <OverviewSignals providers={providers} onTools={()=>onNavigate('library')}/>
   </div>
   <Mission/>
  </>}
  {page==='voice'&&<Hologram onStart={onVoice}/>}
  {page==='mission'&&<Mission/>}
  {page==='monitor'&&<MonitorPanel full/>}
  {page==='resources'&&<ResourceSaver/>}
  {page==='wallpapers'&&<Wallpapers/>}
  {page==='watch'&&<WatchTogether mode="video"/>}
  {page==='music'&&<WatchTogether mode="music"/>}
  {page==='automation'&&<section className="one-surface"><h2>{ar?'الروتينات والتذكيرات':'Routines and reminders'}</h2>
   <button type="button" onClick={onAssistantSettings}><Settings2 size={17}/>{ar?'إعدادات المساعد الشخصي':'Personal assistant settings'}</button>
  </section>}
  {page==='tools'&&<div className="one-panels"><ProviderList providers={providers} onSettings={onModels}/><RuntimeTools/></div>}
  {(page==='tools'||page==='library'||page==='installed')&&<OpenHub mode={page}/>}
 </section>;
}
