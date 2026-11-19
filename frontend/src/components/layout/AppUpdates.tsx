import {useCallback,useEffect,useRef,useState} from 'react';
import {Download,RefreshCw} from 'lucide-react';
import {Modal} from '../ui/Modal';

type Check = {status:string;current:string;version?:string;notes?:string;size?:number};
type UpdateApi = {check_update:()=>Promise<Check>;download_update:(version:string,stageOnly?:boolean)=>Promise<{status:string}>;cancel_staged_update?:()=>Promise<{status:string}>};

function desktopUpdater():UpdateApi|undefined{
 return (window as Window&{pywebview?:{api?:UpdateApi}}).pywebview?.api;
}

export function AppUpdates({ar}:{ar:boolean}){
 const [auto,setAuto]=useState(()=>localStorage.getItem('barq-auto-download-updates')!=='off');
 const [staged,setStaged]=useState<string>();
 const staging=useRef(false);
 const [native,setNative]=useState(false);
 const [open,setOpen]=useState(false);
 const [checking,setChecking]=useState(false);
 const [check,setCheck]=useState<Check>();
 const [install,setInstall]=useState<'working'|'installing'|'error'>();
 const close=useCallback(()=>setOpen(false),[]);
 const refresh=useCallback(async()=>{
  const api=desktopUpdater();
  if(!api?.check_update)return;
  setNative(true);
  setChecking(true);
  try{setCheck(await api.check_update());}
  catch{setCheck({status:'error',current:''});}
  finally{setChecking(false);}
 },[]);
 useEffect(()=>{
  const checkNow=()=>void refresh();
  window.addEventListener('pywebviewready',checkNow);
  checkNow();
  const timer=window.setInterval(checkNow,30*60*1000);
  return ()=>{window.removeEventListener('pywebviewready',checkNow);window.clearInterval(timer);};
 },[refresh]);
 useEffect(()=>{
  if(!auto||install||staging.current||check?.status!=='available'||!check.version||staged===check.version)return;
  const api=desktopUpdater();
  if(!api)return;
  const version=check.version;
  staging.current=true;
  void api.download_update(version,true).then(result=>{
   if(result.status==='staged')setStaged(version);
  }).catch(()=>{}).finally(()=>{staging.current=false;});
 },[auto,check,install,staged]);
 if(!native)return null;
 const available=check?.status==='available';
 const label=ar?(available?'تحديث متاح':'تحديثات التطبيق'):(available?'Update available':'App updates');
 const blocked=install==='working'||install==='installing';
 async function download(){
  const api=desktopUpdater();
  if(!api||!check?.version||blocked)return;
  setInstall('working');
  try{
   const result=await api.download_update(check.version);
   if(result.status==='installing'){setInstall('installing');return;}
   if(result.status==='changed'){await refresh();setInstall(undefined);return;}
   setInstall('error');
  }catch{setInstall('error');}
 }
 const summary=install==='installing'?(ar?'جاري إغلاق برق لتثبيت التحديث…':'Closing BARQ to install the update…'):
  install==='working'?(ar?'جاري تنزيل التحديث والتحقق منه…':'Downloading and verifying the update…'):
  install==='error'?(ar?'تعذّر تنزيل التحديث أو التحقق منه. جرّب تاني.':'Unable to download or verify the update. Try again.'):
  checking?(ar?'جاري التحقق من التحديثات…':'Checking for updates…'):
  staged&&staged===check?.version?(ar?'التحديث اتحمّل وهيتثبّت عند الخروج من برق.':'Downloaded. The update will install when you exit BARQ.'):
  available?(ar?'الإصدار الجديد جاهز للتنزيل.':'The new version is ready to download.'):
  check?.status==='current'?(ar?'أنت على أحدث إصدار.':'You are on the latest version.'):
  check?.status==='unconfigured'?(ar?'قناة التحديث لسه غير مفعّلة.':'The update channel has not been configured.'):
  check?.status==='unavailable'?(ar?'التحديث من داخل برق متاح للنسخ المثبّتة على ويندوز.':'In-app updates require an installed Windows copy.'):
  (ar?'تعذّر التحقق من التحديثات.':'Unable to check for updates.');
 return <>
  <button type="button" className="ops-update-button" data-available={available} onClick={()=>setOpen(true)} title={label} aria-label={label}><Download size={16}/></button>
  <Modal open={open} onClose={close} title={ar?'تحديثات BARQ ONE':'BARQ ONE updates'}>
   <div className="ops-update-content">
    {check?.current&&<p>{ar?'الإصدار الحالي':'Current version'} <bdi>{check.current}</bdi></p>}
    {available&&<div className="ops-update-release">
     <strong>{ar?'الإصدار الجديد':'New version'} <bdi>{check.version}</bdi></strong>
     {!!check.size&&<small><bdi>{(check.size/1024/1024).toFixed(0)} MB</bdi></small>}
     {check.notes&&<p dir="auto">{check.notes}</p>}
    </div>}
    <label><input type="checkbox" disabled={blocked} checked={auto} onChange={event=>{
      const enabled=event.target.checked;
      localStorage.setItem('barq-auto-download-updates',enabled?'on':'off');
      setAuto(enabled);
      if(!enabled){
       setStaged(undefined);
       void desktopUpdater()?.cancel_staged_update?.().then(()=>setStaged(undefined)).catch(()=>{});
      }
    }}/>{ar?'نزّل التحديثات تلقائيًا وثبّتها عند الخروج':'Download updates automatically and install on exit'}</label>
    <p role="status">{summary}</p>
    <div className="ops-update-actions">
     {available&&<button type="button" className="ops-update-install" disabled={blocked||checking} onClick={()=>void download()}><Download size={16}/>{ar?'حدّث الآن':'Update now'}</button>}
     <button type="button" disabled={blocked||checking} onClick={()=>{setInstall(undefined);void refresh();}}><RefreshCw size={15}/>{ar?'التحقق من التحديث':'Check for updates'}</button>
    </div>
   </div>
  </Modal>
 </>;
}
