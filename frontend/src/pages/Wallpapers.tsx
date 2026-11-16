import {useEffect, useRef, useState} from 'react';
import {Download, ExternalLink, Image, Pause, Play, Plus, RefreshCw, Shuffle, Square, Volume2} from 'lucide-react';
import {requestJSON} from '../lib/backend';
import {useApp} from '../store';

type Wallpaper = {id: string; title: string; type: string; preview_available: boolean};
type Reply = {
  capabilities: {family: string; supported: boolean; release: string};
  lively: {installed: boolean; official_url: string};
  engine?: {integrated: boolean; supported: boolean; running: boolean; backend: string; wallpaper_id?: string};
  library: Wallpaper[];
  installer: 'idle' | 'running' | 'finished' | 'failed';
  can_install: boolean;
};
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
  return <div className="barq-media" dir={ar ? 'rtl' : 'ltr'}>
    {data?.engine?.supported && <section className="barq-media-panel">
      <Image size={28} aria-hidden="true"/>
      <h2>{ar ? 'محرك الخلفيات الحية المدمج' : 'Built-in live wallpaper engine'}</h2>
      <p className="barq-muted">{ar ? 'شغّل فيديو أو GIF كخلفية من داخل برق من غير تنزيل أو تثبيت Lively. ملفاتك بتفضل على جهازك.' : 'Run videos or GIFs as wallpapers directly from BARQ; no separate Lively installation. Your files stay local.'}</p>
      <span className="barq-chip">{data.engine.running ? (ar ? 'الخلفية شغالة' : 'Wallpaper running') : (ar ? 'جاهز للتشغيل' : 'Ready to play')}</span>
    </section>}
    {error && <p className="barq-media-error" role="alert">{error}</p>}
    {notice && <p className="barq-muted" role="status">{notice}</p>}
    {!data && !error && <p className="barq-muted" role="status">{ar ? 'بنفحص مشغّل الخلفيات…' : 'Checking the wallpaper player…'}</p>}
    {data && !ready && <section className="barq-media-panel">
      <Image size={29} aria-hidden="true"/>
      <h2>{ar ? 'جهّز الخلفيات الحية' : 'Set up live wallpapers'}</h2>
      <p className="barq-muted">{data.engine ? (ar ? 'المحرك المدمج محتاج Windows 10 أو 11 مع WebView2.' : 'The integrated engine requires Windows 10/11 with WebView2.') : (ar ? 'وضع التوافق القديم يحتاج Lively.' : 'Legacy compatibility mode needs Lively.')}</p>
      {!data.engine && data.can_install && <button className="barq-media-primary" disabled={busy || installing} onClick={install}><Download size={17}/>{installing ? (ar ? 'التثبيت شغّال في Windows…' : 'Windows installer is running…') : (ar ? 'تثبيت مشغّل الخلفيات' : 'Install wallpaper player')}</button>}
      {!data.engine && !data.can_install && <a href={data.lively.official_url} target="_blank" rel="noreferrer"><ExternalLink size={16}/>{ar ? 'تنزيل Lively' : 'Download Lively'}</a>}
      <button disabled={busy} onClick={() => void operate(async () => { await refresh(); })}><RefreshCw size={16}/>{ar ? 'إعادة الفحص' : 'Check again'}</button>
    </section>}
    {data && ready && <>
      <p className="barq-muted">{ar ? 'اختار MP4 أو WebM أو GIF من جهازك، أو طبّق خلفية من مكتبتك.' : 'Choose a local MP4, WebM or GIF, or apply a wallpaper from your library.'}</p>
      <div className="barq-media-toolbar">
        <button className="barq-media-primary" disabled={busy} onClick={addLocal}><Plus size={17}/>{ar ? 'إضافة خلفية' : 'Add wallpaper'}</button>
        <button disabled={busy} onClick={() => invoke('play')}><Play size={16}/>{ar ? 'تشغيل' : 'Play'}</button>
        <button disabled={busy} onClick={() => invoke('pause')}><Pause size={16}/>{ar ? 'إيقاف مؤقت' : 'Pause'}</button>
        <button disabled={busy} onClick={() => invoke('stop')}><Square size={16}/>{ar ? 'إيقاف' : 'Stop'}</button>
        {data.capabilities.family !== 'legacy' && <button disabled={busy} onClick={() => invoke('random')}><Shuffle size={16}/>{ar ? 'عشوائي' : 'Random'}</button>}
        <label><Volume2 size={16}/><input type="range" min="0" max="100" value={volume} onChange={e => setVolume(Number(e.target.value))} aria-label={ar ? 'مستوى الصوت' : 'Volume'}/>{volume}%</label>
        <button disabled={busy} onClick={() => invoke('volume')}>{ar ? 'تطبيق الصوت' : 'Set volume'}</button>
        {!data.engine && <button disabled={busy} onClick={() => invoke('show')}><Image size={16}/>{ar ? 'فتح Lively' : 'Open Lively'}</button>}
        <button disabled={busy} onClick={() => void operate(async () => { await refresh(); })} aria-label={ar ? 'تحديث المكتبة' : 'Refresh library'}><RefreshCw size={16}/></button>
      </div>
      {data.library.length === 0 && <p className="barq-muted">{ar ? 'مكتبة الخلفيات فاضية. اضغط إضافة خلفية عشان تبدأ.' : 'Your library is empty. Add a wallpaper to get started.'}</p>}
      <div className="barq-media-grid">
        {data.library.map(item => <article key={item.id} className="barq-wallpaper-card">
          <div className="barq-wallpaper-preview">{item.preview_available ? <img src={'/v1/wallpapers/preview/' + encodeURIComponent(item.id)} alt="" loading="lazy" decoding="async"/> : <Image size={30}/>}</div>
          <div className="barq-wallpaper-detail">
            <strong dir="auto">{item.title}</strong>
            <button disabled={busy} onClick={() => invoke('apply', item.id)}>{ar ? 'تطبيق' : 'Apply'}</button>
          </div>
        </article>)}
      </div>
    </>}
  </div>;
}
