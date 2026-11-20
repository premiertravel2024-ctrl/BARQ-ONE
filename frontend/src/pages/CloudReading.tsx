import {useCallback,useEffect,useState,type FormEvent} from 'react';
import {Cloud,RefreshCw} from 'lucide-react';
import {APIError,requestJSON} from '../lib/backend';
import {Switch} from '../components/ui/Switch';
import {driveSyncDevice} from '../lib/driveSync';
import {OnlineLibrarySettings} from './OnlineLibraryLink';
import type {DriveBook} from './DriveBooks';

type Connection={connected:boolean;pending:boolean;failed:boolean;folder:string;sync?:boolean};
type Item={id:string;title:string;group:string;cover:string|null};
const root='/v1/reading/drive';

export async function loadCloudBooks(){
 type LocalBook={
  id:string;title:string;active:number;hidden:number;folder_name:string;cover_id:string|null;
  series_id:string|null;issue_number:number|null;position:number;manual_series:number;review_reason:string;
 };
 type LocalSeries={id:string;title:string;position:number};
 try{
  // One Drive read updates the media allowlist and local metadata in one transaction.
  // Indexing is automatic on opening the connected library; owner edits are preserved.
  await requestJSON('/v1/reading/library/refresh',{method:'POST'});
  const metadata=await requestJSON<{books:LocalBook[];series:LocalSeries[]}>('/v1/reading/library/items');
  const bySeries=new Map(metadata.series.map(group=>[group.id,group]));
  return metadata.books.filter(item=>item.active===1&&!item.hidden).map<DriveBook>(item=>{
   const series=item.series_id?bySeries.get(item.series_id):undefined;
   return {
    edition:{id:'google:'+item.id,title:item.title,format:'pdf',driveId:item.id},
    group:series?.title||item.folder_name,
    coverId:item.cover_id||undefined,seriesId:series?.id,
    issueNumber:item.issue_number||undefined,sortPosition:item.position||0,
    manualSeries:!!item.manual_series,reviewReason:item.review_reason,
   };
  }).sort((a,b)=>(a.sortPosition||0)-(b.sortPosition||0)||
   (a.issueNumber??Infinity)-(b.issueNumber??Infinity)||
   a.edition.title.localeCompare(b.edition.title,undefined,{numeric:true}));
 }catch{
  // A damaged/unavailable local index must not prevent an otherwise working reader.
  const result=await requestJSON<{books:Item[]}>(root+'/catalogue');
  return result.books.map<DriveBook>(item=>({
   edition:{id:'google:'+item.id,title:item.title,format:'pdf',driveId:item.id},
   group:item.group,coverId:item.cover||undefined,
  })).sort((a,b)=>a.edition.title.localeCompare(b.edition.title,undefined,{numeric:true}));
 }
}

export function useCloudBooks(){
 const [books,setBooks]=useState<DriveBook[]>();
 const [loading,setLoading]=useState(true);
 const [failed,setFailed]=useState(false);
 const [attempt,setAttempt]=useState(0);
 useEffect(()=>{
  // Keep the local index current without manual re-indexing after every Drive change.
  // Fifteen-minute cadence avoids hammering Drive's API or interrupting the reader.
  const timer=window.setInterval(()=>setAttempt(value=>value+1),15*60*1000);
  return()=>window.clearInterval(timer);
 },[]);
 useEffect(()=>{
  const changed=()=>setAttempt(value=>value+1);
  window.addEventListener('barq:library-changed',changed);
  return()=>window.removeEventListener('barq:library-changed',changed);
 },[]);
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
 const [primary,setPrimary]=useState<boolean>();
 const [primaryError,setPrimaryError]=useState(false);
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

 useEffect(()=>{
  if(!connection?.sync || connection.pending){setPrimary(undefined);setPrimaryError(false);return;}
  let active=true;
  const readPrimary=()=>{
   void requestJSON<{covers_primary:boolean}>(root+'/covers-primary?'+new URLSearchParams({device:driveSyncDevice()}))
    .then(result=>{if(active){setPrimary(result.covers_primary);setPrimaryError(false);}})
    .catch(()=>{if(active)setPrimaryError(true);});
  };
  readPrimary();
  return()=>{active=false;};
 },[connection?.sync,connection?.pending,connection?.folder]);

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
   setConnection(undefined);setPrimary(undefined);setRevision(n=>n+1);
  }catch{setError(label('تعذّر فصل Google Drive.','Could not disconnect Google Drive.'));}
 }

 return <div className="bs-cloud-reading">
  <div className="bs-drive-header">
   <button className="bs-muted-btn" type="button" onClick={()=>setConfig(!config)} aria-expanded={config}><Cloud size={16}/>
    {connection?.connected?label('Google Drive متصل','Google Drive connected'):label('اربط Google Drive','Connect Google Drive')}</button>
   {connection?.connected&&<button className="bs-muted-btn" type="button" disabled={busy||connection.pending} onClick={()=>void refresh()}>
    <RefreshCw size={15}/>{label('حدّث الروايات','Refresh books')}</button>}
  </div>
  {connection?.sync&&<div className="bs-primary-cover">
   <Switch checked={primary===true} disabled={busy||connection.pending||primary!==false||primaryError}
    onChange={()=>void makePrimary()} showLabel label={label('الجهاز الأساسي للأغلفة','Primary cover device')}/>
   <small role="status">{primaryError?label('تعذّر التحقق من الجهاز الأساسي','Could not check the primary device'):
    primary===undefined?label('جاري التحقق…','Checking…'):
    primary?label('الأغلفة بتتزامن من الجهاز ده','Covers sync from this device'):
    label('فعّل الخيار على الجهاز اللي عليه أغلفتك','Enable on the device with your covers')}</small>
  </div>}
  {config&&<form className="bs-cloud-config" onSubmit={connect}>
   <p>{label('استخدم بيانات عميل OAuth من نوع Desktop app في مشروع Google Cloud مفعّل فيه Drive API.',
    'Use Desktop app OAuth credentials from a Google Cloud project with Drive API enabled.')}
    {' '}<a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noreferrer">{label('إعدادات Google Cloud','Google Cloud credentials')}</a></p>
   <label>{label('رابط فولدر الروايات','Drive library folder URL')}<input required value={folder} dir="ltr" onChange={event=>setFolder(event.target.value)}/></label>
   <label>OAuth Client ID<input required value={client} dir="ltr" autoComplete="off" onChange={event=>setClient(event.target.value)}/></label>
   <label>OAuth Client Secret<input required type="password" value={secret} dir="ltr" autoComplete="off" onChange={event=>setSecret(event.target.value)}/></label>
   <Switch checked={sync} onChange={setSync} showLabel
    label={label('زامن إعدادات برق والمحادثات وبيانات القراءة على حساب Google ده','Sync BARQ preferences, conversations and reading data with this Google account')}/>
   <div className="bs-drive-header">
    <button className="bs-muted-btn" disabled={busy||connection?.pending} type="submit">{label('سجّل دخول بـ Google','Sign in with Google')}</button>
    {connection?.connected&&<button className="bs-muted-btn" type="button" onClick={()=>void disconnect()}>{label('افصل الحساب','Disconnect')}</button>}
   </div>
  </form>}
  {connection?.pending&&<p role="status">{label('كمّل موافقة Google في المتصفح وارجع لبرق.','Complete Google consent in your browser and return to BARQ.')}</p>}
  {url&&<a href={url} target="_blank" rel="noreferrer">{label('افتح موافقة Google','Open Google consent')}</a>}
  {error&&<p className="bs-alert" role="alert">{error}</p>}
  {connection?.connected&&<OnlineLibrarySettings ar={ar}/>}
 </div>;
}
