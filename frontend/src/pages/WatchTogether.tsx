import {useEffect, useRef, useState} from 'react';
import {Copy, ExternalLink, Headphones, Link2, Radio, Video, XCircle} from 'lucide-react';
import {requestJSON} from '../lib/backend';
import {useApp} from '../store';
import {Modal} from '../components/ui/Modal';
import {CinemaDiscovery} from './CinemaDiscovery';

type Mode = 'video' | 'music';
type Room = {
  room_id: string;
  mode: Mode;
  host_url: string;
  guest_url: string;
  room_code: string;
  public: boolean;
  lan: boolean;
  guest_connected: boolean;
};

const joinPrefix = 'BARQ-';
const post = (body: unknown): RequestInit => ({method: 'POST', body: JSON.stringify(body)});

function parseInvite(value: string) {
  const invite = value.trim();
  if (!invite.startsWith(joinPrefix) || invite.length > 950) throw new Error('Invalid invitation');
  const fields = new URLSearchParams(atob(invite.slice(joinPrefix.length)));
  const guest_url = fields.get('room');
  const code = fields.get('code');
  if (!guest_url || !code) throw new Error('Invalid invitation');
  return {guest_url, code};
}

export function WatchTogether({mode = 'video'}: {mode?: Mode}) {
  const ar = useApp(s => s.language) === 'ar';
  const [room, setRoom] = useState<Room | null>(null);
  const [guest, setGuest] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const [invite, setInvite] = useState('');
  const [joinOpen, setJoinOpen] = useState(false);
  const current = room?.mode === mode ? room : null;
  const roomId = room?.room_id;
  const mutation = useRef(0);
  const busyRef = useRef(false);
  const music = mode === 'music';
  const Icon = music ? Headphones : Video;
  const inviteCode = current && (current.lan || current.public)
    ? joinPrefix + btoa(new URLSearchParams({room: current.guest_url, code: current.room_code}).toString())
    : '';

  useEffect(() => {
    let live = true;
    let timer: number;
    async function refresh() {
      try {
        const revision = mutation.current;
        if (!document.hidden && !busyRef.current) {
          const active = await requestJSON<{room: Room | null}>('/v1/watchrooms/active');
          if (live && revision === mutation.current && !busyRef.current) setRoom(active.room);
        }
      } catch (e) {
        if (live && !busyRef.current) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (live && roomId) timer = window.setTimeout(() => void refresh(), 5000);
      }
    }
    void refresh();
    return () => { live = false; window.clearTimeout(timer); };
  }, [roomId]);

  async function operate(action: () => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true;
    mutation.current++;
    setBusy(true);
    setError('');
    try { await action(); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { busyRef.current = false; setBusy(false); }
  }

  function start(lan: boolean) {
    if (!lan && !confirmInternetInvite()) return;
    void operate(async () => {
      const created = await requestJSON<Room>('/v1/watchrooms/start', post({mode, lan}));
      setRoom(created);
      if (!lan) setRoom(await publishRoom(created));
    });
  }

  function join() {
    void operate(async () => {
      let parsed: ReturnType<typeof parseInvite>;
      try { parsed = parseInvite(invite); }
      catch { throw new Error(ar ? 'الكود مش كامل. انسخ كود الدعوة اللي بيبدأ بـ BARQ-.' : 'Paste the full BARQ- invitation code.'); }
      const result = await requestJSON<{url: string}>('/v1/watchrooms/join', post(parsed));
      setGuest(result.url);
      setInvite('');
      setJoinOpen(false);
    });
  }

  function confirmInternetInvite() {
    return window.confirm(ar
      ? 'برق هيجهّز دعوة للغرفة عبر الإنترنت. أي حد معاه الدعوة يقدر يطلب الدخول. تكمّل؟'
      : 'BARQ will create an internet room invite. Anyone with the invite can try to join. Continue?');
  }

  function publishRoom(active: Room) {
    return requestJSON<Room>('/v1/watchrooms/publish', post({room_id: active.room_id, confirmed: true}));
  }

  function publish() {
    if (!current || !confirmInternetInvite()) return;
    void operate(async () => {
      setRoom(await publishRoom(current));
      setCopied(false);
    });
  }

  async function copy(value: string) {
    try { await navigator.clipboard.writeText(value); setCopied(true); }
    catch { setError(ar ? 'انسخ كود الدعوة يدويًا من الحقل.' : 'Select and copy the invitation code manually.'); }
  }

  return <div className={'barq-media barq-watch-room'+(music?' barq-music-app':'')} dir={ar ? 'rtl' : 'ltr'}>
    {(music || current || guest) && <header className={'barq-watch-hero'+(music?' barq-music-hero':'')}>
      <div className="barq-watch-hero-mark"><Icon size={22} aria-hidden="true"/></div>
      <div className="barq-watch-hero-copy">
        <span>BARQ ONE · {music ? 'MUSIC ROOM' : 'WATCH ROOM'}</span>
        <h2>{music ? (ar ? 'غرفة الموسيقى' : 'BARQ Music Room') : (ar ? 'سينما برق' : 'BARQ Cinema')}</h2>
        <p>{music?(ar?'موسيقاك المفضلة، وجلسة استماع خاصة مع صاحبك. من ملفك أو مشغّل Spotify وأنغامي الرسمي.':'Your music, your listening lounge. Share local audio or an official Spotify/Anghami player.'):(ar?'شوف الأفلام والمسلسلات والأنمي، وشارك ملف فيديو من جهازك في غرفة خاصة.':'Explore films, series and anime. Watch your own video together privately.')}</p>
      </div>
      {music?<div className="bma-vinyl" aria-hidden="true"><div className="bma-vinyl-center"><Headphones size={28}/></div><div className="bma-bars"><i/><i/><i/><i/><i/><i/><i/></div></div>:<div className="barq-watch-live-label">{ar ? 'جلسة خاصة' : 'Private session'}</div>}
    </header>}
    {!music && !current && !guest && <CinemaDiscovery ar={ar} roomActive={false} onRoom={() => start(false)} onJoin={() => {setError('');setJoinOpen(true);}}/>}
    {!music&&<Modal open={joinOpen} onClose={()=>{if(!busy)setJoinOpen(false)}} title={ar?'الدخول بكود الغرفة':'Join with room code'}>
      <form className="barq-cinema-join-form" onSubmit={e=>{e.preventDefault();join();}}>
        <p>{ar?'الصق كود دعوة برق اللي بيبدأ بـ BARQ- علشان تدخل غرفة صاحبك.':'Paste the BARQ- invitation code your friend sent.'}</p>
        <label htmlFor="cinema-join-code">{ar?'كود الدعوة':'Invite code'}</label>
        <input id="cinema-join-code" autoFocus dir="ltr" value={invite} maxLength={950} placeholder="BARQ-…" onChange={e=>setInvite(e.target.value)} required/>
        <button className="bc-primary" type="submit" disabled={busy||!invite.trim()}>{ar?'دخول الغرفة':'Join room'}</button>
        <button className="bc-lan-create" type="button" disabled={busy} onClick={()=>{setJoinOpen(false);start(true)}}>{ar?'إنشاء غرفة على نفس الشبكة':'Create a local-network room'}</button>
      </form>
    </Modal>}
    {error && <p className="barq-media-error" role="alert">{error}</p>}
    {!room && !guest && music && <div className="barq-room-entry">
      <section className={'barq-media-panel barq-watch-choose-panel'+(music?' bma-choose':'')}>
        <Icon size={28} aria-hidden="true"/>
        <h2>{ar ? 'افتح غرفة' : 'Host a room'}</h2>
        <p className="barq-muted">{ar
          ? music ? 'اختار أغنية من جهازك أو شغّل رابط صوت مباشر.' : 'اختار فيلم من جهازك أو شغّل رابط فيديو مباشر.'
          : music ? 'Choose a music file or a direct audio link.' : 'Choose a video file or a direct video link.'}</p>
        <button className="barq-media-primary" disabled={busy} onClick={() => start(true)}><Radio size={17}/>{ar ? 'إنشاء غرفة على نفس الشبكة' : 'Host on the local network'}</button>
        <button disabled={busy} onClick={() => start(false)}><ExternalLink size={16}/>{ar ? 'غرفة بدعوة عبر الإنترنت' : 'Host with an internet invitation'}</button>
      </section>
      <form className="barq-media-panel barq-watch-choose-panel" onSubmit={event => { event.preventDefault(); join(); }}>
        <Link2 size={28} aria-hidden="true"/>
        <h2>{ar ? 'ادخل غرفة صاحبك' : 'Join a friend'}</h2>
        <label htmlFor="barq-room-invite">{ar ? 'كود دعوة برق' : 'BARQ invitation code'}</label>
        <input id="barq-room-invite" dir="ltr" value={invite} maxLength={950} placeholder="BARQ-…" onChange={e => setInvite(e.target.value)} required/>
        <button className="barq-media-primary" disabled={busy || !invite.trim()}>{ar ? 'دخول' : 'Join'}</button>
      </form>
    </div>}
    {room && !current && !guest && <section className="barq-media-panel">
      <p>{ar ? 'فيه غرفة تانية مفتوحة. اقفلها أو افتحها من تبويبها.' : 'Another room is active. Open its tab or end it here.'}</p>
      <button disabled={busy} onClick={() => void operate(async () => {
        await requestJSON('/v1/watchrooms/close', post({room_id: room.room_id}));
        setRoom(null);
      })}>{ar ? 'إغلاق الغرفة المفتوحة' : 'End active room'}</button>
    </section>}
    {current && !guest && <>
      <section className="barq-media-toolbar barq-watch-controls">
        <span className="barq-chip">{current.guest_connected ? (ar ? 'صاحبك متصل' : 'Guest connected') : (ar ? 'مستني صاحبك' : 'Waiting for a guest')}</span>
        {!current.public && <button disabled={busy} onClick={publish}><Radio size={16}/>{busy ? (ar ? 'بنجهّز رابط الإنترنت…' : 'Preparing the internet invite…') : (ar ? 'إنشاء رابط للإنترنت' : 'Create an internet link')}</button>}
        <button disabled={busy} onClick={() => void operate(async () => {
          await requestJSON('/v1/watchrooms/close', post({room_id: current.room_id}));
          setRoom(null); setCopied(false);
        })}><XCircle size={16}/>{ar ? 'إنهاء الغرفة' : 'End room'}</button>
      </section>
      {inviteCode && <section className="barq-room-share">
        <div className="barq-room-share-summary"><strong>{ar ? 'دعوة الغرفة' : 'Room invite'}</strong><small>{ar ? 'ابعت الكود لصاحبك، أو افتح رابط المتصفح.' : 'Send the invite to your friend, or open the browser link.'}</small></div>
        <button onClick={() => void copy(inviteCode)}><Copy size={16}/>{copied ? (ar ? 'اتنسخ' : 'Copied') : (ar ? 'نسخ كود الدعوة' : 'Copy invite code')}</button>
        <details className="barq-room-share-expand"><summary>{ar ? 'إظهار الكود' : 'Show invite code'}</summary><input readOnly dir="ltr" value={inviteCode} onFocus={e => e.target.select()}/></details>
        <a href={current.guest_url + '#' + current.room_code} target="_blank" rel="noreferrer"><ExternalLink size={16}/>{ar ? 'رابط للمتصفح' : 'Browser link'}</a>
        <button onClick={() => void copy(current.guest_url + '#' + current.room_code)} aria-label={ar ? 'نسخ رابط المتصفح' : 'Copy browser link'}><Copy size={16}/></button>
      </section>}
    </>}
    {(guest || current) && <section className="barq-room-frame barq-watch-player">
      <div className="barq-watch-player-top">
        <div><Icon size={17}/><strong>{music ? (ar ? 'مشغّل الموسيقى' : 'Music player') : (ar ? 'مشغّل المشاهدة' : 'Video player')}</strong></div>
        {!music && <span>{ar ? 'ملء الشاشة من داخل المشغّل' : 'Fullscreen inside player'}</span>}
        {guest && <button onClick={() => setGuest('')}><XCircle size={16}/>{ar ? 'مغادرة الغرفة' : 'Leave room'}</button>}
      </div>
      <iframe title={ar ? 'مشغّل الغرفة' : 'Room player'} src={guest || current?.host_url} allow="autoplay; encrypted-media; fullscreen; picture-in-picture" allowFullScreen referrerPolicy="no-referrer"/>
    </section>}
  </div>;
}
