import {useCallback,useEffect,useState,type FormEvent} from 'react';
import {Cloud,RefreshCw} from 'lucide-react';
import {APIError,requestJSON} from '../lib/backend';
import {driveSyncDevice} from '../lib/driveSync';
import type {DriveBook} from './DriveBooks';

type Connection={connected:boolean;pending:boolean;failed:boolean;folder:string;sync?:boolean};
type Item={id:string;title:string;group:string;cover:string|null};
const root='/v1/reading/drive';

export async function loadCloudBooks(){
 const result=await requestJSON<{books:Item[]}>(root+'/catalogue');
 return result.books.map<DriveBook>(item=>({
  edition:{id:'google:'+item.id,title:item.title,format:'pdf',driveId:item.id},
  group:item.group,coverId:item.cover||undefined,
 })).sort((a,b)=>a.edition.title.localeCompare(b.edition.title,undefined,{numeric:true}));
}

export function useCloudBooks(){
 const [books,setBooks]=useState<DriveBook[]>();
 const [loading,setLoading]=useState(true);
 const [failed,setFailed]=useState(false);
 const [attempt,setAttempt]=useState(0);
 useEffect(()=>{
  let live=true;
  setLoading(true);setFailed(false);
  void requestJSON<Connection>(root+'/status')
   .then(status=>status.connected?loadCloudBooks():undefined)
   .then(items=>{if(live)setBooks(items);})
   .catch(error=>{if(live&&(!(error instanceof APIError)||error.status!==404))setFailed(true);})
   .finally(()=>{if(live)setLoading(false);});
  return()=>{live=false;};
 },[attempt]);
 return {books,loading,failed,retry:()=>setAttempt(value=>value+1)};
}

export function CloudReading({ar}:{ar:boolean}){
 const [connection,setConnection]=useState<Connection>();
 const [sync,setSync]=useState(false);
 const [config,setConfig]=useState(false);
 const [folder,setFolder]=useState('');
 const [client,setClient]=useState('');
 const [secret,setSecret]=useState('');
 const [url,setUrl]=useState('');
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [primary,setPrimary]=useState(false);
 const [revision,setRevision]=useState(0);
 const label=(a:string,e:string)=>ar?a:e;
 const refresh=useCallback(async()=>{
  setBusy(true);
  setError('');
  try{
   await loadCloudBooks();
  }catch{
   setError(ar?'تعذّر تحميل مكتبة Drive. راجع صلاحية الفولدر أو أعد الربط.':'Could not load Drive books. Check folder access or reconnect.');
  }finally{setBusy(false);}
 },[ar]);

 useEffect(()=>{
  let stopped=false;
  let timer:number|undefined;
  let checks=0;
  async function check(){
   try{
    const current=await requestJSON<Connection>(root+'/status');
    if(stopped)return;
    setConnection(current);
    if(current.sync){setSync(true);window.dispatchEvent(new Event('barq:drive-sync'));}
    if(current.pending&&checks++<150){timer=window.setTimeout(()=>void check(),2000);return;}
    if(current.failed){
     setError(ar?'ربط Google ما اكتملش. راجع إعدادات OAuth وحاول تاني.':'Google connection failed. Check your OAuth setup and retry.');
     setConfig(true);
    }else if(current.connected){
     setFolder(current.folder);setConfig(false);setUrl('');await refresh();
    }else{setUrl('');}
   }catch{if(!stopped)setError(ar?'ميزة الربط تتطلب نسخة برق المكتبية المحدّثة.':'Cloud linking requires the updated BARQ desktop app.');}
  }
  void check();
  return()=>{stopped=true;window.clearTimeout(timer);};
 },[ar,refresh,revision]);

 async function connect(event:FormEvent){
  event.preventDefault();setBusy(true);setError('');
  try{
   const result=await requestJSON<{opened:boolean;url:string}>(root+'/connect',{
    method:'POST',body:JSON.stringify({folder,client_id:client.trim(),client_secret:secret.trim(),sync}),
   });
   setSecret('');
   setUrl(result.opened?'':result.url);
   setRevision(n=>n+1);
  }catch{setError(label('راجع بيانات عميل OAuth ورابط فولدر Drive.','Check the desktop OAuth credentials and Drive folder link.'));}
  finally{setBusy(false);}
 }
 async function makePrimary(){
  setBusy(true);setError('');
  try{
   const result=await requestJSON<{covers_primary:boolean}>(root+'/sync',{
    method:'POST',body:JSON.stringify({device:driveSyncDevice(),records:{},claim_primary:true}),
   });
   if(!result.covers_primary)throw new Error('Primary cover sync unavailable');
   setPrimary(true);
  }catch{setError(label('تعذّر تعيين الجهاز الأساسي للأغلفة.','Could not set the primary cover device.'));}
  finally{setBusy(false);}
 }
 async function disconnect(){
  try{
   await requestJSON(root+'/connection',{method:'DELETE'});
   setConnection(undefined);setPrimary(false);setRevision(n=>n+1);
  }catch{setError(label('تعذّر فصل Google Drive.','Could not disconnect Google Drive.'));}
 }

 return <div className="bs-cloud-reading">
  <div className="bs-drive-header">
   <button className="bs-muted-btn" type="button" onClick={()=>setConfig(!config)} aria-expanded={config}><Cloud size={16}/>
    {connection?.connected?label('Google Drive متصل','Google Drive connected'):label('اربط Google Drive','Connect Google Drive')}</button>
   {connection?.connected&&<button className="bs-muted-btn" type="button" disabled={busy||connection.pending} onClick={()=>void refresh()}>
    <RefreshCw size={15}/>{label('حدّث الروايات','Refresh books')}</button>}
  </div>
  {connection?.sync&&<div className="bs-drive-header">
   <button className="bs-muted-btn" type="button" disabled={busy||connection.pending||primary} onClick={()=>void makePrimary()}>
    {primary?label('الجهاز الأساسي للأغلفة','Primary cover device'):label('خلّي الجهاز ده هو الأساسي للأغلفة','Make this the primary cover device')}
   </button>
  </div>}
  {config&&<form className="bs-cloud-config" onSubmit={connect}>
   <p>{label('استخدم بيانات عميل OAuth من نوع Desktop app في مشروع Google Cloud مفعّل فيه Drive API.',
    'Use Desktop app OAuth credentials from a Google Cloud project with Drive API enabled.')}
    {' '}<a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noreferrer">{label('إعدادات Google Cloud','Google Cloud credentials')}</a></p>
   <label>{label('رابط فولدر الروايات','Drive library folder URL')}<input required value={folder} dir="ltr" onChange={event=>setFolder(event.target.value)}/></label>
   <label>OAuth Client ID<input required value={client} dir="ltr" autoComplete="off" onChange={event=>setClient(event.target.value)}/></label>
   <label>OAuth Client Secret<input required type="password" value={secret} dir="ltr" autoComplete="off" onChange={event=>setSecret(event.target.value)}/></label>
   <label><input type="checkbox" checked={sync} onChange={event=>setSync(event.target.checked)}/>
    {label('زامن إعدادات برق والمحادثات وبيانات القراءة على حساب Google ده','Sync BARQ preferences, conversations and reading data with this Google account')}</label>
   <div className="bs-drive-header">
    <button className="bs-muted-btn" disabled={busy||connection?.pending} type="submit">{label('سجّل دخول بـ Google','Sign in with Google')}</button>
    {connection?.connected&&<button className="bs-muted-btn" type="button" onClick={()=>void disconnect()}>{label('افصل الحساب','Disconnect')}</button>}
   </div>
  </form>}
  {connection?.pending&&<p role="status">{label('كمّل موافقة Google في المتصفح وارجع لبرق.','Complete Google consent in your browser and return to BARQ.')}</p>}
  {url&&<a href={url} target="_blank" rel="noreferrer">{label('افتح موافقة Google','Open Google consent')}</a>}
  {error&&<p className="bs-alert" role="alert">{error}</p>}
 </div>;
}
