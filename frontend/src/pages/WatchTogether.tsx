import {useEffect, useRef, useState} from 'react';
import {Copy, ExternalLink, Headphones, Link2, Radio, Video, XCircle} from 'lucide-react';
import {requestJSON} from '../lib/backend';
import {useApp} from '../store';

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

  return <div className="barq-media barq-watch-room" dir={ar ? 'rtl' : 'ltr'}>
    <header className="barq-watch-hero">
      <div className="barq-watch-hero-mark"><Icon size={22} aria-hidden="true"/></div>
      <div className="barq-watch-hero-copy">
        <span>BARQ ONE · {music ? 'MUSIC ROOM' : 'WATCH ROOM'}</span>
        <h2>{music ? (ar ? 'اسمعوا مع بعض' : 'Listen together') : (ar ? 'اتفرجوا مع بعض' : 'Watch together')}</h2>
        <p>{ar ? 'شارك الوسائط والدردشة في غرفة خاصة. ملفاتك بتفضل على جهازك.' : 'Share media and chat in a private room. Your files stay local.'}</p>
      </div>
      <div className="barq-watch-live-label">{ar ? 'جلسة مشتركة' : 'Shared session'}</div>
    </header>
    {error && <p className="barq-media-error" role="alert">{error}</p>}
    {!room && !guest && <div className="barq-room-entry">
      <section className="barq-media-panel barq-watch-choose-panel">
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
        <label>{ar ? 'كود الدخول من برنامج برق' : 'Join code for the BARQ app'}<input readOnly dir="ltr" value={inviteCode} onFocus={e => e.target.select()}/></label>
        <button onClick={() => void copy(inviteCode)}><Copy size={16}/>{copied ? (ar ? 'اتنسخ' : 'Copied') : (ar ? 'نسخ الكود' : 'Copy code')}</button>
        <a href={current.guest_url + '#' + current.room_code} target="_blank" rel="noreferrer"><ExternalLink size={16}/>{ar ? 'رابط للمتصفح' : 'Browser link'}</a>
        <button onClick={() => void copy(current.guest_url + '#' + current.room_code)} aria-label={ar ? 'نسخ رابط المتصفح' : 'Copy browser link'}><Copy size={16}/></button>
      </section>}
    </>}
    {(guest || current) && <section className="barq-room-frame barq-watch-player">
      <div className="barq-watch-player-top">
        <div><Icon size={17}/><strong>{music ? (ar ? 'مشغّل الموسيقى' : 'Music player') : (ar ? 'مشغّل المشاهدة' : 'Video player')}</strong></div>
        <span>{ar ? 'اضغط «ملء الشاشة» داخل المشغّل للتكبير على شاشتك' : 'Use Fullscreen in the player to expand on your display'}</span>
        {guest && <button onClick={() => setGuest('')}><XCircle size={16}/>{ar ? 'مغادرة الغرفة' : 'Leave room'}</button>}
      </div>
      <iframe title={ar ? 'مشغّل الغرفة' : 'Room player'} src={guest || current?.host_url} allow="autoplay; encrypted-media; fullscreen; picture-in-picture" allowFullScreen referrerPolicy="no-referrer"/>
    </section>}
  </div>;
}
