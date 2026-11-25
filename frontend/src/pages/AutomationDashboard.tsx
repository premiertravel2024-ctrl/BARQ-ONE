import {Switch} from '../components/ui/Switch';
import {useAppView} from '../lib/appContext';
import {useEffect, useState} from 'react';
import {AlarmClock, Bell, CalendarDays, Check, Clock3, Cloud, CloudRain, CloudSun, Compass, Droplets, MapPin, Pause, Play, Plus, RefreshCw, Sun, Sunrise, Trash2, Wind} from 'lucide-react';
import {requestJSON} from '../lib/backend';
import {useApp} from '../store';
import {CLOCK_ZONES,DAY_CHANGED,FOCUS_DEADLINE,clockZones,focusDeadline,nextAlarm} from '../components/layout/DayStatus';
import './automation.css';

type City = 'riyadh'|'jeddah'|'makkah'|'madinah'|'dammam'|'cairo';
type Weather = {
 temperature:number; feels_like:number;humidity:number;wind_kmh:number;
 weather_code:number;high:number;low:number;source:string;
 hourly?:Array<{time:string;temperature:number;rain:number;code:number}>;
 forecast?:Array<{date:string;high:number;low:number;code:number}>;
};
type Prayer = {key:string;label:string;time:string;at:string};
type Overview = {city:City;city_label:string;timezone:string;updated_at:string;
 weather:Weather|null;prayers:Prayer[];next_prayer:Prayer|null;errors:string[];prayer_source:string};
type Alarm = {id:string;time:string;label:string;repeat:boolean;enabled:boolean;last_fired:string;snoozed_until?:string;weekdays?:number[];sound?:string};
const CITY_NAMES:Record<City,string>={riyadh:'الرياض',jeddah:'جدة',makkah:'مكة المكرمة',madinah:'المدينة المنورة',dammam:'الدمام',cairo:'القاهرة'};
const CITY_NAMES_EN:Record<City,string>={riyadh:'Riyadh',jeddah:'Jeddah',makkah:'Makkah',madinah:'Madinah',dammam:'Dammam',cairo:'Cairo'};
const PRAYER_NAMES:Record<string,string>={Fajr:'Fajr',Dhuhr:'Dhuhr',Asr:'Asr',Maghrib:'Maghrib',Isha:'Isha'};
function saveCity(value:City){try{localStorage.setItem('barq-automation-city',value)}catch{}}
function initialCity():City{try{const stored=localStorage.getItem('barq-automation-city');return stored && stored in CITY_NAMES?stored as City:'riyadh'}catch{return 'riyadh'}}
function pad(value:number){return String(value).padStart(2,'0')}
function duration(seconds:number){return [Math.floor(seconds/3600),Math.floor(seconds/60)%60,seconds%60].map(pad).join(':')}
function weatherLabel(code:number,ar:boolean):string {
 if(code===0)return ar?'صافي':'Clear';
 if(code<=3)return ar?'غائم جزئيًا':'Partly cloudy';
 if(code===45||code===48)return ar?'ضباب':'Fog';
 if(code>=51 && code<=67)return ar?'أمطار خفيفة':'Rain';
 if(code>=80 && code<=82)return ar?'أمطار':'Rain';
 if(code>=95)return ar?'عواصف رعدية':'Thunderstorm';
 return ar?'متغير':'Variable';
}
function safeClock(value:string){const t=new Date(value);return Number.isFinite(t.getTime())?t.getTime():0}
export function AutomationDashboard(){
 const ar=useApp(s=>s.language)==='ar';
 const [city,setCity]=useState<City>(initialCity);
 const [overview,setOverview]=useState<Overview|null>(null);
 const [alarms,setAlarms]=useState<Alarm[]>([]);
 const [loading,setLoading]=useState(false);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [now,setNow]=useState(Date.now());
 const [when,setWhen]=useState('07:00');
 const [label,setLabel]=useState('');
 const [repeat,setRepeat]=useState(true);
 const [weekdays,setWeekdays]=useState<number[]>([]);
 const [sound,setSound]=useState('classic');
 const [editing,setEditing]=useState<string>();
 const [zones,setZones]=useState(clockZones);
 const [focusUntil,setFocusUntil]=useState<number|null>(()=>focusDeadline()||null);
 const [focusSeconds,setFocusSeconds]=useState(()=>focusDeadline()?Math.max(0,Math.ceil((focusDeadline()-Date.now())/1000)):25*60);
 const [focusActive,setFocusActive]=useState(()=>focusDeadline()>Date.now());
 const [notice,setNotice]=useState('');
 async function fetchAlarms(){const data=await requestJSON<{alarms:Alarm[]}>('/v1/automation/alarms');setAlarms(data.alarms)}
 useEffect(()=>{
  let live=true;
  const load=async()=>{
   setLoading(true);
   try{
    const result=await requestJSON<Overview>('/v1/automation/overview?city='+encodeURIComponent(city));
    if(live){setOverview(result);setError('')}
   }catch(e){if(live){setOverview(null);setError(e instanceof Error?e.message:String(e))}}
   finally{if(live)setLoading(false)}
  };
  void load();
  const refresh=window.setInterval(()=>void load(),10*60*1000);
  return()=>{live=false;window.clearInterval(refresh)};
 },[city]);
 useEffect(()=>{
  void fetchAlarms().catch(e=>setError(e instanceof Error?e.message:String(e)));
 },[]);
 useEffect(()=>{
  const timer=window.setInterval(()=>{
   const time=Date.now();setNow(time);
   if(focusActive&&focusUntil!==null){
    const remaining=Math.max(0,Math.ceil((focusUntil-time)/1000));
    setFocusSeconds(remaining);
    if(remaining===0){
     setFocusActive(false);setFocusUntil(null);setNotice(ar?'انتهى وقت التركيز!':'Focus session complete!');
     try{if('Notification' in window && Notification.permission==='granted')new Notification('BARQ ONE',{body:ar?'انتهى وقت التركيز':'Focus session finished'})}catch{}
    }
   }
  },1000);
  return()=>window.clearInterval(timer);
 },[focusActive,focusUntil,ar]);
 async function addAlarm(event:React.FormEvent<HTMLFormElement>){
  event.preventDefault();if(!when||!label.trim()||busy)return;
  setBusy(true);setError('');
  try{
   await requestJSON('/v1/automation/alarms'+(editing?'/'+editing:''),{method:editing?'PATCH':'POST',body:JSON.stringify({time:when,label:label.trim(),repeat,weekdays,sound})});
   setEditing(undefined);setWeekdays([]);setSound('classic');window.dispatchEvent(new Event(DAY_CHANGED));
   await fetchAlarms();setLabel('');setNotice(ar?'المنبّه اتحفظ على الجهاز.':'Alarm saved locally.');
  }catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}
 }
 async function modifyAlarm(id:string,enabled?:boolean){
  setBusy(true);setError('');
  try{
   if(enabled===undefined)await requestJSON('/v1/automation/alarms/'+id,{method:'DELETE'});
   else await requestJSON('/v1/automation/alarms/'+id,{method:'PATCH',body:JSON.stringify({enabled})});
   await fetchAlarms();window.dispatchEvent(new Event(DAY_CHANGED));
  }catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}
 }
 function setFocus(minutes:number){
  setFocusSeconds(minutes*60);setFocusActive(false);setFocusUntil(null);
  localStorage.removeItem(FOCUS_DEADLINE);
 }
 function toggleFocus(){
  if(focusActive){setFocusActive(false);setFocusUntil(null);localStorage.removeItem(FOCUS_DEADLINE);return;}
  if(focusSeconds<=0)return;
  const deadline=Date.now()+focusSeconds*1000;
  localStorage.setItem(FOCUS_DEADLINE,String(deadline));setFocusUntil(deadline);setFocusActive(true);
 }
 async function snooze(id:string){
  setBusy(true);setError('');
  try{
   await requestJSON('/v1/automation/alarms/'+id+'/snooze',{method:'POST'});
   await fetchAlarms();window.dispatchEvent(new Event(DAY_CHANGED));
  }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
 }
 const nextWake=nextAlarm(alarms,now);
 const weather=overview?.weather;
 const next=overview?.next_prayer;
 const until=next?Math.max(0,Math.floor((safeClock(next.at)-now)/1000)):null;
 const overcast=weather?(weather.weather_code>=51||weather.weather_code===45||weather.weather_code===48):false;
 const WeatherIcon=overcast?CloudRain:weather?.weather_code===0?Sun:CloudSun;
 const currentTime=new Intl.DateTimeFormat(ar?'ar-EG':'en-GB',{timeZone:overview?.timezone||'Asia/Riyadh',hour:'2-digit',minute:'2-digit'}).format(new Date(now));
 useAppView('automation',{mode:focusActive?'focus timer':'dashboard',count:alarms.length,status:loading?'loading':error?'unavailable':undefined});
 return <div className="barq-automation" dir={ar?'rtl':'ltr'}>
  <header className="ba-hero">
   <div><h2>{ar?'مهامي':'My tasks'}</h2><p>{new Intl.DateTimeFormat(ar?'ar-EG':'en-GB',{dateStyle:'full',timeZone:overview?.timezone||'Asia/Riyadh'}).format(now)}</p></div>
   <div className="ba-time"><Clock3 size={17}/><strong dir="ltr">{currentTime}</strong><span>{ar?'توقيت المدينة':'City time'}</span></div>
  </header>
  <section data-spotlight className="ba-card ba-world" aria-label={ar?'الساعات العالمية':'World clocks'}>
   {CLOCK_ZONES.filter(([zone])=>zones.includes(zone)).map(([zone,arabic,english])=><div key={zone}>
    <strong dir="ltr">{new Intl.DateTimeFormat(ar?'ar-EG':'en-GB',{timeZone:zone,hour:'2-digit',minute:'2-digit'}).format(now)}</strong><small>{ar?arabic:english}</small>
   </div>)}
   <details><summary>{ar?'اختار الساعات':'Choose clocks'}</summary>
    {CLOCK_ZONES.map(([zone,arabic,english])=><label key={zone}><input type="checkbox" checked={zones.includes(zone)}
     disabled={zones.length===1&&zones.includes(zone)} onChange={()=>{
      const next=zones.includes(zone)?zones.filter(item=>item!==zone):[...zones,zone];
      setZones(next);localStorage.setItem('barq-clock-zones',JSON.stringify(next));
     }}/>{ar?arabic:english}</label>)}
   </details>
  </section>
  {error&&<p className="ba-error" role="alert">{error}</p>}
  {notice&&<p className="ba-notice" role="status">{notice}</p>}
  <div className="ba-location">
   <div className="ba-location-title"><MapPin size={17}/><strong>{ar?'المدينة':'City'}</strong></div>
   <select value={city} aria-label={ar?'اختيار المدينة':'Choose city'} onChange={e=>{const value=e.target.value as City;setCity(value);saveCity(value);setOverview(null);window.dispatchEvent(new Event(DAY_CHANGED))}}>
    {(Object.keys(CITY_NAMES) as City[]).map(key=><option key={key} value={key}>{ar?CITY_NAMES[key]:CITY_NAMES_EN[key]}</option>)}
   </select>
   
   <button type="button" className="ba-icon-btn" onClick={()=>{setCity(previous=>{setOverview(null);return previous});void requestJSON<Overview>('/v1/automation/overview?city='+encodeURIComponent(city)).then(setOverview).catch(e=>setError(String(e)))}} aria-label={ar?'تحديث':'Refresh'}><RefreshCw size={16}/></button>
  </div>
  <div className="ba-summary-grid">
   <section data-spotlight className="ba-card ba-weather">
    <div className="ba-card-top"><span><Cloud size={17}/>{ar?'حالة الطقس':'Weather'}</span><span>{ar?CITY_NAMES[city]:CITY_NAMES_EN[city]}</span></div>
    {weather?<><div className="ba-temp"><WeatherIcon size={45}/><strong dir="ltr">{weather.temperature}°</strong><div><b>{weatherLabel(weather.weather_code,ar)}</b><small>{ar?'المحسوسة':'Feels like'} {weather.feels_like}°</small></div></div>
     <div className="ba-weather-stats"><span><Sunrise size={15}/>{ar?'العظمى / الصغرى':'High / Low'} <b dir="ltr">{weather.high}° / {weather.low}°</b></span><span><Droplets size={15}/>{weather.humidity}%</span><span><Wind size={15}/>{weather.wind_kmh} km/h</span></div>
     <small className="ba-attribution"><a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">Open-Meteo</a> · {ar?'آخر تحديث':'Updated'} {overview&&new Intl.DateTimeFormat(ar?'ar-EG':'en-GB',{timeZone:overview.timezone,hour:'2-digit',minute:'2-digit'}).format(new Date(overview.updated_at))}</small>
    </>:<div className="ba-empty">{loading?(ar?'بنجيب حالة الطقس...':'Loading weather...'):(ar?'الطقس مش متاح دلوقتي.':'Weather unavailable.')}</div>}
   </section>
   <section data-spotlight className="ba-card ba-prayer-next">
    <div className="ba-card-top"><span><Compass size={17}/>{ar?'الصلاة القادمة':'Next prayer'}</span><span>{ar?'توقيت':'Time zone'} {overview?.timezone||'—'}</span></div>
    {next?<><div className="ba-prayer-name">{ar?next.label:PRAYER_NAMES[next.key]||next.key}</div><div className="ba-countdown" dir="ltr">{until!==null?duration(until):'--:--:--'}</div>
      <span className="ba-prayer-at" dir="ltr">{next.time}</span>
      <p className="ba-muted">{ar?'العدّ التنازلي للصلاة الجاية':'Countdown to the upcoming prayer'}</p>
     </>:<div className="ba-empty">{loading?(ar?'بنجيب مواعيد الصلاة...':'Loading prayer times...'):(ar?'مواعيد الصلاة مش متاحة حاليًا.':'Prayer schedule unavailable.')}</div>}
   </section>
  </div>
  <section data-spotlight className="ba-card ba-forecast" aria-label={ar?'توقعات الطقس للأيام الجاية':'7-day weather outlook'}>
   <div className="ba-section-head"><div><CloudSun size={18}/><h3>{ar?'توقعات الأسبوع':'7-day forecast'}</h3></div>
    <span>{ar?'البيانات من Open-Meteo':'Source: Open-Meteo'}</span></div>
   {!!weather?.hourly?.length&&<div className="ba-hourly" aria-label={ar?'الطقس خلال الساعات الجاية':'Upcoming hourly weather'}>
    {weather.hourly.map(hour=><div key={hour.time}><time dir="ltr">{hour.time.slice(11,16)}</time><strong>{hour.temperature}°</strong>
     <small title={ar?'احتمال المطر':'Rain probability'}><Droplets size={12}/>{hour.rain}%</small></div>)}
   </div>}
   {weather?.forecast?.length?
    <div className="ba-forecast-strip">{weather.forecast.map((day,index)=>{
     const DateLabel=new Date(day.date+'T12:00:00');
     const dayName=DateLabel.toLocaleDateString(ar?'ar-SA':'en-US',{weekday:'short'});
     const Icon=day.code===0?Sun:day.code>=51?CloudRain:CloudSun;
     return <div className={'ba-forecast-day'+(index===0?' ba-forecast-today':'')} key={day.date}>
      <small>{index===0?(ar?'النهارده':'Today'):dayName}</small><Icon size={27}/>
      <strong dir="ltr">{day.high}°</strong><span dir="ltr">{day.low}°</span>
      <i className="ba-forecast-bar" style={{height:Math.max(5,Math.min(22,(day.high-day.low)*1.6))+'px'}}/>
     </div>;
    })}</div>:<p className="ba-muted">{loading?(ar?'بنجيب توقعات الأسبوع...':'Loading forecast...'):(ar?'مفيش توقعات متاحة.':'Forecast unavailable.')}</p>}
  </section>
  <div className="ba-lower-grid">
   <div className="ba-side-stack">
   <section className="ba-card">
    <div className="ba-section-head"><div><CalendarDays size={18}/><h3>{ar?'مواقيت الصلاة اليوم':'Today’s prayer times'}</h3></div><span>{ar?'طريقة أم القرى للسعودية':'Local calculation method'}</span></div>
    <div className="ba-prayer-list">
     {overview?.prayers.length?overview.prayers.map(p=><div className={'ba-prayer-item'+(next?.key===p.key&&new Date(next.at).toDateString()===new Date(p.at).toDateString()?' ba-current':'')} key={p.key}><span>{ar?p.label:PRAYER_NAMES[p.key]||p.key}</span><strong dir="ltr">{p.time}</strong></div>):
      <p className="ba-muted">{loading?(ar?'جاري التحميل':'Loading'):(ar?'لا توجد أوقات متاحة الآن':'No available times')}</p>}
    </div>
    <small className="ba-attribution"><a href="https://aladhan.com/prayer-times-api" target="_blank" rel="noopener noreferrer">AlAdhan</a> · {ar?'ممكن تختلف الدقائق عن مسجدك':'Check local mosque for any differences'}</small>
   </section>
   <section data-spotlight className="ba-card ba-focus">
    <div className="ba-section-head"><div><Clock3 size={18}/><h3>{ar?'وقت التركيز':'Focus timer'}</h3></div></div>
    <div className="ba-focus-clock" dir="ltr">{duration(focusSeconds)}</div>
    <div className="ba-focus-controls">
     <label>{ar?'المدة بالدقايق':'Duration in minutes'}
      <input type="number" min={1} max={180} defaultValue={25} disabled={focusActive}
       onChange={event=>{const value=event.currentTarget.valueAsNumber;if(Number.isInteger(value)&&value>=1&&value<=180)setFocus(value);}}/>
     </label>
     <button type="button" className="ba-primary" onClick={toggleFocus} disabled={!focusActive&&focusSeconds===0}>
      {focusActive?<Pause size={16}/>:<Play size={16}/>} {focusActive?(ar?'إيقاف مؤقت':'Pause'):(ar?'ابدأ التركيز':'Start focus')}
     </button>
     <button type="button" onClick={()=>setFocus(25)}>{ar?'إعادة ضبط':'Reset'}</button>
    </div>
    <p className="ba-muted">{ar?'مؤقت التركيز بيكمل وإنت بتتنقّل جوّه برق.':'The timer keeps running as you move around BARQ.'}</p>
   </section>
   </div>
   <section className="ba-card">
    <div className="ba-section-head"><div><AlarmClock size={18}/><h3>{ar?'المنبّهات':'Alarms'}</h3></div><span>{alarms.length} / 30</span></div>
    {nextWake&&<p className="ba-muted">{ar?'المنبّه الجاي':'Next alarm'} · <bdi>{nextWake.label} {new Date(nextWake.at).toLocaleTimeString(ar?'ar-EG':'en-GB',{hour:'2-digit',minute:'2-digit'})}</bdi></p>}
    <form onSubmit={e=>void addAlarm(e)} className="ba-alarm-form">
      <label>{ar?'الوقت':'Time'}<input type="time" value={when} onChange={e=>setWhen(e.target.value)} required/></label>
      <label>{ar?'عنوان التنبيه':'Alarm label'}<input value={label} maxLength={70} onChange={e=>setLabel(e.target.value)} placeholder={ar?'مثلاً: اجتماع أو استراحة':'e.g. meeting'} required/></label>
      <Switch checked={repeat} onChange={setRepeat} showLabel label={ar?'تكرار المنبّه':'Repeat alarm'}/>
      {repeat&&<fieldset className="ba-alarm-days"><legend>{ar?'أيام التكرار':'Repeat days'}</legend>
       <div className="ba-weekdays">
       {(ar?['الاتنين','التلات','الأربع','الخميس','الجمعة','السبت','الأحد']:['Mon','Tue','Wed','Thu','Fri','Sat','Sun']).map((day,index)=>
        <button key={day} type="button" aria-pressed={weekdays.includes(index)} onClick={()=>setWeekdays(weekdays.includes(index)?weekdays.filter(item=>item!==index):[...weekdays,index])}>{day}</button>)}
       </div><small>{ar?'لو مفيش يوم محدد، المنبّه هيتكرر يوميًا.':'With no days selected, the alarm repeats daily.'}</small>
      </fieldset>}
      <label>{ar?'صوت المنبّه':'Alarm sound'}<select value={sound} onChange={event=>setSound(event.target.value)}>
       <option value="classic">{ar?'كلاسيكي':'Classic'}</option><option value="soft">{ar?'هادي':'Soft'}</option><option value="alert">{ar?'تنبيه واضح':'Alert'}</option>
      </select></label>
      <button type="submit" className="ba-primary" disabled={busy||!label.trim()}><Plus size={16}/>{editing?(ar?'احفظ التعديل':'Save edit'):(ar?'إضافة منبّه':'Add alarm')}</button>
     {editing&&<button type="button" onClick={()=>{setEditing(undefined);setLabel('');}}>{ar?'إلغاء':'Cancel'}</button>}
    </form>
    <div className="ba-alarm-list">
     {alarms.length===0?<p className="ba-muted">{ar?'مفيش منبّهات لسه.':'No alarms yet.'}</p>:alarms.map(alarm=><div key={alarm.id} className={'ba-alarm-item'+(!alarm.enabled?' ba-alarm-off':'')}>
       <div><b dir="ltr">{alarm.time}</b><span>{alarm.label}</span><small>{alarm.repeat?(alarm.weekdays?.length?(ar?'أيام مختارة':'Selected days'):(ar?'يومي':'Daily')):(ar?'مرة واحدة':'One time')}</small>{alarm.snoozed_until&&<small>{ar?'غفوة لحد':'Snoozed until'} {new Date(alarm.snoozed_until).toLocaleTimeString(ar?'ar-EG':'en-GB',{hour:'2-digit',minute:'2-digit'})}</small>}{alarm.last_fired&&<small>{ar?'آخر تشغيل':'Last rang'} <bdi>{alarm.last_fired}</bdi></small>}</div>
       <div className="ba-alarm-actions">
        <button type="button" disabled={busy} onClick={()=>{setEditing(alarm.id);setWhen(alarm.time);setRepeat(alarm.repeat);setLabel(alarm.label);setWeekdays(alarm.weekdays||[]);setSound(alarm.sound||'classic');}}>{ar?'عدّل':'Edit'}</button>
        {alarm.last_fired&&<button type="button" disabled={busy} onClick={()=>void snooze(alarm.id)}>{ar?'غفوة ٥ دقايق':'Snooze 5 min'}</button>}
        <button type="button" aria-label={alarm.enabled?'Disable alarm':'Enable alarm'} onClick={()=>void modifyAlarm(alarm.id,!alarm.enabled)} disabled={busy}>{alarm.enabled?<Check size={16}/>:<Plus size={16}/>}</button><button type="button" aria-label={ar?'حذف المنبّه':'Delete alarm'} disabled={busy} onClick={()=>void modifyAlarm(alarm.id)}><Trash2 size={16}/></button></div>
      </div>)}
    </div>
    <p className="ba-muted ba-note"><Bell size={14}/>{ar?'المنبّهات بتشتغل على الكمبيوتر طول ما خدمة برق مفتوحة، حتى لو النافذة مصغّرة أو برق في الـTray.':'Alarms trigger on this computer while BARQ is running, including while in the system tray.'}</p>
   </section>

  </div>
 </div>;
}
