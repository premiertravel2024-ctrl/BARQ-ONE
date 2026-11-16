import {useEffect,useState} from 'react';
import {FolderOpen,RefreshCw,ShieldCheck} from 'lucide-react';
import {requestJSON} from '../../lib/backend';
import {Button} from '../ui/Button';import {useApp} from '../../store';
type Values={voice_enabled:boolean;stt:'gemini'|'local';enabled:boolean;apps:boolean;files:boolean;folders:boolean;sites:boolean;local_stt_model_path:string;extra_roots:string[]};
export function LauncherSettings(){
 const [settings,setSettings]=useState<Values|null>(null),[status,setStatus]=useState<{counts:Record<string,number>;refreshed:number|null}|null>(null);
 const [alias,setAlias]=useState(''),[appName,setAppName]=useState(''),[roots,setRoots]=useState(''),[working,setWorking]=useState(false),toast=useApp(s=>s.toast);
 useEffect(()=>{void requestJSON<Values>('/v1/launch/settings').then(v=>{setSettings(v);setRoots((v.extra_roots||[]).join('\n'))}).catch(()=>{});
  void requestJSON<{counts:Record<string,number>;refreshed:number|null}>('/v1/launch/status').then(setStatus).catch(()=>{})},[]);
 async function save(values:Partial<Values>){if(!settings)return;const updated={...settings,...values};setSettings(updated);try{
  await requestJSON('/v1/launch/settings',{method:'PUT',body:JSON.stringify({values:updated})});toast('success','اتحفظت إعدادات المشغّل');
 }catch(error){toast('error','تعذّر حفظ الإعدادات',error instanceof Error?error.message:'') }}
 return <section dir="rtl" className="space-y-4 text-sm">
  <h3 className="font-semibold">التشغيل بالأمر والصوت</h3>
  <p className="text-xs text-secondary">البحث عن أسماء البرامج والملفات بيتم محليًا؛ لو اخترت Gemini للتفريغ الصوتي فالتسجيل نفسه بيتبعت للخدمة بموافقتك عند الضغط على زر الأمر الصوتي.</p>
  {!settings?<span className="text-xs text-muted">بفتح الإعدادات المحلية…</span>:<>
   <label className="flex justify-between"><span>تفعيل تشغيل العناصر بالأوامر</span><input type="checkbox" checked={settings.enabled} onChange={e=>void save({enabled:e.target.checked})}/></label>
   <label className="flex justify-between"><span>تفعيل الأمر الصوتي بالضغط</span><input type="checkbox" checked={settings.voice_enabled} onChange={e=>void save({voice_enabled:e.target.checked})}/></label>
   <label className="flex justify-between gap-3"><span>طريقة فهم الصوت</span><select className="rounded-md border border-stroke bg-elevated p-2" value={settings.stt} onChange={e=>void save({stt:e.target.value as 'local'|'gemini'})}><option value="gemini">Gemini — حصة مجانية محدودة</option><option value="local">faster-whisper — محلي بعد التثبيت</option></select></label>
   {settings.stt==='local'&&<label className="block space-y-2"><span>مجلد موديل faster-whisper المثبّت (لا تنزيل تلقائي)</span><input dir="ltr" className="w-full rounded border border-stroke bg-elevated p-2" value={settings.local_stt_model_path} onChange={e=>setSettings({...settings,local_stt_model_path:e.target.value})} onBlur={()=>void save({local_stt_model_path:settings.local_stt_model_path})}/></label>}
   <div className="grid grid-cols-2 gap-3">{(['apps','files','folders','sites'] as const).map(k=><label key={k} className="flex items-center justify-between rounded border border-stroke p-2"><span>{{apps:'برامج',files:'ملفات',folders:'مجلدات',sites:'مواقع'}[k]}</span><input type="checkbox" checked={settings[k]} onChange={e=>void save({[k]:e.target.checked})}/></label>)}</div>
   <label className="block space-y-1"><span className="text-xs text-secondary">مجلدات بحث إضافية (مسار في كل سطر)</span><textarea dir="ltr" rows={3} className="w-full rounded border border-stroke bg-elevated p-2" value={roots} onChange={e=>setRoots(e.target.value)}/></label>
   <Button size="sm" variant="secondary" icon={<FolderOpen size={15}/>} onClick={()=>void save({extra_roots:roots.split('\n').map(s=>s.trim()).filter(Boolean)})}>حفظ مجلدات البحث</Button>
   <div className="grid grid-cols-2 gap-2"><input className="rounded border border-stroke bg-elevated p-2" placeholder="الاسم اللي بتنادي به" value={alias} onChange={e=>setAlias(e.target.value)}/>
      <input className="rounded border border-stroke bg-elevated p-2" placeholder="اسم البرنامج الأصلي" value={appName} onChange={e=>setAppName(e.target.value)}/></div>
   <Button size="sm" variant="outline" disabled={!alias.trim()||!appName.trim()} onClick={()=>void requestJSON('/v1/launch/aliases',{method:'POST',body:JSON.stringify({alias,app_name:appName})}).then(()=>{toast('success','اتحفظ الاسم الجديد');setAlias('')}).catch(e=>toast('error','تعذر حفظ الاسم',String(e)))}>حفظ الاسم البديل للبرنامج</Button>
   <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-stroke p-3"><span className="text-xs text-secondary">الفهرس: {Object.values(status?.counts||{}).reduce((a,b)=>a+b,0)} عنصر. {status?.refreshed?new Date(status.refreshed*1000).toLocaleString('ar-EG'): 'لسه ما اتبناش'}</span>
    <Button size="sm" disabled={working} variant="outline" icon={<RefreshCw size={15}/>} onClick={()=>{setWorking(true);void requestJSON('/v1/launch/reindex',{method:'POST'}).then(()=>requestJSON<{counts:Record<string,number>;refreshed:number|null}>('/v1/launch/status')).then(setStatus).then(()=>toast('success','تم تحديث الفهرس')).catch(e=>toast('error','فشل الفهرسة',String(e))).finally(()=>setWorking(false))}}>تحديث الفهرس</Button></div>
  </>}
  <div className="rounded-lg bg-elevated p-3 text-xs text-secondary"><ShieldCheck size={18} className="mb-2 text-accent"/>مفيش استماع خفي. الملفات لا تُقرأ محتوياتها أثناء الفهرسة. تشغيل البرامج الخطرة بيطلب موافقة من الشاشة، والإيقاف الطارئ شغال.</div>
 </section>
}
