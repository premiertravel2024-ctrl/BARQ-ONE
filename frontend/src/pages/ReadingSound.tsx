import {useEffect,useRef,useState} from 'react';
import {Music2,Pause,Play} from 'lucide-react';

// Original synthesized reading soundscapes. Audio and note patterns are dedicated
// to the public domain under CC0 1.0.
const scenes=[
 {ar:'غموض هادي',en:'Quiet mystery',notes:[110,130.81,164.81,196]},
 {ar:'ليل هادي',en:'Quiet night',notes:[130.81,164.81,196,293.66]},
 {ar:'فضاء',en:'Space',notes:[98,146.83,220,261.63]},
];

export function ReadingSound({ar}:{ar:boolean}){
 const [open,setOpen]=useState(false);
 const [playing,setPlaying]=useState(false);
 const [scene,setScene]=useState(0);
 const [volume,setVolume]=useState(25);
 const [error,setError]=useState(false);
 const audio=useRef<{context:AudioContext;gain:GainNode;voices:OscillatorNode[]}>();
 useEffect(()=>()=>{void audio.current?.context.close();audio.current=undefined;},[]);

 function selectScene(index:number){
  setScene(index);
  const current=audio.current;
  if(current)current.voices.forEach((voice,i)=>
   voice.frequency.setTargetAtTime(scenes[index].notes[i],current.context.currentTime,.35));
 }

 async function toggle(){
  setError(false);
  try{
   if(!audio.current){
    const context=new AudioContext();
    const gain=context.createGain();
    gain.gain.value=0;
    gain.connect(context.destination);
    const voices=scenes[scene].notes.map((frequency,i)=>{
     const voice=context.createOscillator();
     const envelope=context.createGain();
     const modulation=context.createOscillator();
     const depth=context.createGain();
     envelope.gain.value=.1;
     depth.gain.value=.07;
     modulation.frequency.value=.07+i*.024;
     modulation.connect(depth).connect(envelope.gain);
     voice.frequency.value=frequency;
     voice.type=i===0?'triangle':'sine';
     voice.connect(envelope).connect(gain);
     voice.start();
     modulation.start();
     return voice;
    });
    audio.current={context,gain,voices};
   }
   const current=audio.current;
   if(playing){
    current.gain.gain.setTargetAtTime(0,current.context.currentTime,.08);
    setPlaying(false);
   }else{
    await current.context.resume();
    if(audio.current!==current)return;
    current.gain.gain.setTargetAtTime(volume/100,current.context.currentTime,.12);
    setPlaying(true);
   }
  }catch{if(audio.current)setPlaying(false);setError(true);}
 }

 return <div className="bs-reading-sound">
  <button type="button" title={ar?'موسيقى القراءة':'Reading music'} aria-label={ar?'موسيقى القراءة':'Reading music'}
   aria-expanded={open} data-playing={playing} onClick={()=>setOpen(!open)}><Music2 size={17}/></button>
  {open&&<div className="bs-sound-panel">
   <label>{ar?'أجواء القراءة':'Reading ambience'} <select value={scene} onChange={event=>selectScene(Number(event.target.value))}>
    {scenes.map((item,index)=><option key={item.en} value={index}>{ar?item.ar:item.en}</option>)}
   </select></label>
   <label>{ar?'مستوى الصوت':'Volume'} <input type="range" min="0" max="100" value={volume} onChange={event=>{
    const value=Number(event.target.value);
    setVolume(value);
    const current=audio.current;
    if(current&&playing)current.gain.gain.setTargetAtTime(value/100,current.context.currentTime,.08);
   }}/></label>
   <button type="button" onClick={()=>void toggle()}>{playing?<Pause size={16}/>:<Play size={16}/>}
    {playing?(ar?'إيقاف':'Pause'):(ar?'تشغيل':'Play')}</button>
   <a href="https://creativecommons.org/publicdomain/zero/1.0/" target="_blank" rel="noreferrer">CC0 1.0</a>
   {error&&<span role="alert">{ar?'تعذّر تشغيل الصوت':'Audio could not start'}</span>}
  </div>}
 </div>;
}
