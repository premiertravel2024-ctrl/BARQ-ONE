import {useEffect,useState} from 'react';
import {Button} from '../ui/Button';
import {requestJSON} from '../../lib/backend';
import {useApp} from '../../store';

type Status={enabled:boolean;[key:string]:unknown};
type Permission='microphone'|'files'|'computer';
const endpoints={
 microphone:{read:'/v1/voice/wake/control',write:'/v1/voice/wake/control',method:'POST'},
 files:{read:'/v1/device/index/status',write:'/v1/device/index/settings',method:'PUT'},
 computer:{read:'/v1/computer/status',write:'/v1/computer/settings',method:'PUT'},
} as const;

async function loadStatus(key:Permission){
 const result=await requestJSON<Status|{settings?:Status}>(endpoints[key].read);
 return key==='microphone'?result as Status:result.settings as Status|undefined;
}

export function PrivacySettings({ar,openVoice,openComputer}:{ar:boolean;openVoice:()=>void;openComputer:()=>void}){
 const [values,setValues]=useState<Partial<Record<Permission,Status>>>({});
 const [busy,setBusy]=useState<Permission|null>(null);
 const [error,setError]=useState('');
 const localOnly=useApp(s=>s.options.localOnly);
 const setOptions=useApp(s=>s.setOptions);
 const rows=[
  {id:'microphone',label:ar?'الميكروفون في الخلفية':'Background microphone',open:openVoice},
  {id:'files',label:ar?'فهرسة الملفات':'File indexing',open:openComputer},
  {id:'computer',label:ar?'التحكم في الكمبيوتر':'Computer control',open:openComputer},
 ] as const;
 useEffect(()=>{
  let active=true;
  for(const key of Object.keys(endpoints) as Permission[]){
   void loadStatus(key).then(value=>{if(active&&value)setValues(previous=>({...previous,[key]:value}))}).catch(()=>{});
  }
  return()=>{active=false};
 },[]);

 async function disable(key:Permission){
  setBusy(key);setError('');
  try{
   const settings=await loadStatus(key);
   if(!settings)throw Error(ar?'الحالة غير متاحة':'Permission status unavailable');
   const endpoint=endpoints[key];
   const changes=key==='microphone'?{wake_computer_enabled:false}:key==='files'?{content_enabled:false}:{};
   if(key==='computer')await requestJSON('/v1/computer/stop',{method:'POST'});
   await requestJSON(endpoint.write,{method:endpoint.method,body:JSON.stringify({...settings,...changes,enabled:false})});
   if(key==='microphone'||key==='computer'){
    window.dispatchEvent(new Event('barq-handsfree-stop'));
    window.dispatchEvent(new CustomEvent('barq-voice-computer-permission-updated',{detail:{enabled:false}}));
   }
   setValues(previous=>({...previous,[key]:{...settings,enabled:false}}));
  }catch(error){setError(error instanceof Error?error.message:String(error))}
  finally{setBusy(null)}
 }

 return <section className="barq-settings-card space-y-4">
  <label className="flex items-center gap-3 text-sm"><input type="checkbox" checked={localOnly} onChange={event=>setOptions({localOnly:event.target.checked})}/>
   {ar?'معالجة المحادثة والمرفقات محليًا فقط':'Process chat and its attachments locally only'}
  </label>
  {rows.map(row=><div key={row.id} className="flex flex-wrap items-center gap-2 border-t border-stroke pt-3">
   <div className="me-auto"><h3 className="text-sm font-semibold">{row.label}</h3><p className="text-xs text-secondary">
    {values[row.id]?.enabled===true?(ar?'مفعّل':'Enabled'):values[row.id]?.enabled===false?(ar?'متوقف':'Disabled'):(ar?'الحالة غير متاحة':'Status unavailable')}
   </p></div>
   <Button size="sm" variant="secondary" onClick={row.open}>{ar?'التفاصيل':'Details'}</Button>
   <Button size="sm" variant="secondary" disabled={!!busy||values[row.id]?.enabled!==true}
    onClick={()=>void disable(row.id)}>{busy===row.id?(ar?'جاري الإيقاف…':'Turning off…'):(ar?'إيقاف':'Turn off')}</Button>
  </div>)}
  {error&&<p role="alert" className="text-sm text-danger">{error}</p>}
 </section>;
}
