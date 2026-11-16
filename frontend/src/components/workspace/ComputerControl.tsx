import {useCallback,useEffect,useState} from 'react';
import {AlertTriangle,Check,Eye,Monitor,PauseOctagon,Play,RotateCcw,ShieldCheck,ShieldAlert} from 'lucide-react';
import {requestJSON} from '../../lib/backend';
import {useApp} from '../../store';
import {Button} from '../ui/Button';

type Mode='observe'|'ask-always'|'smart'|'trusted';
type Policy={enabled:boolean;direct_commands:boolean;mode:Mode;allowed_folders:string[];local_only_vision:boolean;max_steps:number;max_seconds:number;max_failures:number;max_files:number;actions_per_second:number;approval_seconds:number;blocked_categories:string[];sandbox_available:boolean;vision_note:string};
type Approval={id:string;tool:string;args:string;reason:string;expires_at:number;risk:string};
type ControlTask={id:string;goal:string;status:string;phase?:string;intent?:{label:string;confidence:string;source:string};goal_proof?:{status:string;reason:string};progress:number;steps:string[];message:string;pending:Approval|null;history:Array<{tool:string;status:string;reason?:string;verification?:string;verification_reason?:string;result?:string}>};
type Status={supported:boolean;task?:ControlTask|null;settings?:Policy;reason?:string;health?:{uptime_seconds:number;memory_mb:number|null;cpu_percent:number|null;diagnostics:string};recovered_count?:number};
type Checkpoint={id:string;goal:string;status:string;progress:number;phase:string;message:string};
type Checkpoints={tasks:Checkpoint[];interrupted_on_startup:number;note:string};
type SearchInstallStatus={status:string;step:string;message:string};
type IndexStatus={settings:{enabled:boolean;all_local_drives:boolean;content_enabled:boolean};status:string;entries:number;folders:number;everything_available:boolean;error:string};
type ContentStatus={status:string;indexed:number;skipped:number;error:string};
type InstallPaths={application:string;user_data:string;wake_model:string;note:string};
type BridgeStatus={name:string;version_pinned:string;installed:boolean;transport:string;needs_internet_for_install:boolean;security:string};
export function ComputerControl({settingsOnly=false,initialGoal=''}:{settingsOnly?:boolean;initialGoal?:string}){
 const language=useApp(s=>s.language),L=(ar:string,en:string)=>language==='ar'?ar:en;
 const [info,setInfo]=useState<Status|null>(null),[goal,setGoal]=useState(initialGoal),[model,setModel]=useState('auto');
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[folders,setFolders]=useState('');
 const [approvalEdit,setApprovalEdit]=useState(''),[image,setImage]=useState('');
 type Grant={id:string;root:string;label:string;scopes:string[];created_at:number};
 const [grants,setGrants]=useState<Grant[]>([]),[projectFolder,setProjectFolder]=useState('');
 const [grantScopes,setGrantScopes]=useState<string[]>(['read','write','create','run_tests','build','install_dependencies','run_dev_server','git_local']);
 const [doctorTools,setDoctorTools]=useState<Array<{tool:string;status:string;reason?:string}>>([]);
 const grantOptions=['read','write','create','run_tests','build','install_dependencies','run_dev_server','git_local'];
 const refreshGrants=useCallback(async()=>{try{const data=await requestJSON<{grants:Grant[]}>('/v1/computer/execution/grants');setGrants(data.grants)}catch{}},[]);
 useEffect(()=>{if(settingsOnly)void refreshGrants()},[settingsOnly,refreshGrants]);
 async function chooseProjectFolder(){setBusy(true);setError('');try{const data=await requestJSON<{path:string|null;cancelled:boolean}>('/v1/computer/execution/pick-folder',{method:'POST'});if(data.path)setProjectFolder(data.path)}catch(e){setError(String(e))}finally{setBusy(false)}}
 async function addProjectGrant(){if(!projectFolder.trim())return;setBusy(true);setError('');try{await requestJSON('/v1/computer/execution/grants',{method:'POST',body:JSON.stringify({root:projectFolder,scopes:grantScopes})});await refreshGrants()}catch(e){setError(String(e))}finally{setBusy(false)}}
 async function revokeProjectGrant(id:string){setBusy(true);setError('');try{await requestJSON('/v1/computer/execution/grants/'+id,{method:'DELETE'});await refreshGrants()}catch(e){setError(String(e))}finally{setBusy(false)}}
 async function runDoctor(){setBusy(true);try{const data=await requestJSON<{tools:Array<{tool:string;status:string;reason?:string}>}>('/v1/computer/execution/doctor');setDoctorTools(data.tools)}catch(e){setError(String(e))}finally{setBusy(false)}}

 const [installPaths,setInstallPaths]=useState<InstallPaths|null>(null);
 const [checkpoints,setCheckpoints]=useState<Checkpoints|null>(null);
 const [bridgeStatus,setBridgeStatus]=useState<BridgeStatus|null>(null);
 const [fileIndex,setFileIndex]=useState<IndexStatus|null>(null);
 const [contentStatus,setContentStatus]=useState<ContentStatus|null>(null);
 const [contentQuery,setContentQuery]=useState('');
 const [contentResults,setContentResults]=useState<Array<{name:string;snippet:string}>>([]);
 const [searchInstall,setSearchInstall]=useState<SearchInstallStatus|null>(null);
 const refreshFileIndex=useCallback(async()=>{try{const [index,install,content]=await Promise.all([requestJSON<IndexStatus>('/v1/device/index/status'),requestJSON<SearchInstallStatus>('/v1/device/index/install-status'),requestJSON<ContentStatus>('/v1/device/index/content-status')]);setFileIndex(index);setSearchInstall(install);setContentStatus(content)}catch{}},[]);
 useEffect(()=>{if(!settingsOnly)return;void refreshFileIndex();const timer=setInterval(()=>void refreshFileIndex(),4500);return()=>clearInterval(timer)},[settingsOnly,refreshFileIndex]);
 async function setFileIndexMode(enabled:boolean,allLocalDrives:boolean,contentEnabled:boolean=fileIndex?.settings.content_enabled??false){setBusy(true);setError('');try{await requestJSON('/v1/device/index/settings',{method:'PUT',body:JSON.stringify({enabled,all_local_drives:allLocalDrives,content_enabled:contentEnabled})});await refreshFileIndex();if(enabled)await requestJSON('/v1/device/index/refresh',{method:'POST'});if(!contentEnabled)setContentResults([])}catch(e){setError(String(e))}finally{setBusy(false)}}
 useEffect(()=>{if(!settingsOnly)return;let active=true;void requestJSON<InstallPaths>('/v1/system/installation').then(x=>{if(active)setInstallPaths(x)}).catch(()=>{});return()=>{active=false}},[settingsOnly]);
 useEffect(()=>{let active=true;void requestJSON<BridgeStatus>('/v1/computer/windows-mcp').then(s=>{if(active)setBridgeStatus(s)}).catch(()=>{});return()=>{active=false}},[]);
 const refreshCheckpoints=useCallback(async()=>{try{setCheckpoints(await requestJSON<Checkpoints>('/v1/computer/checkpoints?limit=8'))}catch{}},[]);
 useEffect(()=>{if(!settingsOnly)void refreshCheckpoints()},[settingsOnly,refreshCheckpoints]);
 const poll=useCallback(async()=>{try{const data=await requestJSON<Status>('/v1/computer/status');setInfo(data);if(data.settings&&!folders.trim())setFolders(data.settings.allowed_folders.join('\n'))}catch(e){setError(String(e))}},[folders]);
 // Idle settings need only an occasional refresh; active tasks still update quickly.
 const [taskActive,setTaskActive]=useState(false);
 useEffect(()=>{setTaskActive(!!info?.task&&['running','planning','approval'].includes(info.task.status))},[info?.task?.status]);
 useEffect(()=>{void poll();const timer=setInterval(()=>{if(!document.hidden)void poll()},taskActive?1100:8000);return()=>clearInterval(timer)},[poll,taskActive]);
 useEffect(()=>{if(initialGoal.trim())setGoal(initialGoal)},[initialGoal]);
 const task=info?.task;const setting=info?.settings;
 useEffect(()=>{if(task?.pending)setApprovalEdit(task.pending.args)},[task?.pending?.id]);
 async function send<T>(url:string,body?:unknown):Promise<T|undefined>{setBusy(true);setError('');try{const result=await requestJSON<T>(url,{method:'POST',body:body?JSON.stringify(body):undefined});await poll();await refreshCheckpoints();return result}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}}
 async function update(patch:Partial<Policy>){if(!setting)return;setBusy(true);try{const payload={enabled:setting.enabled,direct_commands:setting.direct_commands??true,mode:setting.mode,local_only_vision:setting.local_only_vision,allowed_folders:setting.allowed_folders,max_steps:setting.max_steps,max_seconds:setting.max_seconds,max_failures:setting.max_failures,max_files:setting.max_files,actions_per_second:setting.actions_per_second,...patch};
  const result=await requestJSON<Policy>('/v1/computer/settings',{method:'PUT',body:JSON.stringify(payload)});setInfo(s=>s?{...s,settings:result}:s)}catch(e){setError(String(e))}finally{setBusy(false)}}
 async function sendApproval(accepted:boolean){if(!task?.pending)return;let updated_args:Record<string,unknown>|undefined;
   try{updated_args=JSON.parse(approvalEdit) as Record<string,unknown>}catch{setError(L('صيغة JSON غير صحيحة','Invalid approval JSON'));return}
   await send('/v1/computer/approve',{id:task.pending.id,accepted,updated_args})}
 if(info?.supported===false)return <section className="rounded-xl border border-stroke bg-elevated p-4 text-sm text-secondary" role="status">{L('التحكم في الكمبيوتر متاح على Windows 10/11 فقط؛ باقي أنظمة التشغيل غير مدعومة حاليًا.','Computer control currently requires Windows 10/11.')}</section>;
 return <section data-barq-computer-release="v2.30-recovery-brain" className="space-y-4 rounded-xl border border-stroke bg-surface p-4" aria-label={L('التحكم في الكمبيوتر','Computer control')}>
  <div className="flex flex-wrap items-center justify-between gap-2"><div className="flex items-center gap-2"><Monitor size={18}/><h3 className="text-base font-semibold">{L('التحكم في الكمبيوتر','Computer Control')}</h3></div>
   <div role="status" className={`rounded-full border px-3 py-1 text-xs ${task&&['running','planning','approval'].includes(task.status)?'border-danger text-danger':'border-stroke text-secondary'}`}>{task?.status??(setting?.enabled?L('صلاحية التحكم مفعّلة','Control enabled'):L('صلاحية التحكم مقفولة','Control disabled'))}{task?.progress?` · ${task.progress}`:''}</div>
   {task&&['running','planning','approval'].includes(task.status)&&<Button variant="danger" size="sm" icon={<PauseOctagon size={16}/>} onClick={()=>{void send('/v1/computer/stop')}}>{L('إيقاف فورًا','STOP NOW')}</Button>}
  </div>
  {!settingsOnly&&info?.health&&<div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-stroke bg-elevated px-3 py-2 text-xs text-secondary" aria-label={L('حالة محرك برق','BARQ engine health')}>
    <span>{L('وقت التشغيل','Uptime')}: {Math.floor(info.health.uptime_seconds/60)}m</span>
    <span>RAM: {info.health.memory_mb===null?'—':`${info.health.memory_mb} MB`}</span>
    <span>CPU: {info.health.cpu_percent===null?'—':`${info.health.cpu_percent}%`}</span>
    {!!info.recovered_count&&<span className="text-warning">{L('مهام انقطعت','Interrupted tasks')}: {info.recovered_count}</span>}
   </div>}
  {!settingsOnly&&task&&<div className="space-y-2 rounded-lg border border-stroke bg-elevated p-3" aria-label={L('مراحل عقل برق','BARQ execution pipeline')}>
    <p className="text-xs font-semibold">{L('فهم الكلام ← النية ← التخطيط ← التنفيذ ← التحقق','Understand → Intent → Plan → Execute → Verify')}</p>
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
     {([{id:'understand',ar:'فهم الكلام',en:'Understand'},{id:'intent',ar:'تحديد النية',en:'Intent'},
        {id:'plan',ar:'تخطيط',en:'Plan'},{id:'execute',ar:'تنفيذ',en:'Execute'},
        {id:'verify',ar:'تحقق',en:'Verify'}] as const).map(stage=><div key={stage.id}
       className={`rounded-md border px-2 py-2 text-center text-xs ${task.phase===stage.id?'border-danger text-primary font-semibold':'border-stroke text-secondary'}`}
       aria-current={task.phase===stage.id?'step':undefined}>{L(stage.ar,stage.en)}</div>)}
    </div>
    {task.intent&&<p className="text-xs text-secondary">{L('النية المكتشفة','Detected intent')}: {task.intent.label} · {L('المصدر','Source')}: {task.intent.source}</p>}
    {task.goal_proof?.status&&<p role="status" className={`text-xs ${task.goal_proof.status==='verified'?'text-success':'text-warning'}`}>
     {task.goal_proof.status==='verified'?L('النتيجة مؤكدة بفحص مستقل','Outcome independently verified'):L('النتيجة غير مؤكدة بعد','Outcome not yet verified')} · {task.goal_proof.reason}
    </p>}
  </div>}
  {!settingsOnly&&<div className="space-y-3"><label className="block text-sm">{L('اكتب المهمة بوضوح','Describe the task')}<textarea className="ui-input mt-1 min-h-20 w-full" maxLength={3000} value={goal} onChange={e=>setGoal(e.target.value)} placeholder={L('افتح المفكرة وأنشئ ملفًا تجريبيًا داخل AgentWorkspace','Open Notepad and create a test document in AgentWorkspace')}/></label>
   <label className="block text-sm">{L('النموذج','Model')}<input className="ui-input mt-1 w-full" dir="ltr" value={model} onChange={e=>setModel(e.target.value)} placeholder="auto"/></label>
   <Button variant="primary" disabled={busy||!setting?.enabled||!goal.trim()||!!task&&['running','planning','approval'].includes(task.status)} icon={<Play size={16}/>} onClick={()=>{void send('/v1/computer/start',{conversation_id:useApp.getState().activeId||'',goal,model})}}>{L('ابدأ المهمة','Start task')}</Button>
   <p className="text-xs text-secondary">{L('المهام تنفذ على جهازك بعد المرور ببوابة الأمان. انقل المؤشر لأعلى يسار الشاشة للإيقاف الطارئ.','Tasks execute on this device with a safety gate. Move the pointer to the top-left corner to abort.')}</p>
  </div>}
  {!settingsOnly&&checkpoints&&checkpoints.tasks.length>0&&<details className="rounded-lg border border-stroke bg-elevated p-3">
    <summary className="cursor-pointer text-sm font-semibold">{L('المهام المحفوظة واستعادة العمل','Saved tasks & recovery')} ({checkpoints.tasks.length})</summary>
    <p className="mt-2 text-xs text-secondary">{L('لا يتم إعادة تشغيل الإجراءات أو تكرار الموافقات تلقائيًا بعد توقف برق. الاستكمال يبدأ بفحص جديد للجهاز.','Actions and approvals are never replayed automatically. Continuation starts a new observation.')}</p>
    <div className="mt-2 space-y-2">{checkpoints.tasks.map(saved=><div key={saved.id} className="flex items-start justify-between gap-2 rounded-md border border-stroke p-2">
      <div className="min-w-0"><p className="truncate text-xs font-medium">{saved.goal}</p><p className="text-xs text-secondary">{saved.status} · {saved.progress} {L('خطوة','steps')}</p></div>
      {['interrupted','needs_review','failed','limit'].includes(saved.status)&&<Button size="sm" variant="secondary" disabled={busy||!setting?.enabled||!!task&&['running','planning','approval'].includes(task.status)} onClick={()=>{
        if(window.confirm(L('هيبدأ برق المهمة من جديد بملاحظة الحالة الحالية للجهاز، من غير إعادة تشغيل الخطوات المحفوظة تلقائيًا. موافق؟','BARQ will begin again from a fresh observation, without replaying saved actions. Continue?')))void send('/v1/computer/continue',{task_id:saved.id,confirmed:true});
      }}>{L('فحص واستكمال','Recheck')}</Button>}
    </div>)}</div>
   </details>}
  {bridgeStatus&&<div className="flex items-center justify-between gap-3 rounded-lg border border-stroke bg-elevated p-3" role="status">
    <div><h4 className="text-sm font-semibold">Windows-MCP · BARQ System Bridge</h4>
      <p className="mt-1 text-xs text-secondary">{bridgeStatus.installed?L('الأداة متثبتة، وبرق هيشغّلها محليًا عند الحاجة. لا يوجد وصول عن بُعد.','Installed; BARQ launches it locally on demand. No remote access.'):L('لسه مش متثبتة. اختار Windows-MCP أثناء تثبيت برق، أو شغّل INSTALL_BARQ_WINDOWS_MCP.bat من مجلد البرنامج.','Not installed. Select Windows-MCP during BARQ Setup or run INSTALL_BARQ_WINDOWS_MCP.bat in the installation folder.')}</p>
      <p className="mt-1 text-xs text-secondary">v{bridgeStatus.version_pinned} · {bridgeStatus.transport} · {L('الأوامر الحساسة تمر على موافقة برق','Sensitive actions still require BARQ approval')}</p>
    </div><span className={`shrink-0 rounded-md px-2 py-1 text-xs ${bridgeStatus.installed?'border border-success text-success':'border border-warning text-warning'}`}>{bridgeStatus.installed?L('مثبّت','Installed'):L('مطلوب التثبيت','Missing')}</span>
  </div>}
  {setting&&<div className="flex items-center justify-between gap-3 rounded-lg border border-stroke bg-elevated p-3">
    <div><h4 className="text-sm font-semibold">{L('تفعيل برق للتفاعل مع الكمبيوتر','Allow BARQ to interact with this PC')}</h4>
     <p className="mt-1 text-xs text-secondary">{L('تفعيل اختياري للشات والصوت. فتح التطبيقات والكتابة والتنقل يتم داخل حدود الصلاحيات؛ الأوامر الحساسة تحتاج موافقة على الشاشة.','Opt in to desktop actions from chat and voice. Sensitive actions still require on-screen approval.')}</p></div>
    <label className="shrink-0"><input type="checkbox" aria-label={L('تفعيل التحكم في الجهاز','Enable computer interaction')} checked={setting.enabled} disabled={busy||!!task&&['running','planning','approval'].includes(task.status)} onChange={e=>{void update({enabled:e.target.checked})}} /></label>
  </div>}
  {settingsOnly&&fileIndex&&<section className="rounded-lg border border-stroke bg-elevated p-3 space-y-2" aria-label={L('بحث الملفات المحلي','Local file search')}>
    <h4 className="text-sm font-semibold">{L('فهرس بحث برق في الجهاز','BARQ local file index')}</h4>
    <p className="text-xs text-secondary">{L('البحث في أسماء الملفات محلي. قراءة محتوى المستندات اختيار منفصل ويتطلب إذنك، ولا يتم إرساله للسحابة.','Filename search is local. Document contents require separate opt-in and are never automatically uploaded.')}</p>
    <label className="flex gap-2 items-center text-sm"><input type="checkbox" checked={fileIndex.settings.enabled} disabled={busy||!setting?.enabled} onChange={e=>void setFileIndexMode(e.target.checked,fileIndex.settings.all_local_drives)}/>{L('تفعيل فهرسة الملفات','Enable local file indexing')}</label>
    <label className="flex gap-2 items-center text-sm"><input type="checkbox" checked={fileIndex.settings.all_local_drives} disabled={busy||!fileIndex.settings.enabled} onChange={e=>void setFileIndexMode(true,e.target.checked)}/>{L('السماح بفهرسة كل الأقراص المحلية (بدون مجلدات النظام)','Include all local drives, excluding protected folders')}</label>
    <label className="flex gap-2 items-center text-sm"><input type="checkbox" checked={fileIndex.settings.content_enabled} disabled={busy||!fileIndex.settings.enabled} onChange={e=>void setFileIndexMode(true,fileIndex.settings.all_local_drives,e.target.checked)}/>{L('السماح بفهرسة نصوص المستندات محليًا (PDF / Word / Excel / نص / كود)','Opt in to local document content indexing (PDF / Word / text / code)')}</label>
    {fileIndex.settings.content_enabled&&<div className="space-y-2">
     <p role="status" className="text-xs text-secondary">{L('فهرس المحتوى','Content index')}: {contentStatus?.status||'idle'} · {contentStatus?.indexed||0} {L('ملف اتفهرس في الدورة الحالية','files indexed this run')}</p>
     <div className="flex gap-2"><input className="ui-input min-w-0 flex-1" value={contentQuery} placeholder={L('ابحث داخل المستندات…','Search inside documents…')} onChange={e=>setContentQuery(e.target.value)}/><Button size="sm" variant="secondary" disabled={contentQuery.trim().length<2||busy} onClick={async()=>{try{const response=await requestJSON<{results:Array<{name:string;snippet:string}>}>(`/v1/device/content-search?query=${encodeURIComponent(contentQuery)}`);setContentResults(response.results||[])}catch(e){setError(String(e))}}}>{L('بحث','Search')}</Button></div>
     {contentResults.slice(0,10).map((hit,i)=><p key={`${hit.name}-${i}`} className="text-xs text-secondary"><strong>{hit.name}</strong> — {hit.snippet}</p>)}
    </div>}
    <p className="text-xs text-secondary">{L('الحالة','Status')}: {fileIndex.status} · {L('ملفات','Files')}: {fileIndex.entries} · {L('مجلدات','Folders')}: {fileIndex.folders} · Everything: {fileIndex.everything_available?'Ready':'Optional'}</p>
    {searchInstall&&searchInstall.status!=='idle'&&<p role="status" className="text-xs text-secondary">{L('تثبيت البحث','Search installation')}: {searchInstall.status} {searchInstall.step} {searchInstall.message}</p>}
    <Button variant="secondary" size="sm" disabled={busy||!fileIndex.settings.enabled} onClick={async()=>{try{await requestJSON('/v1/device/index/refresh',{method:'POST'});await refreshFileIndex()}catch(e){setError(String(e))}}}>{L('تحديث الفهرس','Refresh index')}</Button>
    {!fileIndex.everything_available&&<Button variant="secondary" size="sm" disabled={busy||!fileIndex.settings.enabled} onClick={async()=>{
       if(!window.confirm(L('توافق على تثبيت محرك Everything الرسمي من winget؟ ممكن تظهر موافقة Windows، ومش هيتم تشغيل أي كود من GitHub.','Install official Everything through winget? Windows may ask for confirmation.')))return;
       try{const answer=await requestJSON<{status:string;message?:string}>('/v1/device/index/install-everything',{method:'POST',body:JSON.stringify({approved:true})});setError(answer.message||answer.status)}catch(e){setError(String(e))}
      }}>{L('تثبيت بحث Everything الرسمي','Install official Everything')}</Button>}

   </section>}
  {setting&&<details open={settingsOnly} className="rounded-lg border border-stroke p-3"><summary className="cursor-pointer text-sm font-semibold">{L('الصلاحيات والأمان','Safety and permissions')}</summary>
   <div className="mt-3 space-y-3"><label className="block text-sm">{L('وضع الصلاحيات','Permission mode')}<select className="ui-input mt-1 w-full" value={setting.mode} disabled={busy||!!task&&['running','planning','approval'].includes(task.status)} onChange={e=>{void update({mode:e.target.value as Mode})}}>
     <option value="observe">{L('مراقبة فقط','Observe only')}</option><option value="ask-always">{L('اسأل قبل كل خطوة','Ask before every action')}</option><option value="smart">{L('تنفيذ تلقائي للأوامر اليومية','Automatic everyday actions')}</option><option value="trusted">{L('موثوق — للمختبرات فقط','Trusted — sandbox only')}</option>
    </select></label>
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={setting.direct_commands??true} disabled={busy} onChange={e=>{void update({direct_commands:e.target.checked})}}/>{L('نفّذ أوامري مباشرة بدون موافقات متكررة','Execute my commands directly')}</label>
    {setting.mode==='smart'&&!setting.direct_commands&&<p className="text-xs text-secondary">{L('فعّل التحكم مرة واحدة. يفتح برق التطبيقات والملفات العادية ويبحث في الملفات غير الحساسة وينفّذ التعديلات داخل مجلدات العمل المسموح بها مباشرة. العمليات الخطرة ما زالت تحتاج مراجعة، ولا يمكن تجاوز صلاحيات Windows.','Enable computer control once. Everyday app launches, ordinary file reads and workspace edits then run without repeated prompts. Risky operations still need review; Windows permissions are unchanged.')}</p>}
    {setting.direct_commands&&<p className="text-xs text-secondary">{L('الأمر الصريح منك يصرّح بخطوات تنفيذه: التطبيقات والملفات والإعدادات والتثبيت والبرمجة. زر الإيقاف وحدود Windows والعمليات المحظورة تظل فعالة.','Your direct request authorizes its execution steps: apps, files, settings, installation and coding. Stop controls, Windows permissions and blocked operations remain active.')}</p>}
    {setting.mode==='trusted'&&<p role="alert" className="rounded-md border border-warning p-2 text-xs text-warning"><AlertTriangle size={14} className="inline"/> {L('تنبيه: هذا الوضع عالي الخطورة. استخدم جهازًا تجريبيًا فقط.','Warning: Trusted mode is dangerous. Use a disposable VM only.')}</p>}
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={setting.local_only_vision} disabled={busy} onChange={e=>{void update({local_only_vision:e.target.checked})}}/>{L('صور الشاشة محليًا فقط (Ollama)','Local-only screenshots (Ollama)')}</label>
    <p className="text-xs text-secondary">{L('لا يتم إرسال لقطات الشاشة للسحابة في هذا الإصدار.','This release never sends screenshots to cloud models.')}</p>
    <label className="block text-sm">{L('المجلدات المسموح بها (كل مسار بسطر)','Allowed folders (one per line)')}<textarea dir="ltr" className="ui-input mt-1 w-full font-mono text-xs" rows={3} value={folders} onChange={e=>setFolders(e.target.value)}/></label>
    <Button variant="secondary" disabled={busy} size="sm" icon={<ShieldCheck size={15}/>} onClick={()=>{void update({allowed_folders:folders.split('\n').map(s=>s.trim()).filter(Boolean)})}}>{L('حفظ المجلدات','Save folders')}</Button>
    <Button variant="secondary" disabled={busy} size="sm" onClick={async()=>{try{const result=await requestJSON<{folders:string[]}>('/v1/computer/standard-user-folders');const normal=result.folders.filter(Boolean);if(!normal.length){setError(L('مجلدات المستخدم المعتادة غير موجودة على هذا الجهاز.','Standard folders not found.'));return}await update({allowed_folders:normal});setFolders(normal.join('\n'))}catch(e){setError(String(e))}}}>{L('السماح بمجلدات سطح المكتب والمستندات والتنزيلات','Allow Desktop, Documents and Downloads')}</Button>
    <div className="text-xs text-secondary">{L('حدود افتراضية','Default limits')}: {setting.max_steps} {L('خطوة','steps')} · {setting.max_seconds}s · {setting.max_files} {L('ملفًا','files')} · {setting.actions_per_second}/s</div>
    <details><summary className="cursor-pointer text-xs">{L('الإجراءات المحظورة','Blocked actions')}</summary><ul className="mt-2 list-disc ps-5 text-xs text-secondary">{setting.blocked_categories.map(x=><li key={x}>{x}</li>)}</ul></details>
    <p className="text-xs text-secondary">{L('Sandbox غير منفذ آليًا في هذا الإصدار، ويجب استخدام Windows Sandbox خارجيًا.','One-click sandbox not implemented; use Windows Sandbox separately.')}</p>
   </div></details>}
  {settingsOnly&&<details className="rounded-xl border border-stroke p-3" aria-label={L('صلاحيات المشاريع','Project grants')}>
    <summary className="cursor-pointer text-sm font-semibold">{L('صلاحيات المشاريع — امنحها مرة واحدة','Project permissions — one-time consent')}</summary>
    <p className="mt-2 text-xs text-secondary">{L('اختار مجلد مشروع واحد والصلاحيات اللي برق مسموح له يستخدمها فيه. العمليات الخطرة تفضل تحتاج موافقة على الشاشة.','Choose one project folder and its exact scopes. Risky actions still require on-screen approval.')}</p>
    <div className="mt-3 flex flex-wrap gap-2">
      <Button variant="secondary" size="sm" disabled={busy||!setting?.enabled} onClick={()=>{void chooseProjectFolder()}}>{L('اختار فولدر المشروع','Choose project folder')}</Button>
      <input aria-label={L('مسار المشروع','Project folder path')} dir="ltr" className="ui-input min-w-0 flex-1 text-xs" value={projectFolder} onChange={e=>setProjectFolder(e.target.value)}/>
    </div>
    <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">{grantOptions.map(scope=><label key={scope} className="flex items-center gap-2 text-xs"><input type="checkbox" checked={grantScopes.includes(scope)} onChange={e=>setGrantScopes(old=>e.target.checked?[...old,scope]:old.filter(s=>s!==scope))}/>{scope}</label>)}</div>
    <div className="mt-3"><Button size="sm" variant="primary" disabled={busy||!setting?.enabled||!projectFolder.trim()||!grantScopes.length} onClick={()=>{void addProjectGrant()}}>{L('اسمح للمشروع','Grant project')}</Button></div>
    <div className="mt-3 space-y-2">{grants.map(g=><div key={g.id} className="flex items-center justify-between gap-2 rounded-lg border border-stroke p-2 text-xs"><div className="min-w-0"><p dir="ltr" className="break-all">{g.root}</p><p className="text-secondary">{g.scopes.join(' · ')}</p></div><Button variant="danger" size="sm" onClick={()=>{void revokeProjectGrant(g.id)}}>{L('إلغاء','Revoke')}</Button></div>)}</div>
    <div className="mt-3 flex flex-wrap gap-2"><Button variant="secondary" size="sm" disabled={busy} onClick={()=>{void runDoctor()}}>{L('افحص أدوات Windows','Check Windows tools')}</Button><Button variant="danger" size="sm" disabled={busy||!grants.length} onClick={async()=>{await send('/v1/computer/execution/revoke-all');await refreshGrants()}}>{L('إلغاء كل التصاريح','Revoke all')}</Button></div>
    {!!doctorTools.length&&<div role="status" className="mt-2 grid grid-cols-2 gap-2 text-xs">{doctorTools.map(t=><p key={t.tool}>{t.tool}: {t.status==='available'?L('متاح','Available'):L('ناقص','Missing')}</p>)}</div>}
   </details>}
  {settingsOnly&&installPaths&&<details className="barq-settings-disclosure text-xs" aria-label={L('مسارات برق','BARQ locations')}>
    <summary className="font-semibold">{L('ملفات برق موجودة فين؟','Where are BARQ files?')}</summary>
    <p className="text-secondary">{L('ملفات البرنامج والموديل الصوتي في مجلد التثبيت المختار، وبيانات المحادثات والإعدادات محفوظة بشكل منفصل عشان ما تضيعش مع التحديث.','App and voice model files live in the chosen installer folder. Writable chats/settings are separate to protect them during upgrades.')}</p>
    <p className="mt-2 text-secondary">{L('في Gemini Live السحابي، إجابة معلومات النظام المختصرة يمكن إرسالها إلى Gemini ليرد عليك صوتيًا. لا يتم إرسال ملفاتك أو كلمات مرورك من هذا الفحص.','In cloud Gemini Live calls, the short device-facts answer may be shared with Gemini to speak back. This check does not send your files or passwords.')}</p>
    <dl className="mt-2 space-y-2" dir="ltr"><div><dt>BARQ / EXE</dt><dd className="break-all select-text font-mono">{installPaths.application}</dd></div>
    <div><dt>User data</dt><dd className="break-all select-text font-mono">{installPaths.user_data}</dd></div>
    <div><dt>Arabic wake model</dt><dd className="break-all select-text font-mono">{installPaths.wake_model}</dd></div></dl>
   </details>}
  {!settingsOnly&&task&&<div className="space-y-3">
   <p className="text-xs text-secondary">{task.goal}</p><ol className="list-decimal space-y-1 ps-5 text-xs">{task.steps.map((s,i)=><li key={i}>{s}</li>)}</ol>
   {task.pending&&<div role="alertdialog" aria-label={L('موافقة على إجراء','Approval required')} className="space-y-2 rounded-lg border border-warning bg-elevated p-3"><div className="flex items-center gap-2 text-sm font-semibold"><ShieldAlert size={17}/>{L('هل توافق على تنفيذ هذا الإجراء؟','Approve this action?')}</div>
    <p className="text-xs text-secondary">{task.pending.tool} — {task.pending.reason}</p>
    <p className="text-xs text-warning">{L('الموافقة تنتهي خلال 60 ثانية. راجع الأمر أو المسار بدقة.','Approval expires in 60 seconds. Review the exact command/path.')}</p>
    <textarea className="ui-input w-full font-mono text-xs" dir="ltr" value={approvalEdit} rows={4} onChange={e=>setApprovalEdit(e.target.value)}/>
    <img src={`/v1/computer/screenshot?approval=${encodeURIComponent(task.pending.id)}`} alt={L('الشاشة قبل الإجراء مع إبراز الهدف إن أمكن','Screen before approval; target highlighted when available')} className="max-h-44 w-full rounded-lg border border-stroke object-contain"/>
    <div className="flex flex-wrap gap-2"><Button variant="primary" size="sm" disabled={busy} icon={<Check size={15}/>} onClick={()=>{void sendApproval(true)}}>{L('موافقة','Approve')}</Button><Button variant="secondary" size="sm" disabled={busy} onClick={()=>{void sendApproval(false)}}>{L('رفض','Deny')}</Button></div>
   </div>}
   <div className="flex flex-wrap gap-2"><Button variant="secondary" size="sm" icon={<RotateCcw size={16}/>} disabled={busy||['running','planning','approval'].includes(task.status)} onClick={()=>{void send('/v1/computer/undo')}}>{L('تراجع عن آخر تغيير','Undo last change')}</Button><Button variant="ghost" size="sm" disabled={busy||['running','planning','approval'].includes(task.status)} onClick={()=>{void send('/v1/computer/undo-all')}}>{L('تراجع عن المهمة','Undo entire task')}</Button>
    {['running','approval'].includes(task.status)&&<Button variant="ghost" size="sm" icon={<Eye size={16}/>} onClick={()=>setImage(`/v1/computer/screenshot?t=${Date.now()}`)}>{L('معاينة الشاشة المحلية','View local screen')}</Button>}</div>
   {image&&<div className="overflow-hidden rounded-lg border border-stroke"><img src={image} alt={L('لقطة من الشاشة الحالية','Local desktop screenshot')} className="max-h-72 w-full object-contain"/><p className="p-2 text-xs text-secondary">{L('صورة محلية فقط؛ لا تُرسل لمزود سحابي.','Local preview only; not sent to a cloud provider.')}</p></div>}
   <section aria-live="polite" className="max-h-56 space-y-1 overflow-y-auto rounded-md border border-stroke p-2"><h4 className="mb-2 text-sm font-semibold">{L('سجل التنفيذ','Action timeline')}</h4>{task.history.map((h,i)=><p className="text-xs text-secondary" key={i}>{i+1}. {h.tool} · {h.status} {h.verification?`(${h.verification})`:''}{h.reason?` — ${h.reason}`:''}{h.verification_reason?` — ${h.verification_reason}`:''}</p>)}{task.message&&<p className="text-sm">{task.message}</p>}</section>
  </div>}
  {error&&<p className="rounded-md border border-danger p-2 text-xs text-danger" role="alert">{error}</p>}
 </section>
}
