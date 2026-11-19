import {useEffect,useState} from 'react';
import {AlarmClock,Clock3,CloudSun} from 'lucide-react';
import {requestJSON} from '../../lib/backend';

export const DAY_CHANGED='barq-day-changed';
export const FOCUS_DEADLINE='barq-focus-until';
const DEFAULT_ZONES=['Asia/Riyadh','Africa/Cairo','Asia/Dubai'];
export const CLOCK_ZONES=[
 ['Asia/Riyadh','الرياض','Riyadh'],['Africa/Cairo','القاهرة','Cairo'],['Asia/Dubai','دبي','Dubai'],
 ['Europe/London','لندن','London'],['America/New_York','نيويورك','New York'],['Asia/Tokyo','طوكيو','Tokyo'],
] as const;
export function clockZones():string[]{
 try{
  const saved:unknown=JSON.parse(localStorage.getItem('barq-clock-zones')||'null');
  if(Array.isArray(saved)&&saved.length&&saved.every(value=>CLOCK_ZONES.some(([zone])=>zone===value)))return saved;
 }catch{/* Default clocks are always available. */}
 return DEFAULT_ZONES;
}
export function focusDeadline():number{
 return Number(localStorage.getItem(FOCUS_DEADLINE))||0;
}

type Alarm={time:string;label:string;enabled:boolean;snoozed_until?:string;last_fired?:string;repeat?:boolean;weekdays?:number[]};
export function nextAlarm(alarms:Alarm[],now:number){
 return alarms.flatMap(alarm=>{
  const timestamps:number[]=[];
  if(alarm.enabled&&/^\d{2}:\d{2}$/.test(alarm.time)){
   const target=new Date(now);
   const [hours,minutes]=alarm.time.split(':').map(Number);
   target.setHours(hours,minutes,0,0);
   if(target.getTime()+60000<=now||alarm.last_fired?.endsWith(alarm.time)&&alarm.last_fired.slice(0,10)===
    [target.getFullYear(),String(target.getMonth()+1).padStart(2,'0'),String(target.getDate()).padStart(2,'0')].join('-'))target.setDate(target.getDate()+1);
   if(alarm.repeat&&alarm.weekdays?.length){
    const days=alarm.weekdays;
    for(let offset=0;offset<7&&!days.includes((target.getDay()+6)%7);offset++)target.setDate(target.getDate()+1);
   }
   timestamps.push(target.getTime());
  }
  const snoozed=Date.parse(alarm.snoozed_until||'');
  if(snoozed>now)timestamps.push(snoozed);
  return timestamps.map(at=>({label:alarm.label,at}));
 }).sort((a,b)=>a.at-b.at)[0];
}

export function DayStatus({ar,onOpen,onFocusDone}:{ar:boolean;onOpen:()=>void;onFocusDone:()=>void}){
 const [now,setNow]=useState(Date.now);
 const [alarms,setAlarms]=useState<Alarm[]>([]);
 const [weather,setWeather]=useState<{temperature:number;city:string}>();
 const [zone,setZone]=useState('Asia/Riyadh');
 const [focusDone,setFocusDone]=useState(false);
 const timeFormat=(zone?:string)=>new Intl.DateTimeFormat(ar?'ar-EG':'en-GB',{timeZone:zone,hour:'2-digit',minute:'2-digit'});
 useEffect(()=>{
  const clock=window.setInterval(()=>{
   const instant=Date.now();
   setNow(instant);
   const deadline=focusDeadline();
   if(deadline&&instant>=deadline){
    localStorage.removeItem(FOCUS_DEADLINE);
    setFocusDone(true);
    window.dispatchEvent(new Event(DAY_CHANGED));
   }
  },1000);
  return()=>window.clearInterval(clock);
 },[]);
 useEffect(()=>{
  if(focusDone){onFocusDone();setFocusDone(false);}
 },[focusDone,onFocusDone]);
 useEffect(()=>{
  let active=true;
  const readAlarms=()=>void requestJSON<{alarms:Alarm[]}>('/v1/automation/alarms')
   .then(result=>{if(active)setAlarms(result.alarms);}).catch(()=>{});
  const readWeather=()=>{
   const city=localStorage.getItem('barq-automation-city')||'riyadh';
   void requestJSON<{city_label:string;timezone:string;weather:{temperature:number}|null}>('/v1/automation/overview?city='+encodeURIComponent(city))
    .then(result=>{
     if(active&&city===(localStorage.getItem('barq-automation-city')||'riyadh')){
      setZone(result.timezone);
      setWeather(result.weather?{temperature:result.weather.temperature,city:ar?result.city_label:city}:undefined);
     }
    }).catch(()=>{});
  };
  const refresh=()=>{readAlarms();readWeather();};
  refresh();
  const alarmPoll=window.setInterval(readAlarms,30000);
  const weatherPoll=window.setInterval(readWeather,600000);
  window.addEventListener(DAY_CHANGED,refresh);
  return()=>{active=false;window.clearInterval(alarmPoll);window.clearInterval(weatherPoll);window.removeEventListener(DAY_CHANGED,refresh);};
 },[ar]);
 const next=nextAlarm(alarms,now);
 const date=new Intl.DateTimeFormat(ar?'ar-EG':'en-GB',{dateStyle:'full',timeZone:zone}).format(now);
 return <button type="button" className="ops-day-status" onClick={onOpen}
  aria-label={ar?'الساعة والطقس والمنبّهات':'Clock, weather and alarms'}
  title={[date,weather&&weather.city+' '+weather.temperature+'°',next&&next.label+' '+timeFormat().format(next.at)].filter(Boolean).join(' · ')}>
  <Clock3 size={15}/><bdi>{timeFormat(zone).format(now)}</bdi>
  {weather&&<span className="ops-day-weather"><CloudSun size={15}/><bdi>{weather.temperature}°</bdi></span>}
  {next&&<span className="ops-day-alarm"><AlarmClock size={15}/><bdi>{timeFormat().format(next.at)}</bdi></span>}
 </button>;
}
