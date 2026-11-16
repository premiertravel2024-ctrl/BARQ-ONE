import {useEffect,useState} from 'react';
import {AudioLines,Volume2,VolumeX} from 'lucide-react';
import {useApp} from '../../store';
import {isSpeechPlaying} from '../../lib/speechGlow';
import {Button} from '../ui/Button';
import {getHandsFreeState} from './HandsFreeVoice';
import {HologramCore} from './HologramCore';
import './hologram.css';

const labels={
 ar:{idle:'جاهز أكلمك',connecting:'بوصل الصوت…',listening:'سامعك',hearing:'سامع كلامك',processing:'بفهم طلبك…',executing:'ببدأ التنفيذ…',approval:'مستني موافقتك',speaking:'برد عليك',busy:'شغال على طلبك…'},
 en:{idle:'Ready to talk',connecting:'Connecting…',listening:'Listening',hearing:'Hearing you',processing:'Checking your request…',executing:'Starting the action…',approval:'Waiting for approval',speaking:'Speaking',busy:'Working on your request…'},
};

export function Hologram({onStart}:{onStart:()=>void}){
 const ar=useApp(state=>state.language)==='ar';
 const streaming=useApp(state=>state.streaming);
 const [voice,setVoice]=useState(getHandsFreeState);
 const [speaking,setSpeaking]=useState(isSpeechPlaying);
 const [lightweight,setLightweight]=useState(()=>localStorage.getItem('barq-hologram-quality')==='low');
 useEffect(()=>{
  const syncVoice=()=>setVoice(getHandsFreeState());
  const syncPlayback=()=>setSpeaking(isSpeechPlaying());
  window.addEventListener('barq-handsfree-state',syncVoice);
  window.addEventListener('barq-speech-playback',syncPlayback);
  syncVoice();
  syncPlayback();
  return()=>{
   window.removeEventListener('barq-handsfree-state',syncVoice);
   window.removeEventListener('barq-speech-playback',syncPlayback);
  };
 },[]);
 const task=voice.task;
 const working=task&&['planning','running','approval'].includes(task.status);
 const phase=task?.pending?'approval':speaking?'speaking':
  voice.phase==='hearing'||voice.phase==='processing'||voice.phase==='executing'?voice.phase:
  working||streaming?'busy':voice.phase;
 const status=labels[ar?'ar':'en'][phase];
 const caption=working?(task?.message||voice.caption):(voice.caption||task?.message);
 function toggleVoice(){
  if(getHandsFreeState().active)window.dispatchEvent(new Event('barq-handsfree-stop'));
  else onStart();
 }
 return <section className="barq-hologram" data-phase={phase} aria-label={ar?'هولوجرام برق':'BARQ hologram'}>
  <div className="barq-hologram-console">
   <div className="barq-hologram-stage">
    <div className="barq-hologram-header">
     <h2>{ar?'برق':'BARQ'}</h2>
     <p role="status">{status}</p>
    </div>
    <HologramCore phase={phase} level={voice.inputLevel/100} lightweight={lightweight}/>
   </div>
  <div className="barq-hologram-controls">
   {task?.is_sequence&&!!task.steps?.length&&<progress className="barq-hologram-progress" max={task.steps.length}
    value={task.verified_steps??0} aria-label={ar?'خطوات التنفيذ المتحقق منها':'Verified execution steps'}/>}
   {caption&&<p className="barq-hologram-caption" dir="auto">{caption}</p>}
   <div className="flex flex-wrap justify-center gap-2">
    <Button variant={voice.active?'secondary':'primary'} icon={<AudioLines size={18}/>} onClick={toggleVoice}>
     {voice.active?(ar?'اقفل الصوت':'End voice'):(ar?'اتكلم مع برق':'Talk to BARQ')}
    </Button>
    {voice.active&&speaking&&<Button icon={<VolumeX size={18}/>} title="Alt+V" onClick={()=>{window.dispatchEvent(new Event('barq-handsfree-interrupt'));}}>
     {ar?'وقف الرد':'Interrupt reply'}
    </Button>}
    {(voice.speakerBlocked||voice.micBlocked)&&<Button icon={<Volume2 size={18}/>} onClick={()=>{window.dispatchEvent(new Event('barq-handsfree-unlock'));}}>
     {voice.micBlocked?(ar?'فعّل الميكروفون':'Enable microphone'):(ar?'فعّل السماعة':'Enable audio')}
    </Button>}
   </div>
   <label className="barq-hologram-quality"><input type="checkbox" checked={lightweight} onChange={e=>{
    setLightweight(e.target.checked);localStorage.setItem('barq-hologram-quality',e.target.checked?'low':'default');
   }}/>{ar?'عرض خفيف':'Low graphics'}</label>
   {(voice.timings.audioMs!==undefined||voice.timings.executionMs!==undefined)&&<details className="barq-hologram-timings">
    <summary>{ar?'زمن الاستجابة':'Response timing'}</summary>
    {voice.timings.executionMs!==undefined&&<p>{ar?'بداية معالجة الأمر':'Command dispatch'} · {(voice.timings.executionMs/1000).toFixed(2)} {ar?'ث':'s'}</p>}
    {voice.timings.audioMs!==undefined&&<p>{ar?'بداية الرد الصوتي':'Audio onset'} · {(voice.timings.audioMs/1000).toFixed(2)} {ar?'ث':'s'}</p>}
   </details>}
  </div>
  </div>
 </section>;
}
