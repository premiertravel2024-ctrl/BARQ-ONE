import {useCallback,useEffect,useRef,useState,type ReactNode} from 'react';
import {Settings2,Palette,BrainCircuit,Keyboard,Database,ShieldAlert,Download,Trash2,Check,X,Info,AudioLines,FolderCode,Activity,PlugZap,BookOpen} from 'lucide-react';
import {useApp} from '../../store';import {useT} from '../../i18n';import {Modal} from '../ui/Modal';import {Button} from '../ui/Button';import {Switch} from '../ui/Switch';import {ModelControls} from '../workspace/ModelControls';
import {deleteConversation} from '../../lib/backend';import {BrandLockup,BrandMark} from '../ui/BrandMark';
import {VoiceSettings} from './VoiceSettings';
import {LauncherSettings} from '../launcher/LauncherSettings';import {PerformanceSettings} from './PerformanceSettings';
import {NetworkMap} from '../network/NetworkMap';
import {ComputerControl} from '../workspace/ComputerControl';
import {IntegrationsSettings} from './IntegrationsSettings';
import {MemorySettings} from './MemorySettings';
type Tab='assistant'|'launcher'|'network'|'general'|'appearance'|'models'|'voice'|'workspace'|'computer'|'integrations'|'memory'|'performance'|'shortcuts'|'data'|'about';
export const shortcuts=[['Ctrl + Space','مشغّل برق للبرامج والملفات'],['Ctrl / ⌘ + K','Open command palette'],['Ctrl / ⌘ + Shift + O','New chat'],['Ctrl / ⌘ + /','Keyboard shortcuts'],['Enter','Send message'],['Shift + Enter','New line'],['Esc','Close menu or dialog']];
export function SettingsModal({open,onClose,initialTab='general',onWorkspace,embedded=false}:{open:boolean;onClose:()=>void;initialTab?:Tab;onWorkspace:()=>void;embedded?:boolean}){
 const [tab,setTab]=useState<Tab>(initialTab),[confirmClear,setConfirmClear]=useState(false),[sectionQuery,setSectionQuery]=useState('');
 const mainRef=useRef<HTMLElement>(null);const t=useT();const language=useApp(s=>s.language),setLanguage=useApp(s=>s.setLanguage),theme=useApp(s=>s.theme),setTheme=useApp(s=>s.setTheme),chats=useApp(s=>s.chats),clearAll=useApp(s=>s.clearAll),toast=useApp(s=>s.toast),sidebarCollapsed=useApp(s=>s.sidebarCollapsed),setCollapsed=useApp(s=>s.setSidebarCollapsed);
 useEffect(()=>{if(open){setTab(initialTab);setSectionQuery('')}},[open,initialTab]);
 useEffect(()=>{if(open&&mainRef.current)mainRef.current.scrollTop=0},[tab,open]);
 const tabs:[Tab,ReactNode, string][]=[['general',<Settings2 size={16}/>,t('general')],['appearance',<Palette size={16}/>,t('appearance')],['models',<BrainCircuit size={16}/>,t('models')],['voice',<AudioLines size={16}/>,language==='ar'?'المكالمات الصوتية':'Voice calls'],['assistant',<AudioLines size={16}/>,language==='ar'?'برق الصوتي':'BARQ Voice Assistant'],['workspace',<FolderCode size={16}/>,language==='ar'?'البرمجة':'Programming'],['computer',<ShieldAlert size={16}/>,language==='ar'?'التحكم في الكمبيوتر':'Computer Control'],['integrations',<PlugZap size={16}/>,language==='ar'?'التكاملات':'Integrations'],['memory',<BookOpen size={16}/>,language==='ar'?'الذاكرة':'Memory'],['launcher',<FolderCode size={16}/>,language==='ar'?'التشغيل بالأمر':'Launcher'],['performance',<Activity size={16}/>,language==='ar'?'الأداء':'Performance'],['network',<BrainCircuit size={16}/>,language==='ar'?'شبكة الأوامر':'Model network'],['shortcuts',<Keyboard size={16}/>,t('shortcuts')],['data',<Database size={16}/>,t('data')],['about',<Info size={16}/>,language==='ar'?'حول BARQ':'About BARQ']];

 const groupedTabs:{labelAr:string;labelEn:string;ids:Tab[]}[]=[
  {labelAr:'التخصيص',labelEn:'Personalize',ids:['general','appearance','models','voice']},
  {labelAr:'المهام والتحكم',labelEn:'Capabilities',ids:['assistant','workspace','computer','integrations','memory','launcher','network']},
  {labelAr:'النظام',labelEn:'System',ids:['performance','shortcuts','data','about']},
 ];
 const tabDescriptions:Record<Tab,[string,string]>={
  general:['اللغة وطريقة عرض برق','Language and general preferences'],
  appearance:['الألوان والهوية البصرية','Colors and interface appearance'],
  models:['إدارة النماذج المحلية والسحابية','Manage local and cloud models'],
  voice:['صوت Google للمحادثات والمكالمات المباشرة','Google voice for direct calls'],
  assistant:['الاستماع في الخلفية، أدوات البحث والطقس والكمبيوتر','Background listening, web, weather and Windows tools'],
  workspace:['بناء البرامج من المحادثة','Build applications from chat'],
  computer:['صلاحيات الجهاز والتحكم في ويندوز','Desktop control and permission settings'],
  integrations:['ربط Outlook والتطبيقات بصلاحيات واضحة','Connect Outlook and apps with explicit permissions'],
  memory:['المعلومات المحفوظة بإذنك محليًا','Your user-approved local notes'],
  launcher:['تشغيل التطبيقات والملفات بالأوامر','Launch apps and files by command'],
  network:['توزيع المهام بين نماذج برق','Routing tasks across models'],
  performance:['استهلاك الموارد وسرعة الاستجابة','Resource usage and response performance'],
  shortcuts:['اختصارات لوحة المفاتيح','Keyboard shortcuts'],
  data:['المحادثات والحفظ والنسخ الاحتياطي','Chats, storage and backups'],
  about:['معلومات عن برق والإصدار','Version and product details'],
 };
 const currentTab=tabs.find(([id])=>id===tab);
 const shownGroups=groupedTabs.map(group=>({...group,ids:group.ids.filter(id=>{const item=tabs.find(([key])=>key===id);const search=sectionQuery.trim().toLocaleLowerCase();return !search||[item?.[2]||'',...tabDescriptions[id],id].some(value=>value.toLocaleLowerCase().includes(search))})})).filter(group=>group.ids.length>0);
 const exportData=useCallback(()=>{const data=JSON.stringify({format:'ai-router-chats-v1',exportedAt:new Date().toISOString(),chats},null,2);const href=URL.createObjectURL(new Blob([data],{type:'application/json'}));const link=document.createElement('a');link.href=href;link.download=`ai-router-chats-${new Date().toISOString().slice(0,10)}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(href),1000);toast('success','Chats exported')},[chats,toast]);
 const layout=<div className="barq-settings-layout" dir={language==='ar'?'rtl':'ltr'}>
   <label className="barq-settings-mobile text-sm">{language==='ar'?'اختر القسم':'Choose a section'}
    <select className="ui-input mt-2" value={tab} onChange={e=>setTab(e.target.value as Tab)} aria-label={language==='ar'?'قسم الإعدادات':'Settings section'}>{tabs.map(([id,,label])=><option key={id} value={id}>{label}</option>)}</select>
   </label>
   <nav className="barq-settings-nav" aria-label={language==='ar'?'أقسام الإعدادات':'Settings sections'}>
    <label className="barq-settings-search"><span className="sr-only">{language==='ar'?'بحث في الإعدادات':'Search settings'}</span><input type="search" value={sectionQuery} onChange={event=>setSectionQuery(event.target.value)} placeholder={language==='ar'?'ابحث عن إعداد...':'Find a setting...'} className="ui-input"/></label>
    {!shownGroups.length&&<p className="px-3 py-4 text-xs text-secondary">{language==='ar'?'مفيش إعدادات مطابقة':'No matching settings'}</p>}
    {shownGroups.map(group=><div key={group.labelEn} className="barq-settings-nav-group">
      <p className="barq-settings-nav-label">{language==='ar'?group.labelAr:group.labelEn}</p>
      {group.ids.map(id=>{const item=tabs.find(([key])=>key===id);if(!item)return null;const [,icon,label]=item;
       return <button key={id} type="button" onClick={()=>setTab(id)} aria-current={tab===id?'page':undefined} className={`barq-settings-tab focus-ring ${tab===id?'is-active':''}`}>{icon}<span>{label}</span></button>})}
     </div>)}
   </nav>
   <section ref={mainRef} className="barq-settings-main" aria-label={language==='ar'?'إعدادات برق':'BARQ preferences'}>
    <header className="barq-settings-heading"><span className="barq-settings-heading-icon" aria-hidden="true">{currentTab?.[1]}</span><div><h3>{currentTab?.[2]}</h3><p>{tabDescriptions[tab][language==='ar'?0:1]}</p></div></header>
    <div className="barq-settings-content">
   {tab==='general'&&<div className="space-y-5"><section className="barq-settings-card"><h3 className="mb-2 text-sm font-semibold">{t('language')}</h3><div className="flex gap-2"><Button variant={language==='en'?'primary':'outline'} size="sm" onClick={()=>setLanguage('en')}>English</Button><Button variant={language==='ar'?'primary':'outline'} size="sm" onClick={()=>setLanguage('ar')}>العربية</Button></div></section><div className="barq-settings-card flex items-center justify-between gap-4"><div><h3 className="text-sm font-semibold">{language==='ar'?'تصغير شريط المحادثات':'Compact navigation'}</h3><p className="mt-1 text-xs text-muted">{language==='ar'?'اختصر الشريط الجانبي على الكمبيوتر.':'Use a smaller sidebar on desktop.'}</p></div><Switch checked={sidebarCollapsed} onChange={setCollapsed} label={language==='ar'?'تصغير الشريط':'Collapse sidebar'}/></div><div className="barq-settings-note text-xs text-secondary"><Info size={16} className="mb-2 text-accent"/>{language==='ar'?'الواجهة متصلة بمحرك Python المحلي داخل تطبيق سطح المكتب. إدارة الأدوات والمشاريع من مساحة البرمجة.':'Connected to the local Python API. Use Coding Workspace for projects and tools.'}</div></div>}
   {tab==='appearance'&&<div className="barq-settings-card space-y-5"><h3 className="text-sm font-semibold">{language==='ar'?'المظهر':'Theme'}</h3><div className="grid grid-cols-2 gap-3">{(['dark','light'] as const).map(option=><button key={option} onClick={()=>setTheme(option)} className={`focus-ring relative overflow-hidden rounded-lg border p-2 text-start ${theme===option?'border-accent':'border-stroke'}`}><div className={`mb-3 h-24 rounded-sm p-3 ${option==='dark'?'bg-[#0F1115]':'bg-[#F7F8FA]'}`}><div className={`mb-2 h-3 w-3/4 rounded ${option==='dark'?'bg-[#191D24]':'bg-white'}`}/><div className="h-4 w-1/2 rounded bg-accent/35"/></div><span className="flex items-center justify-between text-sm capitalize">{language==='ar'?(option==='dark'?'داكن':'فاتح'):option}{theme===option&&<Check size={15} className="text-accent"/>}</span></button>)}</div></div>}
   {tab==='models'&&<ModelControls/>}
   {tab==='voice'&&<VoiceSettings mode="conversation"/>}
   {tab==='assistant'&&<VoiceSettings mode="assistant" onNavigate={setTab}/>}
   {tab==='workspace'&&<div className="barq-settings-card space-y-3"><h3 className="text-sm font-semibold">{language==='ar'?'بناء البرامج من المحادثة':'Build applications from chat'}</h3><p className="text-sm text-secondary">{language==='ar'?'قول لبرق ابنيلي برنامج وحدد المطلوب. الطلب والتقدم والموافقات وملفات التسليم بتظهر في المحادثة. بناء EXE يحتاج Windows وأدوات البناء.':'Ask BARQ to build an application. Progress, approvals and deliverables appear in chat. EXE builds require Windows and build tools.'}</p><Button onClick={onWorkspace} variant="secondary">{language==='ar'?'ارجع للمحادثة':'Return to chat'}</Button></div>}
   {tab==='computer'&&<ComputerControl settingsOnly/>}
   {tab==='integrations'&&<IntegrationsSettings/>}
   {tab==='memory'&&<MemorySettings/>}
   {tab==='launcher'&&<LauncherSettings/>}
   {tab==='performance'&&<PerformanceSettings active={open&&tab==='performance'}/>}
   {tab==='network'&&<NetworkMap active={open&&tab==='network'}/>}
   {tab==='shortcuts'&&<div className="barq-settings-card"><p className="mb-4 text-sm text-secondary">{language==='ar'?'اختصارات لوحة المفاتيح للعمل بسرعة.':'Work faster with keyboard shortcuts.'}</p><div className="space-y-3">{shortcuts.map(([key,description])=><div key={key} className="flex items-center justify-between gap-3 border-b border-stroke pb-2 text-sm"><span>{description}</span><kbd className="whitespace-nowrap rounded-sm border border-stroke bg-elevated px-2 py-1 font-mono text-xs text-secondary">{key}</kbd></div>)}</div></div>}
   {tab==='about'&&<section className="space-y-5" aria-label="About BARQ"><div className="overflow-hidden rounded-2xl border border-stroke bg-elevated"><div className="flex items-center justify-between gap-4 p-5"><div className="min-w-0"><div className="mb-3 inline-flex items-center gap-3 rounded-xl border border-stroke/80 bg-base/40 px-3 py-2"><BrandLockup compact/><span className="rounded-full border border-stroke px-2 py-0.5 text-[11px] text-secondary">v2.41.4</span></div><h3 className="text-xl font-bold">BARQ ONE</h3><p className="mt-1 text-sm text-secondary">{language==='ar'?'مساعد ذكاء اصطناعي متعدد النماذج — مصري الهوية، سريع، ومرتاح في الاستخدام.':'A comfortable multi-model AI assistant with a clear Egyptian product identity.'}</p></div><div className="shrink-0 rounded-2xl border border-stroke/80 bg-base/40 p-3"><BrandMark size={78}/></div></div><div className="grid gap-3 border-t border-stroke p-5 sm:grid-cols-3"><div className="rounded-xl border border-stroke/80 bg-base/30 p-3"><p className="text-[11px] text-muted">{language==='ar'?'المطور':'Developer'}</p><p className="mt-1 text-sm font-semibold">أشرف محمد</p></div><div className="rounded-xl border border-stroke/80 bg-base/30 p-3"><p className="text-[11px] text-muted">{language==='ar'?'الهوية':'Identity'}</p><p className="mt-1 text-sm font-semibold">{language==='ar'?'برق — مساعد مصري متعدد النماذج':'BARQ — multi-model AI assistant'}</p></div><div className="rounded-xl border border-stroke/80 bg-base/30 p-3"><p className="text-[11px] text-muted">{language==='ar'?'إلهام الاسم':'Name inspiration'}</p><p className="mt-1 text-sm font-semibold">{language==='ar'?'مستوحى من الدبلجة المصرية لاسم Lightning McQueen':'Inspired by the Egyptian dub of Lightning McQueen'}</p></div></div></div><p className="text-sm text-secondary">{language==='ar'?'الإصدار 2.41.4 — النماذج السحابية والمحلية، تنفيذ الأوامر، والمحادثة الصوتية.':'Version 2.41.4 — cloud and local models, command execution and voice chat.'}</p><p className="text-xs text-muted">{language==='ar'?'بياناتك وإعداداتك تظل في نفس المسار المحلي عند التحديث.':'Your local data and settings remain in the same directory during upgrades.'}</p><div className="rounded-xl border border-stroke/80 bg-base/30 p-4" aria-label={language==='ar'?'حقوق مصادر بيانات الأفلام':'Movie catalogue credits'}>
  <div className="flex flex-wrap items-center gap-3">
    <a href="https://www.themoviedb.org" target="_blank" rel="noopener noreferrer" title="The Movie Database" className="inline-flex items-center rounded-lg bg-[#0d253f] px-3 py-2">
      <img src="https://www.themoviedb.org/assets/v4/logos/v2/blue_short-8e7b30f73a4020692ccca9c88bafe5dcb6f8a62a4c6bc55cd9ba82bb2cd95f6c.svg" alt="TMDB" width="72" height="28" style={{objectFit:'contain'}} loading="lazy"/>
    </a>
    <div><strong className="text-xs">{language==='ar'?'حقوق مكتبة الأفلام':'Movie catalogue credits'}</strong>
      <p className="mt-1 text-xs text-secondary" dir="ltr">This product uses the TMDB API but is not endorsed or certified by TMDB.</p>
    </div>
  </div>
</div><p className="text-xs text-secondary">Lively Wallpaper by rocksdanister — <a href="https://github.com/lively-community/lively" target="_blank" rel="noreferrer" className="underline">GPL-3.0</a> · {language==='ar'?'النسخة القديمة لويندوز 8.1 مرخصة بـ Ms-PL؛ تعمل Lively كبرنامج منفصل عن برق.':'Windows 8.1 legacy release: MS-PL; Lively runs as a separate application.'}</p></section>}
   {tab==='data'&&<div className="barq-settings-card space-y-5"><div><h3 className="text-sm font-semibold">{language==='ar'?'المحادثات المحلية':'Local conversations'}</h3><p className="mt-1 text-sm text-secondary">{chats.length} {language==='ar'?'محادثة محفوظة على جهازك.':'conversations saved on this device.'}</p></div><Button variant="secondary" icon={<Download size={16}/>} onClick={exportData}>{t('export')}</Button><div className="border-t border-stroke pt-4"><h3 className="mb-2 text-sm font-semibold text-danger">{language==='ar'?'إجراءات خطيرة':'Danger zone'}</h3>{confirmClear?<div className="flex flex-wrap items-center gap-2"><p className="w-full text-sm text-secondary">{language==='ar'?'حذف جميع المحادثات من الجهاز؟':'Remove all conversations from this device?'}</p><Button variant="danger" icon={<Trash2 size={16}/>} onClick={()=>{void Promise.all(chats.map(c=>deleteConversation(c.id))).then(()=>{clearAll();setConfirmClear(false);toast('success','All chats cleared')}).catch(error=>toast('error','Could not delete all chats',error instanceof Error?error.message:'Local API unavailable'))}}>{t('confirm')}</Button><Button variant="ghost" icon={<X size={16}/>} onClick={()=>setConfirmClear(false)}>{t('cancel')}</Button></div>:<Button variant="danger" icon={<Trash2 size={16}/>} onClick={()=>setConfirmClear(true)}>{t('clear')}</Button>}</div></div>}
    </div></section></div>;
 if(embedded)return <section className="ops-settings"><h1>{t('settingsTitle')}</h1>{layout}</section>;
 return <Modal open={open} onClose={onClose} title={t('settingsTitle')} wide dialogClassName="barq-settings-dialog" bodyClassName="barq-settings-body">{layout}</Modal>;
}

