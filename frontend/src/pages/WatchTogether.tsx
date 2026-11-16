import {useEffect,useState} from 'react';
import {Video,Link2,Copy,XCircle,ExternalLink,Users,Radio} from 'lucide-react';
import {requestJSON} from '../lib/backend';
import {useApp} from '../store';

type Room={room_id:string;host_url:string;guest_url:string;room_code:string;public:boolean;note?:string};
type State={rooms:{room_id:string;guest_connected:boolean;host_connected:boolean;age_seconds:number}[];service:string;transcoding:boolean};

export function WatchTogether(){
 const ar=useApp(s=>s.language)==='ar';
 const [room,setRoom]=useState<Room|null>(null);
 const [status,setStatus]=useState<State|null>(null);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [copied,setCopied]=useState(false);
 useEffect(()=>{
  let live=true;
  async function poll(){
   try{
    const [result,active]=await Promise.all([
      requestJSON<State>('/v1/watchrooms/status'),
      requestJSON<{room:Room|null}>('/v1/watchrooms/active'),
    ]);
    if(live){setStatus(result);setRoom(active.room);}
   }catch(e){if(live)setError(e instanceof Error?e.message:String(e))}
  }
  void poll();const timer=window.setInterval(()=>void poll(),3000);
  return()=>{live=false;window.clearInterval(timer)};
 },[]);
 async function start(){
  if(busy||room)return;setBusy(true);setError('');
  try{setRoom(await requestJSON<Room>('/v1/watchrooms/start',{method:'POST',body:'{}'}))}
  catch(e){setError(e instanceof Error?e.message:String(e))}
  finally{setBusy(false)}
 }
 async function stop(){
  if(!room||busy)return;setBusy(true);setError('');
  try{
   await requestJSON('/v1/watchrooms/close',{method:'POST',body:JSON.stringify({room_id:room.room_id})});
   setRoom(null);
  }catch(e){setError(e instanceof Error?e.message:String(e))}
  finally{setBusy(false)}
 }
 async function publish(){
  if(!room||busy)return;
  if(!window.confirm(ar?'هتفتح رابطًا مؤقتًا للغرفة عبر الإنترنت. أي شخص معه الرابط والكود يقدر يحاول يدخل. الخدمة للتجارب فقط ومش مناسبة للبث الدائم. توافق؟':'Publish a temporary testing link. Anyone with the link and code can try to join. Proceed?'))return;
  setBusy(true);setError('');
  try{
   const answer=await requestJSON<{guest_url:string;room_code:string;public:boolean}>('/v1/watchrooms/publish',{
    method:'POST',body:JSON.stringify({room_id:room.room_id,confirmed:true})});
   setRoom({...room,...answer});
  }catch(e){setError(e instanceof Error?e.message:String(e))}
  finally{setBusy(false)}
 }
 async function copy(value:string){
  try{await navigator.clipboard.writeText(value);setCopied(true)}catch{setError(ar?'مش قادر أنسخ تلقائيًا. انسخ النص من الحقل.':'Copy failed. Please select the link manually.')}
 }
 const current=status?.rooms.find(r=>r.room_id===room?.room_id);
 return <div className="barq-media" dir={ar?'rtl':'ltr'}>
  <header className="barq-media-head"><div><h2>{ar?'غرفة مشاهدة مع صديق':'Watch Together'}</h2>
   <p>{ar?'شخص واحد، رابط وكود، بدون تثبيت للضيف. الفيديو من متصفحك إلى متصفحه عبر WebRTC.':'One guest, link and code, no guest installation. Browser-to-browser WebRTC.'}</p></div><span className="barq-chip"><Users size={15}/>{ar?'شخصان فقط':'One guest'}</span></header>
  {error&&<p className="barq-media-error" role="alert">{error}</p>}
  {!room&&<section className="barq-media-empty"><Video size={28}/><p>{ar?'الضيف هيفتح الرابط في متصفح حديث. صاحب الغرفة هيختار ملف الفيديو من داخل صفحة المشاهدة، من غير ما السيرفر يقرأ الملفات.':'Your friend joins in a modern browser. Pick your file locally in the host page; the server never reads your filesystem.'}</p>
    <button disabled={busy} onClick={()=>void start()}>{ar?'إنشاء غرفة محلية':'Create local watch room'}</button>
    <p className="barq-muted">{ar?'البث عبر الإنترنت محتاج نفقًا خارجيًا بموافقتك، ونجاح WebRTC بيعتمد على الشبكة.':'Internet access needs your explicit approval to enable a temporary tunnel. P2P may fail on strict NAT networks.'}</p></section>}
  {room&&<>
   <div className="barq-media-toolbar"><button disabled={busy||room.public} onClick={()=>void publish()}><Radio size={16}/>{ar?'نشر رابط اختبار خارجي بموافقتي':'Publish temporary external test link'}</button>
    <button disabled={busy} onClick={()=>void stop()}><XCircle size={16}/>{ar?'إغلاق الغرفة بالكامل':'End room and stream'}</button></div>
   <section className="barq-media-metrics">
    <div><span>{ar?'المضيف':'Host'}</span><strong>{current?.host_connected?(ar?'متصل':'Connected'):(ar?'غير متصل':'Not connected')}</strong></div>
    <div><span>{ar?'الضيف':'Guest'}</span><strong>{current?.guest_connected?(ar?'متصل':'Connected'):(ar?'لم يدخل':'Waiting')}</strong></div>
    <div><span>{ar?'وضع الرابط':'Link status'}</span><strong>{room.public?(ar?'مؤقت خارجي':'Temporary public'):(ar?'محلي فقط':'Local only')}</strong></div>
   </section>
   <div className="barq-room-share"><label>{ar?'رابط الضيف':'Guest link'} <input readOnly dir="ltr" value={room.guest_url} onFocus={e=>e.target.select()}/></label>
    <button onClick={()=>void copy(room.guest_url)} aria-label={ar?'نسخ الرابط':'Copy link'}><Copy size={16}/>{copied?(ar?'تم النسخ':'Copied'):(ar?'نسخ الرابط':'Copy link')}</button>
    <label>{ar?'كود الغرفة':'Room code'} <input readOnly dir="ltr" value={room.room_code} onFocus={e=>e.target.select()}/></label>
    <button onClick={()=>void copy(room.room_code)}><Copy size={16}/>{ar?'نسخ الكود':'Copy code'}</button>
    <a target="_blank" rel="noreferrer" href={room.host_url}><ExternalLink size={16}/>{ar?'افتح صفحة المضيف':'Open host page'}</a>
   </div>
   <section className="barq-room-frame"><h3><Link2 size={16}/>{ar?'المشاهدة والدردشة داخل برق':'Watch and chat inside BARQ'}</h3>
    <iframe title="BARQ Watch Together host" src={room.host_url} allow="autoplay" referrerPolicy="no-referrer"/>
   </section>
   <p className="barq-muted">{ar?'الدردشة والبث مؤقتان. الملفات غير المدعومة في المتصفح محتاجة تحويل خارجي حاليًا. لا يوجد TURN مجاني مضمون أو تجاوز لحماية DRM.':'Stream and chat are ephemeral. Unsupported codecs still require external conversion. No guaranteed free TURN relay or DRM bypass.'}</p>
  </>}
 </div>;
}
