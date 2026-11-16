import {useEffect,useState} from 'react';
import {Image,Pause,Play,Square,Shuffle,Volume2,ExternalLink,RefreshCw} from 'lucide-react';
import {requestJSON} from '../lib/backend';
import {useApp} from '../store';

type Wallpaper={id:string;title:string;type:string;preview_available:boolean};
type Reply={capabilities:{family:string;supported:boolean;release:string};lively:{installed:boolean;license:string;official_url:string;path:string|null};library:Wallpaper[];processes:{pid:number;name:string;ram_mb:number|null;cpu_percent:number|null}[];autopause:string};

export function Wallpapers(){
 const ar=useApp(s=>s.language)==='ar';
 const [data,setData]=useState<Reply|null>(null);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [volume,setVolume]=useState(40);
 async function refresh(){
  try{setData(await requestJSON<Reply>('/v1/wallpapers/status'));setError('')}
  catch(e){setError(e instanceof Error?e.message:String(e))}
 }
 useEffect(()=>{void refresh()},[]);
 async function addLocal(){
  if(busy)return;setBusy(true);setError('');
  try{
   const answer=await requestJSON<{status:string;verified:boolean}>('/v1/wallpapers/pick-local',{method:'POST'});
   if(answer.status==='command_sent')setError(ar?'بعت الملف المختار إلى Lively، بس تأكد إنه ظهر على سطح المكتب.':'Media sent to Lively; verify the wallpaper is visible.');
   await refresh();
  }catch(e){setError(e instanceof Error?e.message:String(e))}
  finally{setBusy(false)}
 }
 async function invoke(action:string,wallpaper_id?:string){
  if(busy)return;setBusy(true);setError('');
  try{
   const result=await requestJSON<{status:string;verified:boolean}>('/v1/wallpapers/action',{
    method:'POST',body:JSON.stringify({action,wallpaper_id,volume:action==='volume'?volume:undefined})
   });
   if(!result.verified)setError(ar?'بعت الأمر إلى Lively، لكن لازم تتأكد من ظهوره على سطح المكتب.':'Command sent to Lively; visible playback still needs confirmation.');
   await refresh();
  }catch(e){setError(e instanceof Error?e.message:String(e))}
  finally{setBusy(false)}
 }
 return <div className="barq-media" dir={ar?'rtl':'ltr'}>
  <header className="barq-media-head"><div><h2>{ar?'الخلفيات الحية':'Live Wallpapers'}</h2>
   <p>{ar?'التحكم في برنامج Lively الخارجي من داخل برق، من غير نسخ محركه.':'Control the separate Lively Wallpaper application from BARQ.'}</p></div>
   <span className="barq-chip">{data?.capabilities.release||'Windows'} · {data?.lively.license||'GPL-3.0 / MS-PL'}</span></header>
  {error&&<p className="barq-media-error" role="status">{error}</p>}
  {data&&!data.lively.installed&&<section className="barq-media-empty"><Image size={27}/><p>{ar?'Lively مش ظاهر في مسارات التثبيت المعروفة. نزّله من المصدر الرسمي بعد موافقتك، أو افتح نسختك المثبتة.':'Lively is not detected in standard install paths. You can install it from its official project.'}</p>
   <a href={data.lively.official_url} target="_blank" rel="noreferrer"><ExternalLink size={15}/>{ar?'الإصدار الرسمي':'Official releases'}</a></section>}
  {data?.lively.installed&&<>
   <div className="barq-media-toolbar">
    <button disabled={busy} onClick={()=>void invoke('show')}><Image size={16}/>{ar?'افتح Lively':'Open Lively'}</button>
    <button disabled={busy} onClick={()=>void addLocal()}>{ar?'أضف فيديو أو GIF من جهازك':'Add local video / GIF'}</button>
    <button disabled={busy} onClick={()=>void invoke('play')}><Play size={16}/>{ar?'تشغيل':'Play'}</button>
    <button disabled={busy} onClick={()=>void invoke('pause')}><Pause size={16}/>{ar?'إيقاف مؤقت':'Pause'}</button>
    <button disabled={busy} onClick={()=>void invoke('stop')}><Square size={16}/>{ar?'إيقاف الخلفية':'Stop'}</button>
    {data.capabilities.family!=='legacy'&&<button disabled={busy} onClick={()=>void invoke('random')}><Shuffle size={16}/>{ar?'عشوائي':'Random'}</button>}
    <label><Volume2 size={16}/><input type="range" min="0" max="100" value={volume} onChange={e=>setVolume(Number(e.target.value))} aria-label={ar?'مستوى الصوت':'Volume'}/>{volume}%</label>
    <button disabled={busy} onClick={()=>void invoke('volume')}>{ar?'تطبيق الصوت':'Apply volume'}</button>
    <button disabled={busy} onClick={()=>void refresh()} aria-label={ar?'تحديث':'Refresh'}><RefreshCw size={16}/></button>
   </div>
   <p className="barq-muted">{ar?'إيقاف الخلفية تلقائيًا وقت الألعاب أو البطارية بيتضبط من إعدادات Lively نفسه. افتح البرنامج واضبط قواعد الأداء.':'For fullscreen/battery auto-pause, configure Lively performance rules in its own settings.'}</p>
   <div className="barq-media-grid">
   {data.library.map(item=><article key={item.id} className="barq-wallpaper-card">
     <div className="barq-wallpaper-preview">{item.preview_available?<img src={'/v1/wallpapers/preview/'+encodeURIComponent(item.id)} alt={item.title} loading="lazy"/>:<Image size={30}/>}</div>
     <div className="barq-wallpaper-detail"><strong dir="auto">{item.title}</strong><small dir="auto">{item.type}</small>
      <button disabled={busy} onClick={()=>void invoke('apply',item.id)}>{ar?'تطبيق':'Apply'}</button></div>
    </article>)}
   </div>
   {!data.library.length&&<p className="barq-muted">{ar?'مكتبة Lively مش موجودة في المسار المعروف. افتح Lively وأضف الفيديو أو GIF من واجهته؛ مش هنجرب مسارات ملفات من غير موافقتك.':'No detected Lively library. Add a local video/GIF using the official Lively app.'}</p>}
   <section className="barq-media-metrics"><div><span>{ar?'عمليات Lively المرصودة':'Measured Lively processes'}</span><strong>{data.processes.length}</strong></div>
    <div><span>{ar?'ذاكرة عمليات Lively':'Lively RAM'}</span><strong>{data.processes.reduce((sum,p)=>sum+(p.ram_mb||0),0).toFixed(1)} MB</strong></div>
    <div><span>{ar?'استخدام CPU':'CPU usage'}</span><strong>{ar?'غير مقاس بعد':'Not sampled'}</strong></div></section>
  </>}
 </div>;
}
