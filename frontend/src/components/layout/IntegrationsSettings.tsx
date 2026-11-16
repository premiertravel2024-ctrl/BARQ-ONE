import {useCallback,useEffect,useState} from 'react';
import {Mail,MessageCircle,RefreshCw,ShieldCheck,Unplug} from 'lucide-react';
import {requestJSON} from '../../lib/backend';
import {useApp} from '../../store';
import {Button} from '../ui/Button';

type OutlookStatus={configured:boolean;connected:boolean;state:string;error:string;permissions:string[]};
type Status={outlook:OutlookStatus;whatsapp:{state:string;personal_chat_access:boolean;note:string}};
type Inbox={messages:{subject:string;sender:string;received:string;is_read:boolean}[];count:number;read_only:boolean};
type DeviceCode={verification_uri:string;user_code:string;expires_in:number};

export function IntegrationsSettings(){
 const ar=useApp(s=>s.language)==='ar',L=(a:string,b:string)=>ar?a:b;
 const [info,setInfo]=useState<Status|null>(null),[login,setLogin]=useState<DeviceCode|null>(null);
 const [inbox,setInbox]=useState<Inbox|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const refresh=useCallback(async()=>{try{setInfo(await requestJSON<Status>('/v1/integrations/status'))}catch(e){setError(String(e))}},[]);
 useEffect(()=>{void refresh();const timer=setInterval(()=>{if(!document.hidden)void refresh()},login?3000:20000);return()=>clearInterval(timer)},[refresh,login]);
 useEffect(()=>{if(info?.outlook.connected)setLogin(null)},[info?.outlook.connected]);
 async function action(fn:()=>Promise<unknown>){setBusy(true);setError('');try{await fn();await refresh()}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}}
 return <div className="space-y-4" aria-label={L('ربط التطبيقات','App integrations')}>
  <section className="barq-settings-card space-y-3">
   <div className="flex items-center justify-between gap-2"><h3 className="flex items-center gap-2 text-sm font-semibold"><Mail size={17}/>Microsoft Outlook</h3><span className="text-xs text-secondary">{info?.outlook.connected?L('متصل','Connected'):L('غير متصل','Disconnected')}</span></div>
   <p className="text-xs text-secondary">{L('تسجيل دخول Microsoft الرسمي بصلاحية قراءة البيانات الأساسية للرسائل فقط. لا توجد صلاحية إرسال أو حذف، ورمز الجلسة يبقى في الذاكرة مؤقتًا.','Official Microsoft device sign-in with Mail.ReadBasic only. No send/delete permission; temporary token kept in RAM.')}</p>
   {!info?.outlook.configured&&<p className="rounded-md border border-stroke p-2 text-xs text-secondary">{L('لتفعيل الربط: عيّن BARQ_MS_CLIENT_ID الخاص بتطبيق Microsoft Entra Public Client وثبّت requirements-outlook-optional.txt.','To enable: set BARQ_MS_CLIENT_ID for an Entra public client application and install requirements-outlook-optional.txt.')}</p>}
   <div className="flex flex-wrap gap-2">
    {!info?.outlook.connected?<Button size="sm" disabled={busy||!info?.outlook.configured} onClick={()=>void action(async()=>setLogin(await requestJSON<DeviceCode>('/v1/integrations/outlook/connect',{method:'POST'})))} icon={<ShieldCheck size={15}/>}>{L('ربط Outlook','Connect Outlook')}</Button>:
     <><Button size="sm" disabled={busy} icon={<RefreshCw size={15}/>} onClick={()=>void action(async()=>setInbox(await requestJSON<Inbox>('/v1/integrations/outlook/inbox?limit=10')))}>{L('أحدث 10 رسائل','Latest 10 messages')}</Button>
      <Button size="sm" variant="danger" disabled={busy} icon={<Unplug size={15}/>} onClick={()=>void action(async()=>{await requestJSON('/v1/integrations/outlook/disconnect',{method:'POST'});setInbox(null)})}>{L('قطع الاتصال','Disconnect')}</Button></>}
   </div>
   {login&&<div className="space-y-2 rounded-lg border border-stroke bg-elevated p-3 text-sm"><p>{L('افتح رابط تسجيل الدخول الرسمي وأدخل هذا الرمز:','Open Microsoft verification page and enter this code:')}</p>
     <code className="select-text text-lg font-bold tracking-widest" dir="ltr">{login.user_code}</code><p><a className="text-accent underline" href={login.verification_uri} target="_blank" rel="noopener noreferrer">{L('صفحة تسجيل الدخول إلى Microsoft','Microsoft sign-in')}</a></p>
     <p className="text-xs text-secondary">{L('برق مش هيطلب كلمة السر. الاتصال يظهر تلقائيًا بعد موافقتك.','BARQ never asks for your password. Connection status updates after approval.')}</p>
   </div>}
   {inbox&&<div className="max-h-64 space-y-2 overflow-y-auto" aria-label={L('الرسائل الأخيرة','Recent emails')}>{inbox.messages.map((item,i)=><div key={`${item.received}-${i}`} className="rounded-lg border border-stroke p-2 text-xs"><p className="font-semibold">{item.subject||L('(بدون موضوع)','(no subject)')}</p><p className="text-secondary" dir="ltr">{item.sender} · {item.received}</p></div>)}</div>}
  </section>
  <section className="barq-settings-card space-y-2"><h3 className="flex items-center gap-2 text-sm font-semibold"><MessageCircle size={17}/>WhatsApp</h3>
   <p className="text-xs text-secondary">{L('قراءة محادثات واتساب الشخصي عبر API غير مدعومة رسميًا. واجهة WhatsApp Business Cloud تتطلب حساب أعمال واعتمادات وموافقات منفصلة؛ مفيش وصول أو مراقبة مفعلة حاليًا.','Reading personal WhatsApp chats via a general API is not supported. WhatsApp Business Cloud needs a business account and separate permissions; no access or monitoring is active.')}</p>
  </section>
  {error&&<p role="alert" className="rounded-lg border border-danger p-2 text-xs text-danger">{error}</p>}
 </div>
}
