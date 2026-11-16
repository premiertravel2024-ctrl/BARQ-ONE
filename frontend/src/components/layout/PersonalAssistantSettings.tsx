import {useEffect,useState} from 'react';
import {requestJSON} from '../../lib/backend';
import {Button} from '../ui/Button';
type Settings={owner_name:string;routines:Record<string,string[]>;favorites:Record<string,string>;notify_voice:boolean;watches:Array<{id:string;message:string}>;owner_model_ready:boolean;owner_voice_enrolled:boolean;hotkey:{ready:boolean;error?:string}};
export function PersonalAssistantSettings(){
 const [value,setValue]=useState<Settings|null>(null),[work,setWork]=useState(''),[game,setGame]=useState(''),[favorites,setFavorites]=useState(''),[status,setStatus]=useState(''),[busy,setBusy]=useState(false);
 const load=async()=>{const next=await requestJSON<Settings>('/v1/personal/settings');setValue(next);setWork((next.routines['جهزني للشغل']||[]).join('\n'));setGame((next.routines['وضع اللعب']||[]).join('\n'));setFavorites(Object.entries(next.favorites).map(([k,v])=>k+' = '+v).join('\n'));};
 useEffect(()=>{void load().catch(()=>setStatus('تعذر قراءة إعدادات مساعدك الشخصي.'))},[]);
 async function save(){if(!value)return;setBusy(true);setStatus('');try{
  const items:Record<string,string>={};for(const line of favorites.split('\n').filter(x=>x.trim())){const i=line.indexOf('=');if(i<1)throw Error('المفضلة: اكتب اسم = المسار أو اسم التطبيق');items[line.slice(0,i).trim()]=line.slice(i+1).trim();}
  await requestJSON('/v1/personal/settings',{method:'PUT',body:JSON.stringify({owner_name:value.owner_name,routines:{...value.routines,'جهزني للشغل':work.split('\n').map(x=>x.trim()).filter(Boolean),'وضع اللعب':game.split('\n').map(x=>x.trim()).filter(Boolean)},favorites:items,notify_voice:value.notify_voice})});setStatus('اتحفظت تفضيلاتك وروتيناتك على الجهاز.');
 }catch(e){setStatus(e instanceof Error?e.message:'فشل الحفظ')}finally{setBusy(false)}}
 return <section className="barq-settings-card space-y-3 text-sm" aria-label="مساعدك الشخصي"><h4 className="barq-settings-subtitle">مساعدك الشخصي — الروتينات والمفضلة</h4>
 <p className="text-xs text-secondary">Ctrl + Alt + Pause إيقاف فوري للاستماع والصوت والتنفيذ. الاستئناف من أيقونة برق بجانب الساعة.</p>
 {value&&<><Button size="sm" variant="danger" onClick={()=>void requestJSON('/v1/personal/command',{method:'POST',body:JSON.stringify({text:'وقف كل حاجة'})}).then(()=>setStatus('اتوقف الصوت والتنفيذ. استأنف من أيقونة برق.'))}>إيقاف فوري</Button><p className="text-xs text-secondary">{value.hotkey.ready?'اختصار الإيقاف العام مسجل وجاهز.':value.hotkey.error||'الاختصار يعمل داخل تطبيق Windows المثبت.'}</p><label className="block text-xs">الاسم اللي برق يعرفك بيه<input className="ui-input mt-1" maxLength={60} value={value.owner_name} onChange={e=>setValue({...value,owner_name:e.target.value})}/></label>
 <p className="text-xs">تمييز المتحدث: {value.owner_voice_enrolled?'بصمتك مسجلة محليًا':value.owner_model_ready?'النموذج جاهز؛ سجّل نداءك من قسم الخلفية':'نموذج الصوت يحتاج إصلاح النسخة'}. التسجيل 3 مرات من ميكروفون جهازك.</p>
 <label className="block text-xs">«جهزني للشغل» — فتح أو صوت أو سطوع في كل سطر<textarea className="ui-input mt-1 min-h-24" value={work} onChange={e=>setWork(e.target.value)} placeholder={'افتح Outlook\nافتح Excel\nافتح فولدر تقارير'}/></label>
 <label className="block text-xs">«وضع اللعب» — فتح أو صوت أو سطوع في كل سطر<textarea className="ui-input mt-1 min-h-20" value={game} onChange={e=>setGame(e.target.value)} placeholder={'افتح Steam\nظبط الصوت على 30 في المية'}/></label>
 <label className="block text-xs">المفضلة — اسم = مسار أو تطبيق<textarea className="ui-input mt-1 min-h-20" value={favorites} onChange={e=>setFavorites(e.target.value)} placeholder={'تقاريري = D:\\Reports'}/></label>
 <label className="flex gap-2 text-xs"><input type="checkbox" checked={value.notify_voice} onChange={e=>setValue({...value,notify_voice:e.target.checked})}/>نطق تنبيهات اكتمال المهام بصوت Windows العربي إن كان متاحًا</label>
 <div className="flex gap-2"><Button size="sm" disabled={busy} onClick={()=>void save()}>حفظ تفضيلاتي</Button><Button size="sm" variant="secondary" onClick={()=>void load()}>تحديث</Button></div>
 {value.watches.map(w=><div key={w.id} className="flex items-center justify-between gap-3 text-xs"><span>{w.message}</span><Button size="sm" variant="secondary" onClick={()=>void requestJSON('/v1/personal/watches/'+w.id,{method:'DELETE'}).then(load)}>إلغاء التذكير</Button></div>)}
 <p className="text-xs text-secondary">جرّب: «افتح المفضل تقاريري»، «بلغني لما التنزيل يخلص»، «فكرني بالتقرير لما أفتح Outlook»، «رجّع آخر تغيير»، «ترجم المحدد».</p>
 </>}{status&&<p role="status" className="text-xs text-secondary">{status}</p>}</section>;
}
