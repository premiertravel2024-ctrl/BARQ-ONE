import {useCallback,useEffect,useRef,useState} from 'react';
import {Headphones,Link2,Music2,Pause,Play,Send,Users,X} from 'lucide-react';

type State={type:'state';code:string;participants:number;track:string;title:string;paused:boolean;position:number;updated:number};
type Chat={type:'chat';id:string;text:string;sender:string;at:number};
type RoomInfo={code:string;secret:string};
const qs=new URLSearchParams(window.location.search);
const initialCode=qs.get('room')||'';
const initialSecret=qs.get('key')||'';

export function ListeningRoom({onBack}:{onBack:()=>void}){
 const [room,setRoom]=useState<RoomInfo|null>(initialCode&&initialSecret?{code:initialCode,secret:initialSecret}:null);
 const [code,setCode]=useState(initialCode),[secret,setSecret]=useState(initialSecret);
 const [status,setStatus]=useState(''),[connected,setConnected]=useState(false),[people,setPeople]=useState(0);
 const [track,setTrack]=useState(''),[title,setTitle]=useState(''),[url,setUrl]=useState('');
 const [paused,setPaused]=useState(true),[messages,setMessages]=useState<Chat[]>([]),[draft,setDraft]=useState('');
 const socket=useRef<WebSocket|null>(null),audio=useRef<HTMLAudioElement|null>(null),previousTrack=useRef('');
 const silent=useRef(false);
 const ignoreEventsUntil=useRef(0);
 const invite=room?`${window.location.origin}/?room=${encodeURIComponent(room.code)}&key=${encodeURIComponent(room.secret)}`:'';
 const send=useCallback((data:object)=>{if(socket.current?.readyState===WebSocket.OPEN)socket.current.send(JSON.stringify(data))},[]);
 useEffect(()=>{
  if(!room)return;
  let active=true;
  const scheme=window.location.protocol==='https:'?'wss':'ws';
  const ws=new WebSocket(`${scheme}://${window.location.host}/v1/listening/rooms/${encodeURIComponent(room.code)}/ws?secret=${encodeURIComponent(room.secret)}`);
  socket.current=ws;
  ws.onopen=()=>{if(active){setConnected(true);setStatus('تم الاتصال بالغرفة')}};
  ws.onmessage=event=>{
   if(!active)return;
   let msg:State|Chat|{type:'error';message:string};
   try{msg=JSON.parse(event.data)}catch{return}
   if(msg.type==='error'){setStatus(msg.message);return}
   if(msg.type==='chat'){setMessages(items=>[...items.slice(-99),msg]);return}
   setPeople(msg.participants);setTrack(msg.track);setTitle(msg.title);setPaused(msg.paused);
   const player=audio.current;
   if(player){
    silent.current=true;ignoreEventsUntil.current=Date.now()+300;
    if(previousTrack.current!==msg.track){previousTrack.current=msg.track;player.src=msg.track;player.load()}
    const target=msg.position+(msg.paused?0:Math.max(0,(Date.now()/1000-msg.updated)));
    if(Number.isFinite(target)&&Math.abs(player.currentTime-target)>1.5){try{player.currentTime=target}catch{/* metadata pending */}}
    if(msg.paused)player.pause();else void player.play().catch(()=>setStatus('اضغط تشغيل لتفعيل الصوت في المتصفح'));
    silent.current=false;
   }
  };
  ws.onclose=()=>{if(active){setConnected(false);setStatus('الاتصال بالغرفة اتقفل. راجع الرابط أو اتصال السيرفر.')}};
  ws.onerror=()=>{if(active)setStatus('تعذر الوصول لسيرفر الغرفة')};
  return()=>{active=false;ws.close();if(socket.current===ws)socket.current=null;setConnected(false)};
 },[room]);
 async function create(){
  try{const response=await fetch('/v1/listening/rooms',{method:'POST'});if(!response.ok)throw Error(`HTTP ${response.status}`);
   const data=await response.json() as RoomInfo;setRoom(data);setMessages([]);setStatus('');
  }catch{setStatus('تعذر إنشاء غرفة. تأكد إن سيرفر برق شغال.')}
 }
 async function join(){
  try{const response=await fetch('/v1/listening/rooms/join',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:code.trim().toUpperCase(),secret:secret.trim()})});
   if(!response.ok){const e=await response.json() as {detail?:string};throw Error(e.detail||'تعذر الدخول')}
   setRoom({code:code.trim().toUpperCase(),secret:secret.trim()});setMessages([]);setStatus('');
  }catch(e){setStatus(e instanceof Error?e.message:'تعذر الدخول')}
 }
 function updatePlayback(next:{track?:string;title?:string;paused?:boolean;position?:number}){
  const player=audio.current;
  send({type:'playback',track:next.track??track,title:next.title??title,paused:next.paused??paused,position:next.position??player?.currentTime??0});
 }
 function leave(){socket.current?.close();setRoom(null);setPeople(0);setMessages([]);audio.current?.pause();previousTrack.current='';history.replaceState({},'',window.location.pathname)}
 return <div className="flex h-full min-h-0 flex-col overflow-y-auto bg-base p-5 text-primary" dir="rtl">
  <header className="mb-6 flex items-center justify-between gap-3 border-b border-stroke pb-4"><div className="flex items-center gap-3"><span className="rounded-2xl bg-accent/15 p-3 text-accent"><Headphones size={26}/></span><div><h1 className="text-xl font-bold">غرفة الاستماع</h1><p className="text-sm text-secondary">اسمع مع صاحبك في نفس اللحظة — شخصين بس</p></div></div><button onClick={onBack} aria-label="رجوع" className="rounded-xl border border-stroke p-2"><X size={19}/></button></header>
  {!room?<div className="mx-auto w-full max-w-xl space-y-5"><div className="rounded-2xl border border-stroke bg-surface p-5"><h2 className="mb-3 font-semibold">ابدأ غرفة جديدة</h2><button onClick={()=>void create()} className="rounded-xl bg-accent px-5 py-3 font-semibold text-white">إنشاء غرفة خاصة</button></div><div className="space-y-3 rounded-2xl border border-stroke bg-surface p-5"><h2 className="font-semibold">الدخول لغرفة صديقك</h2><input className="ui-input w-full" placeholder="كود الغرفة" value={code} onChange={e=>setCode(e.target.value)} /><input className="ui-input w-full" placeholder="مفتاح الدعوة" value={secret} onChange={e=>setSecret(e.target.value)}/><button onClick={()=>void join()} disabled={!code.trim()||!secret.trim()} className="rounded-xl border border-stroke px-5 py-2 disabled:opacity-50">دخول الغرفة</button></div></div>:
  <div className="mx-auto grid w-full max-w-5xl gap-5 lg:grid-cols-[1.3fr_1fr]">
   <section className="space-y-5 rounded-2xl border border-stroke bg-surface p-5"><div className="flex flex-wrap items-center justify-between gap-3"><span className="flex items-center gap-2 text-sm"><Users size={16}/>{people}/2 {connected?'متصل':'غير متصل'}</span><button onClick={leave} className="text-sm text-danger">مغادرة</button></div>
    <div className="rounded-xl bg-elevated p-4"><div className="mb-2 flex items-center gap-2"><Link2 size={16}/><strong>رابط الدعوة الخاص</strong></div><p className="mb-3 break-all text-xs text-secondary">{invite}</p><button onClick={()=>void navigator.clipboard.writeText(invite).then(()=>setStatus('تم نسخ الدعوة')).catch(()=>setStatus('انسخ الرابط يدويًا'))} className="rounded-lg border border-stroke px-3 py-2 text-sm">نسخ الرابط</button></div>
    <div className="space-y-3"><label className="block text-sm font-semibold" htmlFor="music-url">رابط مباشر لملف صوت (HTTPS)</label><input id="music-url" className="ui-input w-full" type="url" placeholder="https://example.com/music.mp3" value={url} onChange={e=>setUrl(e.target.value)}/><input className="ui-input w-full" placeholder="اسم الأغنية (اختياري)" value={title} onChange={e=>setTitle(e.target.value)}/><button onClick={()=>{if(!/^https:\/\/[^\s]+$/i.test(url)){setStatus('استخدم رابط HTTPS مباشر');return}updatePlayback({track:url,title,paused:true,position:0})}} disabled={!connected} className="rounded-xl bg-accent px-4 py-2 text-white disabled:opacity-50">تحميل الأغنية للغرفة</button></div>
    <div className="space-y-3 rounded-xl border border-stroke p-4"><div className="flex items-center gap-3"><Music2 className="text-accent" size={24}/><div className="min-w-0"><strong className="block truncate">{title||'مفيش أغنية شغالة'}</strong><span className="text-xs text-secondary">التشغيل بيتزامن تلقائيًا</span></div></div><audio ref={audio} controls className="w-full" preload="metadata" onPlay={()=>{if(!silent.current&&Date.now()>ignoreEventsUntil.current)updatePlayback({paused:false})}} onPause={()=>{if(!silent.current&&Date.now()>ignoreEventsUntil.current)updatePlayback({paused:true})}} onSeeked={()=>{if(!silent.current&&Date.now()>ignoreEventsUntil.current)updatePlayback({position:audio.current?.currentTime??0})}}/><div className="flex gap-2"><button disabled={!track||!connected} onClick={()=>{const player=audio.current;if(!player)return;if(player.paused){void player.play().catch(()=>setStatus('تعذر تشغيل الرابط الصوتي'));updatePlayback({paused:false})}else{player.pause();updatePlayback({paused:true})}}} className="flex items-center gap-2 rounded-lg border border-stroke px-4 py-2 disabled:opacity-50">{paused?<Play size={16}/>:<Pause size={16}/>} {paused?'تشغيل':'إيقاف'}</button></div></div>
   </section>
   <section className="flex min-h-80 flex-col rounded-2xl border border-stroke bg-surface p-5"><h2 className="mb-4 font-bold">شات الغرفة</h2><div aria-live="polite" className="min-h-40 flex-1 space-y-2 overflow-y-auto rounded-xl bg-elevated p-3">{messages.map(msg=><div key={msg.id} className="rounded-lg border border-stroke p-2 text-sm"><span className="mb-1 block text-xs text-muted">مشارك</span>{msg.text}</div>)}{!messages.length&&<p className="text-sm text-secondary">ابعت أول رسالة لصاحبك</p>}</div><form className="mt-3 flex gap-2" onSubmit={e=>{e.preventDefault();if(draft.trim()){send({type:'chat',text:draft.trim()});setDraft('')}}}><input className="ui-input min-w-0 flex-1" maxLength={500} placeholder="اكتب رسالة..." value={draft} onChange={e=>setDraft(e.target.value)}/><button disabled={!connected||!draft.trim()} aria-label="إرسال" className="rounded-xl bg-accent px-3 text-white disabled:opacity-50"><Send size={18}/></button></form></section>
  </div>}
  {status&&<p role="status" className="mx-auto mt-4 w-full max-w-5xl text-sm text-secondary">{status}</p>}
  <p className="mx-auto mt-5 max-w-5xl text-xs text-secondary">الغرف متاحة مؤقتًا على سيرفر برق المحلي. علشان حد يدخل من جهاز تاني عبر الإنترنت لازم خادم وسيط آمن أو اتصال VPN. الروابط المباشرة لازم تكون متاحة للطرفين؛ مفيش إعادة بث لمحتوى محمي.</p>
 </div>
}
