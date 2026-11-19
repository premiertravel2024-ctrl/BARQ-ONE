import {useEffect,useRef,useState} from 'react';
import {Music2,Pause,Play,SkipBack,SkipForward} from 'lucide-react';
import {soundtracks} from './readingSoundtracks';

type Mood='all'|'quiet'|'bright';

export function ReadingSound({ar}:{ar:boolean}){
 const audio=useRef<HTMLAudioElement>(null);
 const [open,setOpen]=useState(false);
 const [playing,setPlaying]=useState(false);
 const [loading,setLoading]=useState(false);
 const [volume,setVolume]=useState(22);
 const [mood,setMood]=useState<Mood>('all');
 const [index,setIndex]=useState(0);
 const [error,setError]=useState(false);
 const track=soundtracks[index];
 const queue=soundtracks.map((item,i)=>item.mood===mood||mood==='all'?i:-1).filter(i=>i>=0);
 const label=(a:string,e:string)=>ar?a:e;
 useEffect(()=>{if(audio.current)audio.current.volume=volume/100;},[volume]);

 async function play(){
  const player=audio.current;
  if(!player)return;
  if(!player.getAttribute('src'))player.src=track.audio;
  setError(false);setLoading(true);
  try{await player.play();}
  catch(reason){if(!(reason instanceof DOMException&&reason.name==='AbortError'))setError(true);}
  finally{setLoading(false);}
 }
 function select(next:number,resume=playing){
  const player=audio.current;
  if(!player)return;
  setIndex(next);setError(false);setLoading(false);
  player.src=soundtracks[next].audio;
  if(resume)void play();
 }
 function step(delta:number,resume=playing){
  const position=queue.indexOf(index);
  select(queue[(position+delta+queue.length)%queue.length],resume);
 }

 return <div className="bs-reading-sound" onKeyDown={event=>{if(event.key==='Escape')setOpen(false);}}>
  <audio ref={audio} preload="none" onPlay={()=>setPlaying(true)} onPause={()=>setPlaying(false)}
   onEnded={()=>step(1,true)} onError={()=>{setPlaying(false);setLoading(false);setError(true);}}/>
  <button type="button" title={label('موسيقى القراءة','Reading music')} aria-label={label('موسيقى القراءة','Reading music')}
   aria-expanded={open} data-playing={playing} onClick={()=>setOpen(!open)}><Music2 size={17}/></button>
  {open&&<div className="bs-sound-panel">
   <strong>{label('ساوندتراك القراءة','Reading soundtrack')}</strong>
   <label>{label('المزاج','Mood')}<select value={mood} onChange={event=>{
    const value=event.target.value as Mood;
    setMood(value);
    if(value!=='all'&&track.mood!==value)select(soundtracks.findIndex(item=>item.mood===value));
   }}>
    <option value="all">{label('كل المقطوعات','All recordings')} · {soundtracks.length}</option>
    <option value="quiet">{label('هادي وتركيز','Quiet focus')}</option>
    <option value="bright">{label('خفيف ومبهج','Light and bright')}</option>
   </select></label>
   <label>{label('المقطوعة','Track')}<select dir="auto" value={index} onChange={event=>select(Number(event.target.value))}>
    {queue.map(i=><option key={i} value={i}>{soundtracks[i].title}</option>)}
   </select></label>
   <div className="bs-sound-meta" dir="ltr">{track.composer} · {track.artist}</div>
   <div className="bs-sound-controls" dir="ltr">
    <button type="button" aria-label={label('المقطوعة السابقة','Previous track')} onClick={()=>step(-1)}><SkipBack size={16}/></button>
    <button type="button" aria-label={playing?label('إيقاف مؤقت','Pause'):label('تشغيل','Play')} disabled={loading}
     onClick={()=>playing?audio.current?.pause():void play()}>{playing?<Pause size={17}/>:<Play size={17}/>}</button>
    <button type="button" aria-label={label('المقطوعة التالية','Next track')} onClick={()=>step(1)}><SkipForward size={16}/></button>
   </div>
   <label>{label('مستوى الصوت','Volume')}<input type="range" min="0" max="100" value={volume}
    onChange={event=>setVolume(Number(event.target.value))}/></label>
   <a href={track.source} target="_blank" rel="noreferrer">{track.collection} · CC0</a>
   {error&&<span role="alert">{label('تعذّر تشغيل المقطوعة. جرّب مرة تانية أو اختار مقطوعة تانية.','Could not play this track. Retry or choose another recording.')}</span>}
  </div>}
 </div>;
}
