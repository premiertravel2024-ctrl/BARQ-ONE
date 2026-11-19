import {useCallback, useEffect, useRef, useState} from 'react';
import {Copy, ExternalLink, Headphones, Link2, Radio, Video, Search, LogOut, Globe2} from 'lucide-react';
import {requestJSON} from '../lib/backend';
import {useApp} from '../store';
import {ButtonGroup, ButtonGroupItem} from '../components/ui/ButtonGroup';
import {Modal} from '../components/ui/Modal';
import {IconButton} from '../components/ui/IconButton';
import './roomExperience.css';
import {useAppView} from '../lib/appContext';
import {MusicServices,type RoomTrack} from './MusicServices';
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
function WatchContext({status}:{status:string}){useAppView('watch',{mode:'room',status});return null;}
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

export function WatchTogether({mode = 'video',track,onTrack,requestedProvider,onRoomState}: {mode?: Mode;track?:RoomTrack;onTrack?:(track:RoomTrack)=>void;requestedProvider?:RoomTrack['provider'];onRoomState?:(status:string)=>void}) {
  const ar = useApp(s => s.language) === 'ar';
  const [room, setRoom] = useState<Room | null>(null);
  const [guest, setGuest] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const [invite, setInvite] = useState('');
  const [joinOpen, setJoinOpen] = useState(false);
  const [hostOpen, setHostOpen] = useState(false);
  const [providerOpen,setProviderOpen]=useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [provider,setProvider]=useState<RoomTrack['provider']>('spotify');
  const current = room?.mode === mode ? room : null;
  useEffect(() => {
    if (!requestedProvider) return;
    setProvider(requestedProvider);
    setProviderOpen(true);
  }, [requestedProvider, current?.room_id]);
  const frame=useRef<HTMLIFrameElement>(null);
  const pendingShare=useRef('');
  const sharedSelection=useRef(false);
  const [trackStatus,setTrackStatus]=useState('');
  const roomStatus=guest?'guest':current?(current.guest_connected?'guest connected':'waiting for guest'):'no active room';
  useEffect(()=>onRoomState?.(roomStatus),[roomStatus,onRoomState]);
  useEffect(()=>{setTrackStatus('');pendingShare.current='';sharedSelection.current=false;},[track,current?.room_id]);
  useEffect(()=>{
    if(!current||!track||guest)return;
    const origin=new URL(current.host_url,window.location.href).origin;
    const onResult=(event:MessageEvent)=>{
      if(event.origin!==origin||event.source!==frame.current?.contentWindow||
         event.data?.type!=='barq-room-track-result'||!pendingShare.current||event.data.id!==pendingShare.current)return;
      pendingShare.current='';
      sharedSelection.current=event.data.ok===true;
      setTrackStatus(event.data.ok
        ?(ar?'الأغنية ظهرت في الغرفة. كل مشارك يقدر يشغّلها عنده.':'The track is in the room. Each participant can play it.')
        :(ar?'استنى لحد ما الغرفة تتصل واضغط مشاركة تاني.':'Wait for the room connection, then retry sharing.'));
    };
    window.addEventListener('message',onResult);
    return()=>window.removeEventListener('message',onResult);
  },[ar,current?.host_url,track,guest]);
  const sendTrack=useCallback(()=>{
    if(!frame.current?.contentWindow||!current||!track||guest||pendingShare.current||sharedSelection.current)return;
    const id=crypto.randomUUID();
    pendingShare.current=id;
    setTrackStatus(ar?'جاري إرسال الاختيار للمشغّل…':'Sending the selection to the player…');
    frame.current.contentWindow.postMessage({type:'barq-room-track',id,track:{
      provider:track.provider,kind:track.kind,id:track.id,
    }},new URL(current.host_url,window.location.href).origin);
    window.setTimeout(()=>{
      if(pendingShare.current!==id)return;
      pendingShare.current='';
      setTrackStatus(ar?'المشغّل لسه ما أكدش المشاركة. جرّب تاني.':'The player has not confirmed the share. Please retry.');
    },4500);
  },[ar,current?.host_url,track,guest]);
  useEffect(()=>{
    if(!track||!current||guest)return;
    const timer=window.setTimeout(sendTrack,1000);
    return()=>window.clearTimeout(timer);
  },[track,current?.room_id,guest,sendTrack]);
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

  const picker=music&&!guest&&onTrack&&<section className="barq-music-providers">
      <ButtonGroup size="sm" aria-label={ar?'مصدر الموسيقى':'Music source'}>
        <ButtonGroupItem aria-pressed={provider==='anghami'} onClick={()=>setProvider('anghami')}>{ar?'أنغامي':'Anghami'}</ButtonGroupItem>
        <ButtonGroupItem aria-pressed={provider==='spotify'} onClick={()=>setProvider('spotify')}>Spotify</ButtonGroupItem>
      </ButtonGroup>
      {provider&&<MusicServices key={provider} provider={provider} ar={ar} roomOnly onShare={selection=>{onTrack(selection);setProviderOpen(false)}}/>}
    </section>;
  return <div className={'barq-media barq-watch-room'+(music?' barq-music-app':'')} dir={ar ? 'rtl' : 'ltr'}>
    {music&&!current&&!guest&&<section className="barq-music-lobby">
      <div className="barq-lobby-top">
        <div className="barq-lobby-mark"><Headphones size={19}/><span>{ar?'استماع سوا':'Listen together'}</span></div>
        <div className="barq-lobby-actions">
          <button type="button" className="bc-primary" disabled={busy} onClick={()=>setHostOpen(true)}><Headphones size={17}/>{ar?'افتح غرفة':'Host a room'}</button>
          <IconButton label={ar?'ادخل غرفة صاحبك':'Join a friend'} icon={<Link2 size={17}/>} onClick={()=>{setError('');setJoinOpen(true)}}/>
        </div>
      </div>
      {picker}
    </section>}
    {!music && !current && !guest && <CinemaDiscovery ar={ar} roomActive={false} onRoom={() => { setError(''); setHostOpen(true); }} onJoin={() => {setError('');setJoinOpen(true);}}/>}
    <Modal open={hostOpen} onClose={()=>setHostOpen(false)} title={ar?'غرفة جديدة':'New room'} dialogClassName="barq-room-dialog">
      <div className="barq-room-choices">
        <button type="button" disabled={busy} onClick={()=>{setHostOpen(false);start(false)}}><Globe2 size={21}/><span>{ar?'عبر الإنترنت':'Online'}</span></button>
        <button type="button" disabled={busy} onClick={()=>{setHostOpen(false);start(true)}}><Radio size={21}/><span>{ar?'الشبكة المحلية':'Local network'}</span></button>
      </div>
    </Modal>
    <Modal open={joinOpen} onClose={()=>{if(!busy)setJoinOpen(false)}} title={ar?'ادخل غرفة صاحبك':'Join a friend'}>
      <form className="barq-cinema-join-form" onSubmit={e=>{e.preventDefault();join();}}>
        {error&&<p role="alert">{error}</p>}
        <label htmlFor="cinema-join-code">{ar?'كود دعوة برق':'BARQ invitation code'}</label>
        <input id="cinema-join-code" autoFocus dir="ltr" value={invite} maxLength={950} placeholder="BARQ-…" onChange={e=>setInvite(e.target.value)} required/>
        <button className="bc-primary" type="submit" disabled={busy||!invite.trim()}>{ar?'دخول الغرفة':'Join room'}</button>
      </form>
    </Modal>
    <Modal open={shareOpen&&!!inviteCode} onClose={()=>{setShareOpen(false);setCopied(false)}} title={ar?'ادعُ صاحبك':'Invite a friend'}>
      {current&&<div className="barq-cinema-join-form">
        <input aria-label={ar?'كود دعوة برق':'BARQ invitation code'} dir="ltr" value={inviteCode} readOnly onFocus={e=>e.currentTarget.select()}/>
        <button type="button" className="bc-primary" onClick={()=>void copy(inviteCode)}><Copy size={16}/>{copied?(ar?'اتنسخ':'Copied'):(ar?'نسخ كود برق':'Copy BARQ code')}</button>
        <a className="barq-browser-invite" href={current.guest_url+'#'+current.room_code} target="_blank" rel="noreferrer"><ExternalLink size={15}/>{ar?'فتح للضيف في المتصفح':'Open guest view in browser'}</a>
      </div>}
    </Modal>
    {error && <p className="barq-media-error" role="alert">{error}</p>}
    {room && !current && !guest && <section className="barq-media-panel">
      <p>{ar ? 'فيه غرفة تانية مفتوحة. اقفلها أو افتحها من تبويبها.' : 'Another room is active. Open its tab or end it here.'}</p>
      <button disabled={busy} onClick={() => void operate(async () => {
        await requestJSON('/v1/watchrooms/close', post({room_id: room.room_id}));
        setRoom(null);
      })}>{ar ? 'إغلاق الغرفة المفتوحة' : 'End active room'}</button>
    </section>}
    {!music&&(guest||current)&&<WatchContext status={roomStatus}/>}
    {(guest || current) && <section className={'barq-room-frame barq-watch-player'+(music?'':' barq-cinema-player')}>
      <div className="barq-watch-player-top">
        <div><Icon size={17}/><strong>{music ? (ar ? 'غرفة الموسيقى' : 'Music room') : (ar ? 'سينما برق' : 'BARQ Cinema')}</strong></div>
        {current && !guest && <div className="barq-room-actions">
          <span className={'barq-room-presence'+(current.guest_connected?' is-online':'')} role="status" title={current.guest_connected?(ar?'صاحبك متصل':'Guest connected'):(ar?'في انتظار صاحبك':'Waiting for a guest')} aria-label={current.guest_connected?(ar?'صاحبك متصل':'Guest connected'):(ar?'في انتظار صاحبك':'Waiting for a guest')}/>
          <span className="barq-room-connection-kind" title={current.lan?(ar?'شبكة محلية':'Local network'):(ar?'عبر الإنترنت':'Online')}>{current.lan?<Radio size={15}/>:<Globe2 size={15}/>}</span>
          {music&&<IconButton label={ar?'اختار أغنية':'Choose music'} icon={<Search size={17}/>} onClick={()=>setProviderOpen(true)}/>}
          {!current.public&&!current.lan&&<IconButton label={ar?'دعوة عبر الإنترنت':'Internet invite'} icon={<Globe2 size={17}/>} disabled={busy} onClick={publish}/>}
          {inviteCode&&<IconButton label={ar?'ادعُ صاحبك':'Invite a friend'} icon={<Link2 size={17}/>} onClick={()=>{setCopied(false);setShareOpen(true)}}/>}
          <IconButton label={ar?'إنهاء الغرفة':'End room'} icon={<LogOut size={17}/>} disabled={busy} onClick={()=>void operate(async()=>{
            await requestJSON('/v1/watchrooms/close',post({room_id:current.room_id}));setRoom(null);setCopied(false);
          })}/>
        </div>}
        {guest&&<IconButton label={ar?'مغادرة الغرفة':'Leave room'} icon={<LogOut size={17}/>} onClick={()=>setGuest('')}/>}
      </div>
      {current&&picker&&<Modal open={providerOpen} onClose={()=>setProviderOpen(false)} title={ar?'اختار أغنية':'Choose music'} wide dialogClassName="barq-room-dialog">{picker}</Modal>}
      {music&&track&&current&&!guest&&<div className="barq-room-track-status">
        {!sharedSelection.current&&<strong dir="auto">{track.title}</strong>}
        {!sharedSelection.current&&<button type="button" onClick={sendTrack}>{ar?'شارك الاختيار':'Share selection'}</button>}
        <span className="barq-sr-only" role="status">{trackStatus}</span>
      </div>}
      <iframe ref={frame} title={ar ? 'مشغّل الغرفة' : 'Room player'} src={guest || current?.host_url} allow="autoplay; encrypted-media; fullscreen; picture-in-picture" allowFullScreen referrerPolicy="no-referrer"/>
    </section>}
  </div>;
}
