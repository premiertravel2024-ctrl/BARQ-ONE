import {useEffect, useRef, useState} from 'react';
import {Download, ExternalLink, Heart, Image, Layers, Pause, Play, Plus, RefreshCw, Search, Shuffle, Square, Volume2} from 'lucide-react';
import {requestJSON} from '../lib/backend';
import {useApp} from '../store';
import './wallpaperGallery.css';

type Wallpaper = {id: string; title: string; type: string; preview_available: boolean};
type Reply = {
  capabilities: {family: string; supported: boolean; release: string};
  lively: {installed: boolean; official_url: string};
  engine?: {integrated: boolean; supported: boolean; running: boolean; backend: string; wallpaper_id?: string};
  library: Wallpaper[];
  installer: 'idle' | 'running' | 'finished' | 'failed';
  can_install: boolean;
};
function Preview({item,native}:{item:Wallpaper;native:boolean}){const [failed,setFailed]=useState(false);const src='/v1/wallpapers/preview/'+encodeURIComponent(item.id);if(!item.preview_available||failed)return <Image size={50}/>;return native&&/^(mp4|webm)$/.test(item.type)?<video src={src+'#t=0.1'} muted playsInline preload="metadata" onError={()=>setFailed(true)}/>:<img alt="" src={src} loading="lazy" onError={()=>setFailed(true)}/>;}

type CommandResult = {status: string; verified?: boolean};

export function Wallpapers() {
  const ar = useApp(s => s.language) === 'ar';
  const [data, setData] = useState<Reply | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [volume, setVolume] = useState(40);
  const [installing, setInstalling] = useState(false);
  const pending = useRef(false);
  const [query,setQuery]=useState('');
  const [filter,setFilter]=useState<'all'|'video'|'gif'|'favorites'>('all');
  const [favorites,setFavorites]=useState<string[]>(()=>{
    try{const value:unknown=JSON.parse(localStorage.getItem('barq-wallpaper-favorites')||'[]');
      return Array.isArray(value)?value.filter((x):x is string=>typeof x==='string'):[]}catch{return []}
  });
  function toggleFavorite(id:string){
    const list=favorites.includes(id)?favorites.filter(x=>x!==id):[...favorites,id];
    setFavorites(list);try{localStorage.setItem('barq-wallpaper-favorites',JSON.stringify(list))}catch{}
  }
  function isGif(item:Wallpaper){return /gif/i.test(item.type)||/\.gif$/i.test(item.title)}
  function isVideo(item:Wallpaper){return /video|mp4|webm|^0$|^1$/i.test(item.type)||/\.(mp4|webm)$/i.test(item.title)}


  async function refresh() {
    const result = await requestJSON<Reply>('/v1/wallpapers/status?metrics=false');
    setData(result);
    setInstalling(result.installer === 'running');
    return result;
  }

  useEffect(() => {
    void refresh().catch(e => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(() => {
    if (!installing) return;
    let timer: number;
    let live = true;
    async function poll() {
      try {
        const result = await requestJSON<Reply>('/v1/wallpapers/status?metrics=false');
        if (!live) return;
        setData(result);
        if (result.installer !== 'running') {
          setInstalling(false);
          if (result.lively.installed) setNotice(ar ? 'الخلفيات جاهزة. اختار ملف من جهازك.' : 'Ready. Choose a wallpaper file.');
          else setError(ar ? 'التثبيت مخلصش بنجاح. راجع نافذة Windows وجرب تاني.' : 'Installation did not finish. Check the Windows installer and retry.');
          return;
        }
      } catch (e) {
        if (live) setError(e instanceof Error ? e.message : String(e));
      }
      if (live) timer = window.setTimeout(() => void poll(), 3000);
    }
    timer = window.setTimeout(() => void poll(), 1200);
    return () => { live = false; window.clearTimeout(timer); };
  }, [installing, ar]);

  async function operate(action: () => Promise<void>) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError('');
    setNotice('');
    try { await action(); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { pending.current = false; setBusy(false); }
  }

  function install() {
    void operate(async () => {
      const result = await requestJSON<CommandResult>('/v1/wallpapers/install', {method: 'POST'});
      if (result.status === 'running') setInstalling(true);
      else await refresh();
    });
  }

  function invoke(action: string, wallpaper_id?: string) {
    void operate(async () => {
      const result = await requestJSON<CommandResult>('/v1/wallpapers/action', {
        method: 'POST', body: JSON.stringify({action, wallpaper_id, volume: action === 'volume' ? volume : undefined}),
      });
      if (result.verified) setNotice(ar ? 'محرك خلفيات برق أكد تنفيذ الأمر.' : 'BARQ wallpaper engine confirmed the action.');
      else if (result.status === 'command_sent') setNotice(ar ? 'الأمر اتبعت لمشغّل الخلفيات.' : 'Command sent to the wallpaper player.');
      await refresh();
    });
  }

  function addLocal() {
    void operate(async () => {
      const result = await requestJSON<CommandResult>('/v1/wallpapers/pick-local', {method: 'POST'});
      if (result.status === 'cancelled') return;
      setNotice(ar ? 'تم استيراد الخلفية وتشغيلها داخل برق.' : 'Wallpaper imported and launched within BARQ.');
      await refresh();
    });
  }

  const ready = data?.engine ? data.engine.supported : data?.lively.installed;
  const list=(data?.library||[]).filter(item=>{
    const match=(item.title+' '+item.type).toLowerCase().includes(query.trim().toLowerCase());
    return match&&(filter==='all'||(filter==='favorites'?favorites.includes(item.id):filter==='gif'?isGif(item):isVideo(item)));
  });
  const featured=(data?.library||[]).find(x=>x.id===data?.engine?.wallpaper_id)||(data?.library||[])[0];
  return <div className="barq-media barq-wallpaper-studio" dir={ar?'rtl':'ltr'}>
   <header className="bws-hero">
    <div className="bws-hero-copy">
     <span className="bws-overline"><Layers size={16}/> BARQ WALLPAPER STUDIO</span>
     <h2>{ar?'مساحتك، مزاجك، خلفيتك':'Your space. Your atmosphere.'}</h2>
     <p>{ar?'اكتشف الخلفيات الحية اللي على جهازك، رتّب المفضلة، وشغّل اللي يعجبك في ثواني.':'Explore your local animated wallpapers, save favorites, and apply in one click.'}</p>
     <div className="bws-hero-actions">
       <button className="bws-main-btn" disabled={busy||!ready} onClick={addLocal}><Plus size={18}/>{ar?'أضف خلفية حية':'Add live wallpaper'}</button>
       <button disabled={busy} onClick={()=>void operate(async()=>{await refresh()})}><RefreshCw size={16}/>{ar?'تحديث المكتبة':'Refresh library'}</button>
     </div>
     {data?.engine&&<span className={'bws-engine-state'+(data.engine.running?' bws-active':'')}>{data.engine.running?(ar?'الخلفية شغالة حاليًا':'Wallpaper playing'):(ar?'محرك برق جاهز':'BARQ engine ready')}</span>}
    </div>
    <div className="bws-feature-preview" aria-hidden="true">
     {featured?<Preview item={featured} native={!!data?.engine}/>:<Image size={78}/>}
     <span className="bws-feature-badge">{ar?'خلفياتك الحية':'YOUR LIBRARY'}</span>
    </div>
   </header>
   {error&&<p className="barq-media-error" role="alert">{error}</p>}
   {notice&&<p className="bws-notice" role="status">{notice}</p>}
   {!data&&!error&&<p className="barq-muted" role="status">{ar?'بنفحص محرك الخلفيات…':'Checking wallpaper engine…'}</p>}
   {data&&!ready&&<section className="bws-setup">
     <Image size={28}/><div><strong>{ar?'المشغّل محتاج تجهيز':'Player setup required'}</strong>
     <p>{data.engine?(ar?'المحرك المدمج محتاج Windows 10 أو 11 وWebView2.':'The built-in engine needs Windows 10/11 and WebView2.'):(ar?'التوافق القديم يحتاج Lively.':'Legacy Windows requires Lively.')}</p></div>
     {!data.engine&&data.can_install&&<button disabled={busy||installing} onClick={install}><Download size={17}/>{installing?(ar?'جاري التثبيت…':'Installing…'):(ar?'تثبيت المشغّل':'Install player')}</button>}
     {!data.engine&&!data.can_install&&<a target="_blank" rel="noreferrer" href={data.lively.official_url}><ExternalLink size={17}/>{ar?'الموقع الرسمي':'Official download'}</a>}
    </section>}
   {data&&ready&&<>
    <section className="bws-discovery">
     <div className="bws-titlebar"><div><span>{ar?'مكتبتك':'YOUR COLLECTION'}</span><h3>{ar?'استكشف الخلفيات':'Explore wallpapers'}</h3></div>
      <small>{data.library.length} {ar?'خلفية':'wallpapers'}</small></div>
     <div className="bws-toolbar">
      <label className="bws-search"><Search size={18}/><input aria-label={ar?'بحث الخلفيات':'Search wallpapers'} value={query} onChange={e=>setQuery(e.target.value)} placeholder={ar?'ابحث عن خلفية...':'Search wallpapers...'}/></label>
      <div className="bws-tabs" role="group" aria-label={ar?'تصفية الخلفيات':'Filter wallpapers'}>
       {([['all',ar?'الكل':'All'],['video',ar?'فيديو':'Videos'],['gif','GIF'],['favorites',ar?'المفضلة':'Favorites']] as const).map(([key,label])=><button type="button" key={key} aria-pressed={filter===key} onClick={()=>setFilter(key)}>{label}</button>)}
      </div>
     </div>
     {list.length?<div className="bws-gallery">{list.map(item=><article key={item.id} className={'bws-wallpaper'+(data.engine?.wallpaper_id===item.id?' is-playing':'')}>
      <div className="bws-thumb"><Preview item={item} native={!!data.engine}/>
       <span className="bws-type">{isGif(item)?'GIF':isVideo(item)?'VIDEO':String(item.type).slice(0,12)}</span>
       <button type="button" className="bws-heart" aria-label={favorites.includes(item.id)?(ar?'إزالة من المفضلة':'Remove favorite'):(ar?'إضافة للمفضلة':'Add favorite')} aria-pressed={favorites.includes(item.id)} onClick={()=>toggleFavorite(item.id)}><Heart size={17} fill={favorites.includes(item.id)?'currentColor':'none'}/></button>
      </div>
      <div className="bws-wallpaper-text"><strong dir="auto">{item.title}</strong><small>{data.engine?.wallpaper_id===item.id&&data.engine.running?(ar?'قيد التشغيل':'Playing'):(ar?'من مكتبتك المحلية':'From local library')}</small>
       <button disabled={busy} onClick={()=>invoke('apply',item.id)}><Play size={15}/>{ar?'تطبيق الخلفية':'Apply wallpaper'}</button></div>
     </article>)}</div>:<div className="bws-empty"><Image size={30}/><strong>{data.library.length===0?(ar?'مكتبتك لسه فاضية':'Your library is empty'):(ar?'مفيش خلفيات مطابقة':'No matching wallpapers')}</strong><p>{ar?'ضيف ملف فيديو أو GIF من جهازك، أو غيّر البحث.':'Import a video or GIF, or adjust your filters.'}</p><button disabled={busy} onClick={addLocal}><Plus size={16}/>{ar?'إضافة خلفية':'Add wallpaper'}</button></div>}
    </section>
    <details className="bws-player-settings"><summary>{ar?'التحكم في تشغيل الخلفيات':'Playback controls'}</summary>
     <div className="bws-controls">
      <button disabled={busy} onClick={()=>invoke('play')}><Play size={16}/>{ar?'تشغيل':'Play'}</button>
      <button disabled={busy} onClick={()=>invoke('pause')}><Pause size={16}/>{ar?'إيقاف مؤقت':'Pause'}</button>
      <button disabled={busy} onClick={()=>invoke('stop')}><Square size={16}/>{ar?'إيقاف':'Stop'}</button>
      {data.capabilities.family!=='legacy'&&<button disabled={busy} onClick={()=>invoke('random')}><Shuffle size={16}/>{ar?'خلفية عشوائية':'Shuffle'}</button>}
      <label><Volume2 size={16}/><input type="range" min="0" max="100" value={volume} onChange={e=>setVolume(Number(e.target.value))} aria-label={ar?'الصوت':'Volume'}/>{volume}%</label>
      <button disabled={busy} onClick={()=>invoke('volume')}>{ar?'تطبيق الصوت':'Set volume'}</button>
      {!data.engine&&<button disabled={busy} onClick={()=>invoke('show')}><Image size={16}/>{ar?'فتح Lively':'Open Lively'}</button>}
     </div>
    </details>
   </>}
  </div>;
}

