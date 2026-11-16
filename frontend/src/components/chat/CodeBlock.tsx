import {useState} from 'react';
import {Prism as SyntaxHighlighter} from 'react-syntax-highlighter';
import {oneDark,oneLight} from 'react-syntax-highlighter/dist/esm/styles/prism';
import {Check,Copy,Download,FilePenLine,Play,RotateCcw,ShieldCheck} from 'lucide-react';
import {useApp} from '../../store';
import {IconButton} from '../ui/IconButton';import {Button} from '../ui/Button';import {Modal} from '../ui/Modal';
import {requestJSON} from '../../lib/backend';

type Preview={approval_id:string;path:string;diff:string};
const extension:Record<string,string>={python:'py',py:'py',typescript:'ts',tsx:'tsx',javascript:'js',jsx:'jsx',html:'html',css:'css',json:'json',rust:'rs',bash:'sh',shell:'sh',sql:'sql'};
export function CodeBlock({code,language='text',lineNumbers=false}:{code:string;language?:string;lineNumbers?:boolean}){
 const theme=useApp(s=>s.theme),workspace=useApp(s=>s.workspace),lang=useApp(s=>s.language),toast=useApp(s=>s.toast),[copied,setCopied]=useState(false);
 const [dialog,setDialog]=useState<'apply'|'tests'|null>(null),[path,setPath]=useState(''),[preview,setPreview]=useState<Preview|null>(null),[busy,setBusy]=useState(false),[testOutput,setTestOutput]=useState(''),[backupId,setBackupId]=useState<string|null>(null);
 const L=(ar:string,en:string)=>lang==='ar'?ar:en;
 async function copy(){try{await navigator.clipboard.writeText(code);setCopied(true);setTimeout(()=>setCopied(false),1500)}catch{toast('error',L('النسخ غير متاح','Clipboard unavailable'))}}
 function save(){const blob=new Blob([code],{type:'text/plain;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`snippet-${new Date().toISOString().slice(0,10)}.${extension[language]||'txt'}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
 async function prepare(){if(!workspace){toast('info',L('افتح مشروعًا أولًا','Open a project first'),L('انتقل إلى مساحة البرمجة وحدد مسار المشروع.','Select a folder in Coding Workspace.'));return}
  if(!path.trim()){toast('error',L('اكتب مسار الملف داخل المشروع','Enter relative file path'));return}
  setBusy(true);try{const data=await requestJSON<Preview>('/v1/workspace/edit/preview',{method:'POST',body:JSON.stringify({workspace,path:path.trim(),content:code})});setPreview(data)}catch(e){toast('error',L('المعاينة فشلت','Preview failed'),e instanceof Error?e.message:String(e))}finally{setBusy(false)}}
 async function apply(){if(!preview)return;setBusy(true);try{const result=await requestJSON<{saved:boolean;backup_id:string;path:string}>('/v1/workspace/edit/apply',{method:'POST',body:JSON.stringify({approval_id:preview.approval_id,confirmed:true})});setBackupId(result.backup_id);setPreview(null);toast('success',L('تم الحفظ مع نسخة احتياطية','File saved with backup'),result.path)}catch(e){toast('error',L('الحفظ فشل','Save failed'),e instanceof Error?e.message:String(e))}finally{setBusy(false)}}
 async function undo(){if(!backupId)return;setBusy(true);try{await requestJSON('/v1/workspace/edit/undo',{method:'POST',body:JSON.stringify({approval_id:backupId,confirmed:true})});setBackupId(null);toast('success',L('تم التراجع عن التعديل','Edit restored'))}catch(e){toast('error',L('التراجع فشل','Undo failed'),e instanceof Error?e.message:String(e))}finally{setBusy(false)}}
 async function runTests(){if(!workspace)return;setBusy(true);setTestOutput(L('جاري تشغيل الاختبارات…','Running tests…'));try{const result=await requestJSON<{exit_code:number;stdout:string;stderr:string}>('/v1/tools/run',{method:'POST',body:JSON.stringify({tool_id:'project_tests',workspace,confirmed:true})});setTestOutput(`${L('كود الخروج','Exit code')}: ${result.exit_code}\n${result.stdout}\n${result.stderr}`)}catch(e){setTestOutput(e instanceof Error?e.message:String(e))}finally{setBusy(false)}}
 return <div className="my-4 min-w-0 overflow-hidden rounded-xl border border-stroke bg-elevated" dir="ltr">
   <div className="flex flex-wrap items-center justify-between gap-2 border-b border-stroke px-3 py-2"><span className="font-code text-xs font-medium text-secondary">{language||'text'}</span><div className="flex items-center gap-1">
    <IconButton label={copied?L('تم النسخ','Copied'):L('نسخ الكود','Copy code')} icon={copied?<Check size={17} className="text-success"/>:<Copy size={17}/>} className="!min-h-8 !min-w-8" onClick={()=>void copy()}/>
    <IconButton label={L('حفظ الكود كملف','Download code as file')} icon={<Download size={17}/>} className="!min-h-8 !min-w-8" onClick={save}/>
    <IconButton label={L('معاينة التطبيق على المشروع','Review applying code to project')} icon={<FilePenLine size={17}/>} className="!min-h-8 !min-w-8" onClick={()=>{setPreview(null);setDialog('apply')}}/>
    <IconButton label={L('تشغيل اختبارات المشروع بعد الموافقة','Run project tests after approval')} icon={<Play size={17}/>} className="!min-h-8 !min-w-8" onClick={()=>{setTestOutput('');setDialog('tests')}}/>
   </div></div>
   <div className="overflow-x-auto font-code text-[13px] leading-[1.7]"><SyntaxHighlighter language={language} style={theme==='dark'?oneDark:oneLight} showLineNumbers={lineNumbers} wrapLongLines={false} PreTag="div" customStyle={{margin:0,padding:'16px',background:theme==='dark'?'#111419':'#f6f7fc',fontSize:'13px'}}>{code.trimEnd()}</SyntaxHighlighter></div>
   <Modal open={dialog==='apply'} onClose={()=>{if(!busy){setDialog(null);setPreview(null)}}} title={L('معاينة تعديل ملف','Review code change')} wide>
    <div className="space-y-3" dir="auto"><p className="text-sm text-secondary">{L('لا يتم تعديل أي ملف قبل مراجعة الفرق وموافقتك. ضع المسار النسبي للملف داخل المشروع المفتوح.','No file is modified until you review the diff and approve. Enter a relative path within the selected project.')}</p>
     <p className="truncate rounded-lg bg-elevated p-2 font-mono text-xs" dir="ltr">{workspace||L('لا يوجد مشروع مفتوح','No workspace selected')}</p>
     <input className="ui-input" dir="ltr" aria-label={L('مسار الملف النسبي','Relative file path')} placeholder="src/example.py" value={path} onChange={e=>setPath(e.target.value)}/>
     {!preview?<Button size="sm" variant="secondary" disabled={busy||!path.trim()||!workspace} onClick={()=>void prepare()}>{L('معاينة التغييرات','Preview changes')}</Button>:<><p className="text-sm font-semibold"><ShieldCheck size={16} className="inline"/> {L('راجع الفرق قبل الحفظ','Review diff before saving')}</p><pre dir="ltr" className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-base p-3 font-mono text-xs">{preview.diff}</pre><Button variant="primary" size="sm" disabled={busy} onClick={()=>void apply()}>{L('موافقة وحفظ','Approve and save')}</Button></>}
     {backupId&&<Button variant="secondary" size="sm" disabled={busy} icon={<RotateCcw size={16}/>} onClick={()=>void undo()}>{L('التراجع عن آخر تعديل','Undo last edit')}</Button>}
    </div>
   </Modal>
   <Modal open={dialog==='tests'} onClose={()=>{if(!busy)setDialog(null)}} title={L('اختبارات المشروع','Project tests')}>
    <div className="space-y-3"><p className="text-sm text-secondary">{L('تشغيل الاختبارات قد ينفذ كود المشروع. تأكد إنه مشروع موثوق قبل الموافقة.','Tests execute code from your project. Only run tests for a trusted project.')}</p><p dir="ltr" className="truncate rounded-lg bg-elevated p-2 font-mono text-xs">{workspace||L('لا يوجد مشروع مفتوح','No workspace selected')}</p><Button variant="primary" size="sm" disabled={!workspace||busy} onClick={()=>void runTests()}>{L('أوافق على تشغيل pytest','Approve running pytest')}</Button><pre dir="ltr" className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-base p-3 font-mono text-xs">{testOutput||L('لم تبدأ الاختبارات بعد','Tests have not started')}</pre></div>
   </Modal>
  </div>;
}
