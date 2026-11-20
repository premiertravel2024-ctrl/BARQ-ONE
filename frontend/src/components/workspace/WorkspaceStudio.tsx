/** BARQ Studio: project-aware mini IDE. No AI proposal writes without review. */
import {useCallback,useEffect,useMemo,useRef,useState, type CSSProperties, type MouseEvent as ReactMouseEvent} from 'react';
import {MessageCircle, Bot,Braces,Check,ChevronDown,ChevronRight,Code2,Columns2,Command,FileCode2,FileDiff,Folder,FolderOpen,GitBranch,Hammer,LayoutGrid,Maximize2,Monitor,PanelBottomClose,PanelBottomOpen,Play,RotateCcw,Save,Search,Settings2,ShieldAlert,ShieldCheck,Terminal,Workflow,X} from 'lucide-react';
import {useApp} from '../../store';
import {requestJSON} from '../../lib/backend';
import {addEditorFile,reconcileFiles,announceWorkspaceChange,type EditorFile,type DiskFile,type FileSnapshot} from '../../lib/workspaceSync';
import {pendingApproval} from '../../lib/approvals';
import {Button} from '../ui/Button';
import {WorkspaceTools} from './WorkspaceTools';
import {stopGeneration} from '../../lib/chat';
import {LiveCodePanel} from './LiveCodePanel';
import {AgentCodePanel,type LiveDraft} from './AgentCodePanel';
import {PreviewPanel} from './PreviewPanel';
import {WorkCenter} from './WorkCenter';
import type {UiAudit} from './uiAudit';
import {SafetyMonitor,type SafetyReport,type SafetyFinding} from './SafetyMonitor';
import {GuardianDashboard} from './GuardianDashboard';
import {generatedBlocks} from '../../lib/studioStream';
import {chooseWorkspaceSource,pendingSource} from '../../lib/studioProjectFocus';
import {DEFAULT_LAYOUT,useWorkspaceLayout,useWorkspaceFiles,useWorkspaceAI,useWorkspaceMonitor, type Layout} from './studioHooks';

type Entry={name:string;path:string;is_dir:boolean;size:number|null};
type Tree={root:string;items:Entry[];truncated:boolean;stack:string[]};
type DiffPreview={approval_id:string;path:string;diff:string;changed:boolean};
type Activity='explorer'|'search'|'git'|'commands'|'run'|'build'|'tools'|'github'|'computer'|'guardian';
type Bottom='output'|'problems'|'operations'|'tasks'|'terminal'|'security';
type Operation={time:number;actor:string;type:string;details:string;status:string};
type Git={available:boolean;branch:string;changes:string[]};
const activityItems=[
 ['explorer','الملفات',Folder],['search','البحث',Search],['git','التحكم بالإصدارات',GitBranch],
 ['commands','الأوامر والموجّهات',Command],['run','التشغيل والمهام',Play],
 ['guardian','مركز المراقبة',ShieldCheck],['build','بناء EXE',Hammer],['tools','أدوات REA',Braces],['github','GitHub',Workflow],['computer','التحكم في الجهاز',Monitor]
] as const;
const activityGroups=[['explorer','search','git'],['commands','run','guardian','build'],['tools','github','computer']] as const;
const legacy:Partial<Record<Activity,'overview'|'agent'|'build'|'tools'|'github'|'computer'>>={build:'build',tools:'tools',github:'github',computer:'computer'};
const fileLang=(path:string)=>({py:'python',ts:'typescript',tsx:'typescriptreact',js:'javascript',jsx:'javascriptreact',json:'json',html:'html',css:'css',rs:'rust',go:'go',md:'markdown',txt:'plaintext'}[path.split('.').pop()?.toLowerCase()||'']||'plaintext');
function clamp(value:number,min:number,max:number){return Math.min(max,Math.max(min,value))}
function titleOf(path:string){return path.split('/').at(-1)||path}
const errorText=(err:unknown)=>err instanceof Error?err.message:String(err);

export function WorkspaceStudio({open,onClose}:{open:boolean;onClose:()=>void;embedded?:boolean}){
 const language=useApp(s=>s.language);const rtl=language==='ar';const workspaceInStore=useApp(s=>s.workspace),setStoredWorkspace=useApp(s=>s.setWorkspace);
 const selectedModel=useApp(s=>s.selectedModel),localOnly=useApp(s=>s.options.localOnly),toast=useApp(s=>s.toast),handoff=useApp(s=>s.toolHandoff);
 const [path,setPath]=useState(workspaceInStore);const [tree,setTree]=useState<Tree|null>(null),[git,setGit]=useState<Git|null>(null);
 const [activity,setActivity]=useState<Activity>('explorer'),[bottom,setBottom]=useState<Bottom>('output');
 const [layout,setLayout]=useWorkspaceLayout();const [hydrated,setHydrated]=useState(false);
 const {files,setFiles,activeFile,setActiveFile}=useWorkspaceFiles<EditorFile>();
 const filesRef=useRef(files);filesRef.current=files;
 const treeRef=useRef<Tree|null>(null);treeRef.current=tree;
 const rootRef=useRef(''),generation=useRef(0),syncSequence=useRef(0),opening=useRef(false),saving=useRef(false);
 const [syncing,setSyncing]=useState(false);
 const [collapsed,setCollapsed]=useState<string[]>([]),[filter,setFilter]=useState(''),[search,setSearch]=useState('');
 const [results,setResults]=useState<Array<{file:string;line:number;text:string}>>([]),[timeline,setTimeline]=useState<Operation[]>([]);
 const [preview,setPreview]=useState<DiffPreview|null>(null),[previewContent,setPreviewContent]=useState<string|null>(null),[lastUndo,setLastUndo]=useState('');
 const [loading,setLoading]=useState(false),[output,setOutput]=useState(''),[palette,setPalette]=useState(false),[paletteText,setPaletteText]=useState('');
 const [diagnostics,setDiagnostics]=useState<{syntax_errors:Array<{file:string;errors:string[];line?:number}>;test_files:string[];python_files_checked:number;suggested_checks:string[];warnings:string[]}|null>(null);
 const [uiAudit,setUiAudit]=useState<UiAudit|null>(null),[uiAuditBusy,setUiAuditBusy]=useState(false),[uiAuditError,setUiAuditError]=useState('');
 const {reply,setReply,setReplyModel,setStreamStatus,aiLoading,setAiLoading}=useWorkspaceAI();
 const [editorView,setEditorView]=useState<'editor'|'live'|'diff'|'split'|'preview'|'guardian'|'work'>('live'),[codeTarget,setCodeTarget]=useState('');
 const [twoPane,setTwoPane]=useState(true);
 const [liveDraft,setLiveDraft]=useState<LiveDraft|null>(null);const liveSeen=useRef('');
 const activeChatId=useApp(s=>s.activeId);
 const [previewSource,setPreviewSource]=useState<{path:string;content:string;label:string}|null>(null);
 const {monitorDraft,setMonitorDraft,monitorProject,setMonitorProject,previewSafety,setPreviewSafety,monitorSource,setMonitorSource,monitorBusy,setMonitorBusy,projectScanBusy,setProjectScanBusy}=useWorkspaceMonitor<SafetyReport>();
 const [jumpTo,setJumpTo]=useState<{file:string;line:number}|null>(null);
 const editorTextRef=useRef<HTMLTextAreaElement>(null);
 const [recent,setRecent]=useState<string[]>(()=>{try{const value:unknown=JSON.parse(localStorage.getItem('barq-studio-recent')||'[]');return Array.isArray(value)?value.filter((item):item is string=>typeof item==='string'):[]}catch{return []}});
 const [,setSelection]=useState('');
 const studioHandoff=useApp(s=>s.studioCodeHandoff);
 const activeChatStream=useApp(s=>s.streaming&&s.activeId===s.studioCodeHandoff?.chatId);
 const activeChatStreamingId=useApp(s=>s.streamingId);
 const currentPlan=useApp(s=>{const chat=s.chats.find(c=>c.id===s.activeId);return [...(chat?.messages||[])].reverse().find(m=>m.agentTask?.kind==='coding')?.agentTask});
 const plannedCode=pendingSource(currentPlan);
 const handoffMessage=useApp(s=>{const ref=s.studioCodeHandoff;if(!ref)return undefined;const chat=s.chats.find(c=>c.id===ref.chatId);return chat?.messages.find(m=>m.id===ref.messageId)||(s.streaming&&s.activeId===ref.chatId?chat?.messages.find(m=>m.id===s.streamingId):undefined)});
 const [lineInfo,setLineInfo]=useState({line:1,col:1});const workspace=path.trim();
 const active=files.find(f=>f.path===activeFile);const dirty=active&&active.content!==active.original;
 const generated=useMemo(()=>generatedBlocks(reply),[reply]);
 const generatedDraft=generated.find(block=>!!block.content);
 const codeDraft=editorView==='diff'&&previewContent&&preview?{path:preview.path,content:previewContent}:editorView==='live'&&plannedCode?plannedCode:editorView==='live'&&generatedDraft?{path:codeTarget||generatedDraft.filename||'barq-generated.html',content:generatedDraft.content}:active?{path:active.path,content:active.content}:null;
 const monitorReport=monitorSource==='project'?monitorProject:monitorDraft;
 const monitorCount=(monitorDraft?.findings.length||0)+(monitorProject?.findings.length||0);
 const persistenceRef=useRef('');const paletteInputRef=useRef<HTMLInputElement>(null);
 useEffect(()=>{if(handoff)setActivity(handoff.tab==='agent'?'commands':handoff.tab)},[handoff]);
 useEffect(()=>{if(!studioHandoff)return;setReply(handoffMessage?.content||'');setReplyModel(handoffMessage?.model||'');setAiLoading(!!handoffMessage?.isStreaming||activeChatStream);setStreamStatus((!!handoffMessage?.isStreaming||activeChatStream)?'برق بيكتب الكود في المحادثة...':'الكود من المحادثة جاهز للمراجعة');setEditorView('live')},[studioHandoff?.chatId,studioHandoff?.messageId,handoffMessage?.content,handoffMessage?.isStreaming,handoffMessage?.model,activeChatStream,activeChatStreamingId]);
 useEffect(()=>{if(!open||!plannedCode)return;setCodeTarget(plannedCode.path);setEditorView('live')},[open,plannedCode?.path,plannedCode?.content]);
 const message=useCallback((txt:string,problem=false)=>{setOutput(txt);if(problem)toast('error','مساحة العمل',txt)},[toast]);
 useEffect(()=>{
  const output=(event:Event)=>{const detail=(event as CustomEvent<{workspace:string;text:string}>).detail;
   if(detail?.workspace!==rootRef.current)return;setOutput(detail.text);setBottom('output');setLayout(l=>({...l,showBottom:true}))};
  window.addEventListener('barq-tool-output',output);return()=>window.removeEventListener('barq-tool-output',output);
 },[]);
 const sendToMainChat=useCallback((text:string)=>{
  const root=rootRef.current;if(root)setStoredWorkspace(root);
  window.dispatchEvent(new CustomEvent('barq-chat-prefill',{detail:{text:root?`${text}\nالمشروع المحدد: ${root}`:text}}));
 },[]);
 const approvalChat=useApp(state=>state.chats.find(c=>c.id===state.activeId));
 const approval=pendingApproval(approvalChat?.messages||[]);
 const reviewMission=()=>{if(approval)window.dispatchEvent(new CustomEvent('barq-review-approval',{detail:{chatId:useApp.getState().activeId,messageId:approval.messageId}}));else onClose()};
 useEffect(()=>{
  setLiveDraft(null);liveSeen.current='';
  if(!open||!activeChatId||!tree)return;
  let cancelled=false;let timer:ReturnType<typeof setTimeout>;
  const poll=async()=>{
   let nextDelay=1300;
   try{const data=await requestJSON<{draft:LiveDraft|null}>(`/v1/agent/live-code?conversation_id=${encodeURIComponent(activeChatId)}&workspace=${encodeURIComponent(tree.root)}`);
    if(cancelled)return;nextDelay=data.draft?.status==='streaming'?350:1300;setLiveDraft(previous=>previous?.id===data.draft?.id&&previous?.attempt===data.draft?.attempt&&previous?.code===data.draft?.code&&previous?.status===data.draft?.status?previous:data.draft);
    const key=data.draft?`${data.draft.id}:${data.draft.attempt}`:'';
    if(data.draft?.code&&liveSeen.current!==key){liveSeen.current=key;setEditorView('live')}
   }catch{/* Older server or disconnected API: preserve the editor. */}
   if(!cancelled)timer=setTimeout(()=>void poll(),nextDelay);
  };void poll();return()=>{cancelled=true;clearTimeout(timer)};
 },[open,activeChatId,tree?.root]);
 const stopAgentCode=()=>{if(activeChatId)void requestJSON('/v1/brain/cancel',{method:'POST',body:JSON.stringify({conversation_id:activeChatId})}).catch(err=>message(errorText(err),true))};
 const mission=useApp(state=>{
  const chat=state.chats.find(c=>c.id===state.activeId);
  return [...(chat?.messages||[])].reverse().find(m=>m.agentTask?.kind==='coding')?.agentTask;
 });
 // When a new coding job arrives, show the generated CODE rather than the full prompt.
 const lastShownMission=useRef('');
 useEffect(()=>{
  const key=mission?.taskId||mission?.commandId||'';
  if(open&&key&&key!==lastShownMission.current){lastShownMission.current=key;setEditorView('live');}
 },[open,mission?.taskId,mission?.commandId]);
 // Debounced local-only scan of the current editor / generated source. No cloud or code execution.
 useEffect(()=>{
  let cancelled=false;
  if(!open||!codeDraft){setMonitorDraft(null);setMonitorBusy(false);return;}
  setMonitorBusy(true);
  const timer=window.setTimeout(()=>{
   void requestJSON<SafetyReport>('/v1/studio/monitor/draft',{method:'POST',body:JSON.stringify(codeDraft)})
    .then(report=>{if(!cancelled)setMonitorDraft(report)})
    .catch(()=>{if(!cancelled)setMonitorDraft(null)})
    .finally(()=>{if(!cancelled)setMonitorBusy(false)});
  },850);
  return()=>{cancelled=true;window.clearTimeout(timer)};
 },[open,codeDraft?.path,codeDraft?.content]);
 const runSecurityProjectScan=useCallback(async()=>{
  if(!tree||projectScanBusy)return;
  setProjectScanBusy(true);
  try{
   const report=await requestJSON<SafetyReport>(`/v1/studio/monitor/project?workspace=${encodeURIComponent(tree.root)}`);
   setMonitorProject(report);setMonitorSource('project');setBottom('security');setLayout(l=>({...l,showBottom:true}));
  }catch(err){message(`فشل فحص الأمان المحلي: ${errorText(err)}`,true)}
  finally{setProjectScanBusy(false)}
 },[tree,projectScanBusy,message]);
 const showMonitor=()=>{setEditorView('guardian');setActivity('guardian');setLayout(l=>({...l,showAI:false,showBottom:false}))};
 const fixFinding=(finding:SafetyFinding)=>{
  sendToMainChat(`راجع مؤشر الأمان ${finding.rule} في الملف ${finding.file} عند السطر ${finding.line}، وجهز إصلاحًا للموافقة.`);
 };
 useEffect(()=>{
  if(!jumpTo||editorView!=='editor'||activeFile!==jumpTo.file||!editorTextRef.current)return;
  const el=editorTextRef.current;
  const lines=el.value.split('\n');const target=Math.max(1,Math.min(jumpTo.line,lines.length));
  const start=lines.slice(0,target-1).reduce((total,line)=>total+line.length+1,0);
  el.focus();el.setSelectionRange(start,start);el.scrollTop=Math.max(0,(target-4)*21);
  setLineInfo({line:target,col:1});setJumpTo(null);
 },[jumpTo,activeFile,editorView]);
 const refreshLog=useCallback(async(root:string)=>{try{const data=await requestJSON<{events:Operation[]}>(`/v1/studio/operations?workspace=${encodeURIComponent(root)}`);if(root===rootRef.current)setTimeline(data.events)}catch{/*optional*/}},[]);
 const refreshProject=useCallback(async(focusCode=false,suggestedPath?:string)=>{
  const root=rootRef.current;if(!root||opening.current||saving.current)return;
  const epoch=generation.current,sequence=++syncSequence.current;setSyncing(true);
  try{
   const previousTree=treeRef.current;
   const [data,disk,gitData]=await Promise.all([
    requestJSON<Tree>(`/v1/studio/tree?workspace=${encodeURIComponent(root)}`),
    requestJSON<{files:FileSnapshot[]}>('/v1/workspace/snapshots',{method:'POST',body:JSON.stringify({workspace:root,paths:filesRef.current.map(f=>f.path)})}),
    requestJSON<Git>(`/v1/studio/git?workspace=${encodeURIComponent(root)}`)
   ]);
   if(epoch!==generation.current||sequence!==syncSequence.current||saving.current)return;
   setTree(data);setGit(gitData);setFiles(prev=>reconcileFiles(prev,disk.files));void refreshLog(root);
   // Agent saved files on disk; show the actual source in the editor, not a fake typing animation.
   // Never switch away from an unsaved human draft or a pending conflict.
   if(focusCode&&!filesRef.current.some(f=>f.content!==f.original||f.disk)){
    const filename=chooseWorkspaceSource(previousTree?.root===root?previousTree.items:[],data.items,suggestedPath);
    if(filename){
     const existing=filesRef.current.find(f=>f.path===filename);
     const snapshot=disk.files.find(f=>f.path===filename);
     if(existing&&snapshot&&!('error' in snapshot)&&snapshot.exists){
      setActiveFile(filename);setEditorView(view=>view==='live'&&pendingSource([...(useApp.getState().chats.find(c=>c.id===useApp.getState().activeId)?.messages||[])].reverse().find(m=>m.agentTask?.kind==='coding')?.agentTask)?'live':'editor');
     }else if(!existing){
      const fresh=await requestJSON<DiskFile>(`/v1/workspace/file?workspace=${encodeURIComponent(root)}&path=${encodeURIComponent(filename)}`);
      if(epoch!==generation.current||sequence!==syncSequence.current)return;
      const next=addEditorFile(filesRef.current,{path:filename,content:fresh.content,original:fresh.content,revision:fresh.revision});
      filesRef.current=next;setFiles(next);setActiveFile(filename);setEditorView(view=>view==='live'&&pendingSource([...(useApp.getState().chats.find(c=>c.id===useApp.getState().activeId)?.messages||[])].reverse().find(m=>m.agentTask?.kind==='coding')?.agentTask)?'live':'editor');
     }
     setActivity('explorer');
    }
   }
  }catch(err){if(epoch===generation.current)message(`تعذّر تحديث المشروع: ${errorText(err)}`,true)}
  finally{if(sequence===syncSequence.current)setSyncing(false)}
 },[message,refreshLog]);
 useEffect(()=>{
  if(!open)return;
  const changed=(event:Event)=>{const detail=(event as CustomEvent<{workspace:string;path?:string}>).detail;if(detail?.workspace===rootRef.current)void refreshProject(true,detail.path)};
  const focus=()=>{void refreshProject()};
  window.addEventListener('barq-workspace-changed',changed);window.addEventListener('focus',focus);
  void refreshProject();
  return()=>{window.removeEventListener('barq-workspace-changed',changed);window.removeEventListener('focus',focus)};
 },[open,refreshProject]);
 useEffect(()=>{
  const leave=(event:BeforeUnloadEvent)=>{if(filesRef.current.some(f=>f.content!==f.original||f.disk)){event.preventDefault();event.returnValue=''}};
  window.addEventListener('beforeunload',leave);return()=>window.removeEventListener('beforeunload',leave);
 },[]);
 const openProject=useCallback(async(folder:string)=>{
  const real=folder.trim();if(!real)return;
  if(saving.current){message('استنى اكتمال الحفظ قبل تبديل المشروع.');return}
  if(rootRef.current&&filesRef.current.some(f=>f.content!==f.original||f.disk)&&!window.confirm('في تغييرات غير محفوظة. تفتح المشروع وتتخلى عنها؟')){setPath(rootRef.current);setStoredWorkspace(rootRef.current);return}
  const epoch=++generation.current;opening.current=true;setHydrated(false);
  setLoading(true);try{
   const [data,gitData,saved]=await Promise.all([
    requestJSON<Tree>(`/v1/studio/tree?workspace=${encodeURIComponent(real)}`),
    requestJSON<Git>(`/v1/studio/git?workspace=${encodeURIComponent(real)}`),
    requestJSON<{layout?:Partial<Layout>;tabs?:string[];activeFile?:string;activity?:Activity;bottomTab?:Bottom}>(`/v1/studio/state?workspace=${encodeURIComponent(real)}`)
   ]);
   if(epoch!==generation.current)return;
   rootRef.current=data.root;setTree(data);setGit(gitData);setPath(data.root);setStoredWorkspace(data.root);
   setRecent(old=>{const updated=[data.root,...old.filter(item=>item!==data.root)].slice(0,8);localStorage.setItem('barq-studio-recent',JSON.stringify(updated));return updated});
   setFiles([]);setActiveFile('');setPreview(null);setPreviewContent(null);setResults([]);setEditorView(view=>useApp.getState().studioCodeHandoff?'live':view==='live'?'live':view==='work'?'editor':'editor');setMonitorDraft(null);setMonitorProject(null);setMonitorSource('draft');
   setLastUndo('');setDiagnostics(null);setUiAudit(null);setUiAuditError('');setPreviewSource(null);setCollapsed([]);setFilter('');setPreviewSafety(null);
   const next={...DEFAULT_LAYOUT,...saved.layout};setLayout(next);setActivity(current=>current==='github'?'github':saved.activity||'explorer');setBottom(saved.bottomTab||'output');
   setHydrated(false);persistenceRef.current=data.root;
   message(`تم فتح المشروع: ${data.root} · ${data.items.filter(i=>!i.is_dir).length} ملف ظاهر.`);
   await refreshLog(data.root);
   const state=useApp.getState();
   const currentChat=state.chats.find(c=>c.id===state.activeId);
   const currentMission=[...(currentChat?.messages||[])].reverse().find(m=>m.agentTask?.kind==='coding')?.agentTask?.missionProgress;
   const taskProject=currentMission?.files[0]?.path.split('/')[0];
   const ownsProject=!!taskProject&&data.items.some(entry=>entry.path.startsWith(taskProject+'/'));
   const all=(saved.tabs||[]).filter(p=>data.items.some(entry=>entry.path===p&&!entry.is_dir)&&(!ownsProject||p.startsWith(taskProject+'/'))).slice(0,12);
   const opened:EditorFile[]=[];
   for(const item of all){try{const file=await requestJSON<DiskFile>(`/v1/workspace/file?workspace=${encodeURIComponent(data.root)}&path=${encodeURIComponent(item)}`);opened.push({path:item,content:file.content,original:file.content,revision:file.revision})}catch{/*Unreadable files are skipped.*/}}
   if(epoch!==generation.current)return;
   let nextFiles=opened;
   const app=useApp.getState();
   const chat=app.chats.find(c=>c.id===app.activeId);
   const activeMission=[...(chat?.messages||[])].reverse().find(m=>m.agentTask?.kind==='coding')?.agentTask?.missionProgress;
   const lastWritten=[...(activeMission?.files||[])].reverse().find(item=>item.status==='written'||item.status==='verified')?.path;
   const focused=lastWritten&&data.items.some(item=>!item.is_dir&&item.path===lastWritten)?lastWritten:undefined;
   let nextActive=opened.some(f=>f.path===focused)?focused!:(opened.some(f=>f.path===saved.activeFile)?saved.activeFile||'':opened[0]?.path||'');
   if(focused&&!opened.some(f=>f.path===focused))nextActive='';
   if(!nextActive){
    const first=focused||chooseWorkspaceSource([],data.items);
    if(first){try{
     const fresh=await requestJSON<DiskFile>(`/v1/workspace/file?workspace=${encodeURIComponent(data.root)}&path=${encodeURIComponent(first)}`);
     if(epoch!==generation.current)return;
     nextFiles=[...opened,{path:first,content:fresh.content,original:fresh.content,revision:fresh.revision}];nextActive=first;
    }catch{/*empty workspace*/}}
   }
   setFiles(nextFiles);filesRef.current=nextFiles;setActiveFile(nextActive);
   setHydrated(true);
  }catch(err){if(epoch===generation.current){message(`تعذّر فتح المشروع: ${errorText(err)}`,true);setHydrated(!!rootRef.current)}}finally{if(epoch===generation.current){opening.current=false;setLoading(false)}}
 },[setStoredWorkspace,message,refreshLog]);
 useEffect(()=>{if(open&&!opening.current&&workspaceInStore&&rootRef.current!==workspaceInStore)void openProject(workspaceInStore)},[open,workspaceInStore,openProject]);
 useEffect(()=>{if(!hydrated||!tree||persistenceRef.current!==tree.root)return;
  const handle=window.setTimeout(()=>{void requestJSON('/v1/studio/state',{method:'PUT',body:JSON.stringify({workspace:tree.root,state:{layout,tabs:files.map(f=>f.path),activeFile,activity,bottomTab:bottom}})}).catch(()=>{})},500);
  return()=>window.clearTimeout(handle);
 },[tree,hydrated,layout,files.map(f=>f.path).join('|'),activeFile,activity,bottom]);
 const openFile=useCallback(async(file:string)=>{
  if(!tree||opening.current)return;const exists=filesRef.current.find(f=>f.path===file);if(exists){setActiveFile(file);setEditorView('editor');return;}
  const epoch=generation.current;
  try{const data=await requestJSON<DiskFile>(`/v1/workspace/file?workspace=${encodeURIComponent(tree.root)}&path=${encodeURIComponent(file)}`);
    if(epoch!==generation.current)return;
    const next=addEditorFile(filesRef.current,{path:file,content:data.content,original:data.content,revision:data.revision});
    filesRef.current=next;setFiles(next);setActiveFile(file);setPreview(null);setSelection('');setEditorView('editor');
  }catch(err){message(`لا يمكن قراءة الملف: ${errorText(err)}`,true)}
 },[tree,files,message]);
 const openFinding=async(finding:SafetyFinding)=>{
  if(!tree)return;
  try{await openFile(finding.file);setEditorView('editor');setJumpTo({file:finding.file,line:finding.line})}
  catch(err){message(`تعذر فتح الملف: ${errorText(err)}`,true)}
 };
 const updateContent=useCallback((value:string)=>{setFiles(prev=>prev.map(f=>f.path===activeFile?{...f,content:value}:f));setPreview(null);if(previewSource?.path===activeFile)setPreviewSource(prev=>prev?{...prev,content:value}:prev)},[activeFile,previewSource?.path]);
 const openPreview=useCallback((content:string,path:string,label='المعاينة الحية')=>{setPreviewSource({content,path,label});setEditorView('preview')},[]);
 const closeFile=(file:string)=>{const f=files.find(x=>x.path===file);if(f&&(f.content!==f.original||f.disk)&&!window.confirm('الملف فيه تغييرات غير محفوظة. تقفله؟'))return;
  const rest=files.filter(x=>x.path!==file);setFiles(rest);if(activeFile===file)setActiveFile(rest.at(-1)?.path||'');setPreview(null)};
 const proposeSave=useCallback(async(content?:string,targetPath?:string)=>{if(!tree){message('افتح مجلد مشروع الأول علشان تراجع وتحفظ الكود.',true);return}
  const proposedPath=targetPath||active?.path||'';const proposedContent=content??active?.content;
  if(!proposedPath||proposedContent===undefined){message('حدد ملفًا داخل المشروع قبل مراجعة التعديل.',true);return}
  const baseline=filesRef.current.find(f=>f.path===proposedPath);
  if(baseline?.disk||baseline?.syncError){message('الملف اتغيّر خارج المحرر أو مش متاح. حدّثه وراجع التعارض الأول.',true);return}
  const epoch=generation.current;
  setLoading(true);try{const [data,safety]=await Promise.all([
    requestJSON<DiffPreview>('/v1/workspace/edit/preview',{method:'POST',body:JSON.stringify({workspace:tree.root,path:proposedPath,content:proposedContent,expected_revision:baseline?.revision})}),
    requestJSON<SafetyReport>('/v1/studio/monitor/draft',{method:'POST',body:JSON.stringify({path:proposedPath,content:proposedContent})})
   ]);
   if(epoch!==generation.current)return;
   setPreview(data);setPreviewContent(proposedContent);setPreviewSafety(safety);setMonitorDraft(safety);setMonitorSource('draft');setEditorView('diff');
   const severe=(safety.summary.critical||0)+(safety.summary.high||0);
   setBottom(severe?'security':'output');if(severe)setLayout(l=>({...l,showBottom:true}));
   message(severe?`مراجعة الأمان لقت ${severe} مؤشر خطير. راجع تبويب الأمان قبل الموافقة على الحفظ.`:'التعديل في وضع المعاينة فقط. راجع الفروقات ووافق للحفظ.');
  }catch(err){if(epoch===generation.current){message(`تعذّر تجهيز المعاينة: ${errorText(err)}`,true);void refreshProject()}}finally{if(epoch===generation.current)setLoading(false)}
 },[tree,active,message]);
 const applySave=useCallback(async()=>{if(!preview||saving.current)return;
  const serious=(previewSafety?.summary.critical||0)+(previewSafety?.summary.high||0);
  if(serious>0&&!window.confirm(`المراقب رصد ${serious} مؤشر خطر مرتفع أو حرج في الكود المقترح. هل أنت متأكد إنك راجعت التحذيرات وعايز تحفظ التعديل؟`))return;
  saving.current=true;setLoading(true);try{const result=await requestJSON<{saved:boolean;path:string;backup_id:string;workspace:string;revision:string}>('/v1/workspace/edit/apply',{method:'POST',body:JSON.stringify({approval_id:preview.approval_id,confirmed:true})});
   const savedContent=previewContent??files.find(f=>f.path===result.path)?.content??'';
   // Preserve typing made while the save request was in flight.
   setFiles(prev=>{const next={path:result.path,content:savedContent,original:savedContent,revision:result.revision};return prev.some(f=>f.path===result.path)?prev.map(f=>f.path===result.path?{...next,content:f.content===savedContent||f.content===f.original?savedContent:f.content}:f):prev.length<18?[...prev,next]:prev});setActiveFile(result.path);setEditorView('editor');
   setPreview(null);setPreviewContent(null);setPreviewSafety(null);setLastUndo(result.backup_id);message(`اتحفظ الملف: ${result.path} · اتعملت نسخة احتياطية. `);if(tree){void refreshLog(tree.root);void requestJSON<Tree>(`/v1/studio/tree?workspace=${encodeURIComponent(tree.root)}`).then(setTree).catch(()=>{})}
  }catch(err){message(`الحفظ لم يتم: ${errorText(err)}`,true);setPreview(null);setPreviewContent(null);setEditorView('editor')}
  finally{saving.current=false;setLoading(false);announceWorkspaceChange(rootRef.current)}
 },[preview,previewContent,previewSafety,files,tree,refreshLog,message]);
 const undo=async()=>{if(!lastUndo)return;try{await requestJSON('/v1/workspace/edit/undo',{method:'POST',body:JSON.stringify({approval_id:lastUndo,confirmed:true})});
   setLastUndo('');message('تم التراجع. جاري تحديث الملف المستعاد مع الاحتفاظ بأي مسودة غير محفوظة.');void refreshProject();
  }catch(e){message(errorText(e),true)}};
 const runSearch=useCallback(async()=>{if(!tree||search.trim().length<2)return;
  const epoch=generation.current;
  setLoading(true);try{const r=await requestJSON<{hits:Array<{file:string;line:number;text:string}>}>(`/v1/coding/search?workspace=${encodeURIComponent(tree.root)}&phrase=${encodeURIComponent(search.trim())}`);if(epoch!==generation.current)return;setResults(r.hits||[]);setActivity('search');message(`نتائج البحث: ${(r.hits||[]).length}`)}catch(e){if(epoch===generation.current)message(errorText(e),true)}finally{if(epoch===generation.current)setLoading(false)}
 },[tree,search,message]);
 const runDiagnostics=useCallback(async()=>{
  if(!tree)return;const epoch=generation.current;setLoading(true);
  try{const report=await requestJSON<NonNullable<typeof diagnostics>>(`/v1/coding/diagnostics?workspace=${encodeURIComponent(tree.root)}`);
   if(epoch!==generation.current)return;setDiagnostics(report);setBottom('problems');setLayout(l=>({...l,showBottom:true}));
  }catch(err){if(epoch===generation.current)message(errorText(err),true)}finally{if(epoch===generation.current)setLoading(false)}
 },[tree,message]);
 const runUiAudit=useCallback(async()=>{
  const root=tree?.root;if(!root||uiAuditBusy)return;
  setUiAuditBusy(true);setUiAuditError('');setEditorView('work');
  try{const report=await requestJSON<UiAudit>(`/v1/studio/ui-audit?workspace=${encodeURIComponent(root)}`);
   if(root===rootRef.current)setUiAudit(report);
  }catch(err){if(root===rootRef.current)setUiAuditError(`تعذر فحص الواجهة: ${errorText(err)}`)}
  finally{setUiAuditBusy(false)}
 },[tree,uiAuditBusy]);
 const resolveDisk=(keepDraft:boolean)=>{
  if(!active?.disk)return;const disk=active.disk;
  if(!keepDraft&&!window.confirm('استبدال التعديلات غير المحفوظة بنسخة القرص؟'))return;
  if(!keepDraft&&!disk.exists){setFiles(prev=>prev.filter(f=>f.path!==active.path));setActiveFile('');return}
  setFiles(prev=>prev.map(f=>f.path===active.path?{path:f.path,content:keepDraft?f.content:disk.content,original:disk.content,revision:disk.revision}:f));
  setPreview(null);setPreviewContent(null);message(keepDraft?'احتفظت بمسودتك. اضغط معاينة الحفظ لمراجعة الفرق مع أحدث نسخة على القرص.':'تم تحميل نسخة القرص.');
 };
 const stopAI=useCallback(()=>{if(handoffMessage?.isStreaming)stopGeneration()},[handoffMessage?.isStreaming]);
 const planAgent=()=>sendToMainChat(tree
  ?'افحص المشروع الحالي وافهم المطلوب، وجهّز خطة تنفيذ حقيقية بمقاييس قبول واختبارات، ثم نفّذ خطوة بخطوة بعد موافقتي.'
  :'عايز أبني برنامج جديد في مساحة العمل. اسألني عن الفكرة لو الهدف مش واضح، ثم حدد المتطلبات وخطة التنفيذ والاختبارات.');
 const continueAgent=()=>{if(!mission)return;sendToMainChat(`${mission.goal}\nمتابعة المستخدم: كمّل من آخر خطوة مؤكدة، وافحص الملفات والاختبارات قبل أي تعديل. راجع التصميم والكيبورد وRTL والمقاسات المختلفة، واعرض الأدلة والمشاكل قبل إعلان اكتمال العمل.`)};
 const chooseFolder=async()=>{try{const r=await requestJSON<{path:string}>('/v1/studio/pick-folder',{method:'POST'});if(r.path){setPath(r.path);await openProject(r.path)}}catch(e){message(`اختيار المجلد التلقائي مش متاح: ${errorText(e)}. اكتب المسار يدويًا.`)}};
 const reset=()=>{setLayout(DEFAULT_LAYOUT);setActivity('explorer');setBottom('output');setCollapsed([]);setEditorView('editor')};
 function resize(field:'side'|'ai'|'bottom',e:ReactMouseEvent<HTMLDivElement>){e.preventDefault();const x=e.clientX,y=e.clientY,initial=layout[field];
  const move=(ev:MouseEvent)=>{const delta=field==='bottom'?y-ev.clientY:field==='ai'?x-ev.clientX:ev.clientX-x;setLayout(prev=>({...prev,[field]:clamp(initial+delta,field==='bottom'?115:field==='side'?180:260,field==='bottom'?450:650)}))};
  const done=()=>{window.removeEventListener('mousemove',move);window.removeEventListener('mouseup',done)};window.addEventListener('mousemove',move);window.addEventListener('mouseup',done);
 }
 useEffect(()=>{if(!open)return;const key=(e:KeyboardEvent)=>{
  const cmd=e.ctrlKey||e.metaKey;
  if(cmd&&e.key.toLowerCase()==='p'){e.preventDefault();setPalette(true)}
  if(cmd&&e.key.toLowerCase()==='s'&&tree){e.preventDefault();if(active)void proposeSave()}
  if(cmd&&e.key.toLowerCase()==='g'){e.preventDefault();setPalette(true);setPaletteText(':')}
  if(e.key==='Escape'){setPalette(false);if(preview){setPreview(null);setPreviewContent(null);setEditorView('editor')}}
 };
 const external=()=>{setPalette(true);setPaletteText('')};window.addEventListener('keydown',key);window.addEventListener('barq-workspace-command',external);
 return()=>{window.removeEventListener('keydown',key);window.removeEventListener('barq-workspace-command',external)};
 },[open,tree,active,preview,proposeSave]);
 useEffect(()=>{if(palette)paletteInputRef.current?.focus()},[palette]);
 const visible=useMemo(()=>tree?.items.filter(entry=>{if(filter)return entry.path.toLowerCase().includes(filter.toLowerCase());
  return !entry.path.split('/').slice(0,-1).some((_,index,arr)=>collapsed.includes(arr.slice(0,index+1).join('/')))
 })||[],[tree,filter,collapsed]);
 const oldSection=legacy[activity];const paneStyle={gridTemplateColumns:layout.zen||editorView==='work'?'minmax(0,1fr)':`minmax(160px,${layout.side}px) minmax(0,1fr)`} as CSSProperties;
 if(!open)return null;
 if(twoPane)return <section className="barq-studio barq-two-pane flex h-full min-h-0 flex-col overflow-hidden bg-base"
     dir="rtl" aria-label="مساحة برمجة برق - الملفات والكود" data-studio-version="v2.41.21-two-pane-code" data-release-marker="v2.41.21-build-gated-ui" data-chat-mode="unified">
   <header className="barq-two-header" dir="rtl">
    <button className="studio-icon" onClick={onClose} title="العودة إلى المحادثة" aria-label="العودة إلى المحادثة"><MessageCircle size={19}/></button>
    <strong>مساحة العمل</strong><span className="barq-two-project" dir="ltr" title={tree?.root||''}>{tree?.root.split(/[\\/]/).at(-1)||'بدون مشروع'}</span>
    {mission&&<span className="barq-two-mission" title={mission.goal}>{mission.status==='done'?'اكتملت الخطوة':mission.status==='failed'?'تحتاج إصلاحًا':mission.status==='paused'?'متوقفة':'برق بيشتغل على المهمة'}</span>}
    {approval&&<button className="barq-two-action" onClick={reviewMission}>مراجعة الموافقة</button>}
    <button className="barq-two-action" onClick={()=>void refreshProject(true)} disabled={!tree||syncing} title="تحديث ملفات المشروع"><RotateCcw size={15}/> تحديث</button>
    <button className="barq-two-secondary" onClick={()=>setTwoPane(false)} title="إظهار أدوات GitHub والتشخيص والمراقبة">أدوات متقدمة</button>
   </header>
   <div className="barq-two-grid">
    <aside className="barq-two-files" dir="rtl" aria-label="ملفات المشروع">
     <div className="barq-two-section-title"><Folder size={17}/><strong>الملفات</strong><span>{tree?.items.filter(item=>!item.is_dir).length||0}</span></div>
     <div className="barq-two-folder">
      <input aria-label="مسار مجلد المشروع" dir="ltr" value={path} placeholder="C:\\Projects\\App" onChange={e=>setPath(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')void openProject(path)}}/>
      <button onClick={()=>void chooseFolder()} title="اختيار مشروع من الجهاز" aria-label="اختيار مشروع"><FolderOpen size={18}/></button>
      <button className="barq-two-action" disabled={!path.trim()||loading} onClick={()=>void openProject(path)}>فتح</button>
     </div>
     {tree?<>
       <input className="barq-two-filter" aria-label="فلترة الملفات" placeholder="ابحث في أسماء الملفات..." value={filter} onChange={e=>setFilter(e.target.value)}/>
       <div className="barq-two-tree" role="tree" dir="ltr">{visible.map(entry=>{
        const depth=entry.path.split('/').length-1;
        return <button type="button" role="treeitem" key={entry.path} title={entry.path} aria-expanded={entry.is_dir?!collapsed.includes(entry.path):undefined}
         className={`barq-two-file ${entry.path===activeFile?'selected':''}`} style={{paddingLeft:10+depth*14}}
         onClick={()=>entry.is_dir?setCollapsed(old=>old.includes(entry.path)?old.filter(x=>x!==entry.path):[...old,entry.path]):void openFile(entry.path)}>
         {entry.is_dir?(collapsed.includes(entry.path)?<ChevronRight size={14}/>:<ChevronDown size={14}/>):<FileCode2 size={14}/>}<span>{entry.name}</span>
        </button>})}</div>
       {tree.truncated&&<p className="barq-two-muted">تم تحديد عدد الملفات لحماية الأداء.</p>}
      </>:<div className="barq-two-empty-files"><FolderOpen size={30}/><p>اختار مجلد مشروعك، وهنا هتشوف ملفاته وترتيبها.</p>{recent.slice(0,4).map(item=><button key={item} dir="ltr" title={item} onClick={()=>void openProject(item)}>{item}</button>)}</div>}
    </aside>
    <main className="barq-two-code" dir="ltr" aria-label="الكود الجاري كتابته">
     <nav className="barq-two-code-tabs" dir="rtl" aria-label="عرض الكود">
      <button className={editorView==='live'?'active':''} onClick={()=>setEditorView('live')}><Code2 size={16}/> كتابة برق {aiLoading&&<span className="studio-live-dot"/>}</button>
      <button className={editorView==='editor'?'active':''} onClick={()=>setEditorView('editor')}><FileCode2 size={16}/> الملف المفتوح</button>
      {preview&&<button className={editorView==='diff'?'active':''} onClick={()=>setEditorView('diff')}><FileDiff size={16}/> مراجعة التعديل</button>}
      {(previewSource||active)&&<button className={editorView==='preview'?'active':''} onClick={()=>previewSource?setEditorView('preview'):active&&openPreview(active.content,active.path,'المعاينة')}><Monitor size={16}/> معاينة</button>}
      <button className="barq-two-chat" onClick={()=>sendToMainChat(tree?'كمّل تنفيذ مهمة البرمجة الحالية في المشروع المفتوح، واكتب الكود واعرض التقدم في مساحة العمل.':'عايز أبدأ مشروع برمجي جديد في مساحة العمل.')}><MessageCircle size={15}/> أمر لبرق</button>
     </nav>
     {editorView==='diff'&&preview?<div className="barq-two-diff" dir="rtl">
      <div className="barq-two-section-title"><FileDiff size={17}/><strong>مراجعة التعديلات قبل الحفظ</strong><span dir="ltr">{preview.path}</span></div>
      <pre dir="ltr">{preview.diff||'لا توجد اختلافات'}</pre>
      {!!((previewSafety?.summary.critical||0)+(previewSafety?.summary.high||0))&&<p role="alert">في تنبيهات أمان عالية في التعديل. راجعها قبل الموافقة.</p>}
      <div><Button variant="primary" disabled={loading} onClick={()=>void applySave()}>الموافقة والحفظ</Button><Button variant="secondary" onClick={()=>{setPreview(null);setPreviewContent(null);setEditorView('live')}}>إلغاء</Button></div>
     </div>:editorView==='preview'&&(previewSource||active)?<PreviewPanel path={previewSource?.path||active?.path||''} content={previewSource?.content||active?.content||''} title="معاينة البرنامج"/>:
     editorView==='live'?(liveDraft&&(!plannedCode||liveDraft.code||liveDraft.status==='streaming')?<AgentCodePanel draft={liveDraft} canReview={!!approval} onReview={reviewMission} onStop={stopAgentCode}/>:
       <LiveCodePanel answer={reply} streaming={aiLoading} proposed={plannedCode} target={codeTarget} onTarget={setCodeTarget} onReview={(content,target)=>void proposeSave(content,target)} onPreview={(content,target)=>openPreview(content,target,'معاينة الكود')} onOpenEditor={()=>setEditorView('editor')} onStop={stopAI}/>):
     active?<div className="barq-two-editor-wrap">
       <div className="studio-code-header"><span dir="ltr">{active.path}</span><button className="barq-two-action" disabled={loading||!dirty} onClick={()=>void proposeSave()}><Save size={15}/> مراجعة الحفظ</button></div>
       {active.disk&&<div className="barq-two-conflict" dir="rtl" role="alert">الملف اتغير على القرص. راجع التعارض قبل الحفظ.<button onClick={()=>resolveDisk(false)}>نسخة القرص</button><button onClick={()=>resolveDisk(true)}>مسودتي</button></div>}
       <textarea ref={editorTextRef} className="studio-code-editor" dir="ltr" spellCheck={false} aria-label="محرر كود المشروع" value={active.content} onChange={e=>updateContent(e.target.value)} onKeyDown={e=>{if(e.key==='Tab'){e.preventDefault();const el=e.currentTarget;const p=el.selectionStart;updateContent(active.content.slice(0,p)+'  '+active.content.slice(el.selectionEnd));requestAnimationFrame(()=>{el.selectionStart=el.selectionEnd=p+2})}}}/>
       {dirty&&<p className="barq-two-muted" dir="rtl"><ShieldCheck size={14}/> التغييرات مش هتتحفظ على القرص قبل مراجعتك.</p>}
     </div>:<div className="barq-two-code-empty" dir="rtl"><Code2 size={38}/><strong>اختار ملف علشان تشوف الكود</strong><p>أو افتح «كتابة برق» لمتابعة التوليد في الوقت الفعلي.</p><button className="barq-two-action" onClick={()=>setEditorView('live')}>عرض كتابة برق</button></div>}
     <div className="barq-two-status" role="status" dir="rtl">{editorView==='live'?(aiLoading?'● الكود بيتكتب الآن — مش محفوظ':liveDraft?'مسودة مولّدة — لازم مراجعة وحفظ':mission?.status==='done'?'المهمة انتهت — راجع الملفات المحفوظة':'الكود المعروض مش دليل إنه اتحفظ'):editorView==='diff'?'في انتظار الموافقة — لم يتم حفظ التعديل':dirty?'● فيه تغييرات غير محفوظة':mission?.status==='done'?'✓ المهمة انتهت — تحقق من نتائج الاختبارات':'✓ الملف محفوظ — اجتياز الاختبارات غير مؤكد'}</div>
     {output&&<div className="barq-two-status" role="status" dir="rtl">{output.length>180?output.slice(0,180)+'…':output}</div>}
    </main>
   </div>
 </section>;
 return <section className="barq-studio flex h-full min-h-0 flex-col overflow-hidden bg-base" dir={rtl?'rtl':'ltr'} aria-label="مساحة برمجة برق" data-studio-version="v2.41.21-work-center-ui-audit" data-release-marker="v2.41.21-build-gated-ui" data-chat-mode="unified">
  {!layout.zen&&<header className="studio-topbar flex shrink-0 items-center gap-2 px-3 py-2">
   <button type="button" className="studio-back-chat studio-icon" onClick={onClose} title={rtl?'الرجوع للمحادثة':'Back to chat'} aria-label={rtl?'الرجوع للمحادثة':'Back to chat'}><MessageCircle size={19}/></button>
   <div className="min-w-0 flex-1 studio-project-switcher"><div className="truncate text-sm font-semibold">{tree?.root.split(/[\\/]/).at(-1)||'BARQ Studio'}</div><select aria-label="تبديل المشروع" dir="ltr" value={tree?.root||''} onChange={e=>{if(e.target.value)void openProject(e.target.value)}} title={tree?.root||'المشاريع الأخيرة'}><option value="">{tree?'المشاريع الأخيرة':'اختر مشروعًا'}</option>{recent.map(item=><option key={item} value={item}>{item}</option>)}</select></div>
   {git?.available&&<span dir="ltr" className="hidden max-w-[180px] truncate text-xs text-secondary md:inline"><GitBranch size={13} className="inline"/> {git.branch}</span>}
   <button className="studio-icon studio-work-top" title="مركز متابعة المهام" aria-label="متابعة المهمة" onClick={()=>setEditorView('work')}><LayoutGrid size={16}/><span>متابعة المهمة</span></button>
   <button className="studio-icon studio-safety-top" title="مراقب أخطاء وأمان الكود" onClick={showMonitor}><ShieldAlert size={16}/><span>مراقب الكود</span>{monitorCount>0&&<span className="studio-safety-badge">{monitorCount}</span>}</button>
   <button className="studio-icon studio-top-primary" title="فحص المشروع" disabled={!tree||loading} onClick={()=>void runDiagnostics()}><Play size={16}/> <span>فحص</span></button>
   <button className="studio-icon" title="تحديث الملفات من القرص" aria-label="تحديث الملفات من القرص" disabled={!tree||syncing||loading} onClick={()=>void refreshProject()}><RotateCcw size={18} className={syncing?'animate-spin':''}/></button>
   <button className="studio-icon" title="افتح لوحة الأوامر Ctrl+P" onClick={()=>setPalette(true)}><Command size={18}/></button>
   <button className="studio-icon" title="تخطيط هادئ" onClick={()=>setLayout(l=>({...l,zen:!l.zen}))}><Maximize2 size={18}/></button>
   <button className="studio-icon" title="إعادة ضبط التخطيط" onClick={reset}><Settings2 size={18}/></button><button className="studio-icon" title="عرض الملفات والكود فقط" onClick={()=>setTwoPane(true)}><Columns2 size={17}/></button>
   <span className="hidden text-xs text-secondary xl:inline" dir="ltr">{localOnly?'Ollama':selectedModel}</span>
  </header>}
  {mission&&<div className="barq-work-strip" dir="rtl" role="status">
    <span className="barq-work-strip-dot"/><strong className="truncate" title={mission.goal}>{mission.goal.length>90?mission.goal.slice(0,90)+"…":mission.goal}</strong>
    <span className="barq-work-strip-state">{mission.status==='plan_ready'?'موافقة مطلوبة':mission.status==='paused'?'متوقفة':mission.status==='failed'?'تحتاج إصلاحًا':mission.status==='done'?'الخطوة انتهت':'متابعة المهمة'}</span>
    <button type="button" onClick={()=>setEditorView('work')}>تفاصيل المهمة</button>
    {approval&&<button type="button" className="barq-work-strip-review" onClick={reviewMission}>مراجعة الموافقة</button>}
   </div>}
  <div className="flex min-h-0 flex-1" dir="ltr">
   {!layout.zen&&<nav className="studio-rail" aria-label="أنشطة مساحة العمل" dir="rtl">{activityGroups.map((group,index)=><div className="studio-rail-group" key={index}>{group.map(id=>{const item=activityItems.find(entry=>entry[0]===id);if(!item)return null;const [,label,Icon]=item;return <button key={id} type="button" aria-label={label} aria-current={activity===id?'page':undefined} title={label} className={`studio-rail-button ${activity===id?'active':''}`} onClick={()=>{setActivity(id);if(id==='guardian'){setEditorView('guardian');setLayout(l=>({...l,showAI:false,showBottom:false}))}}}><Icon size={18} strokeWidth={1.75}/></button>})}</div>)}</nav>}
   <div className="studio-panes grid min-h-0 min-w-0 flex-1 overflow-hidden" style={paneStyle}>
    {!layout.zen&&editorView!=='work'&&<aside dir="rtl" className="studio-side relative min-h-0 overflow-auto">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-stroke bg-surface px-3 py-2 text-sm font-semibold"><span>{activityItems.find(x=>x[0]===activity)?.[1]}</span><button title="الرجوع للشات الأساسي" onClick={onClose}><MessageCircle size={17}/></button></div>
      {activity==='explorer'&&<>
       <div className="space-y-2 p-3"><div className="flex gap-1"><input value={path} onChange={e=>setPath(e.target.value.replaceAll('\\\\','\\'))} dir="ltr" aria-label="مسار المشروع" placeholder="C:\\Projects\\MyApp" className="ui-input min-w-0 flex-1 text-xs"/><button onClick={()=>void chooseFolder()} title="اختيار مجلد" className="studio-icon"><FolderOpen size={18}/></button></div>
        <Button variant="primary" size="sm" disabled={!path.trim()||loading} onClick={()=>void openProject(path)} className="w-full">فتح المشروع</Button>
        {tree?.stack.length? <p className="text-xs text-secondary">{tree.stack.join(' · ')}</p>:null}
        {tree&&<input value={filter} onChange={e=>setFilter(e.target.value)} placeholder="فلترة الملفات" aria-label="فلترة الملفات" className="ui-input text-xs"/>}
       </div>
       <div className="studio-tree" role="tree" aria-label="شجرة ملفات المشروع" dir="ltr">{loading&&!tree&&<div className="space-y-2 p-3" role="status" aria-label="جاري فتح المشروع"><div className="shimmer h-7 rounded-md"/><div className="shimmer h-7 rounded-md"/><div className="shimmer h-7 rounded-md"/></div>}{visible.map(entry=>{const depth=entry.path.split('/').length-1;const expanded=!collapsed.includes(entry.path);
        return <button key={entry.path} role="treeitem" aria-expanded={entry.is_dir?expanded:undefined} className={`studio-tree-row ${activeFile===entry.path?'active':''}`} title={entry.path} style={{paddingLeft:8+depth*14}} onClick={()=>entry.is_dir?setCollapsed(prev=>expanded?[...prev,entry.path]:prev.filter(x=>x!==entry.path)):void openFile(entry.path)}>
          {entry.is_dir?(expanded?<ChevronDown size={14}/>:<ChevronRight size={14}/>):<FileCode2 size={14}/>}<span className="truncate">{entry.name}</span>
        </button>})}{tree?.truncated&&<p className="p-3 text-xs text-secondary">الشجرة محدودة لحماية الأداء؛ أضف مسارًا أدق.</p>}</div>
      </>}
      {activity==='search'&&<div className="space-y-2 p-3"><input aria-label="بحث بالكود" placeholder="ابحث في ملفات المشروع" value={search} onChange={e=>setSearch(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')void runSearch()}} className="ui-input text-sm"/><Button size="sm" variant="primary" disabled={!tree||loading||search.trim().length<2} onClick={()=>void runSearch()}>بحث</Button><div className="space-y-1">{results.map((r,i)=><button key={`${r.file}-${r.line}-${i}`} className="studio-search-result" onClick={()=>{void openFile(r.file).then(()=>setJumpTo({file:r.file,line:r.line}))}}><span dir="ltr" className="block truncate text-xs font-semibold">{r.file}:{r.line}</span><span dir="ltr" className="block truncate text-[11px] text-secondary">{r.text}</span></button>)}</div></div>}
      {activity==='git'&&<div className="space-y-2 p-3"><Button size="sm" variant="secondary" onClick={()=>{if (!tree) return; void requestJSON<Git>(`/v1/studio/git?workspace=${encodeURIComponent(tree.root)}`).then(setGit).catch(error => message(errorText(error), true));}}>تحديث الحالة</Button><p dir="ltr" className="text-xs text-secondary">{git?.branch||'لا يوجد مستودع Git'}</p>{git?.changes.map((c,i)=><p key={i} dir="ltr" className="truncate rounded bg-elevated p-2 text-xs">{c}</p>)}<p className="text-xs text-secondary">للاستعراض والـ Commit وعمليات GitHub افتح نشاط GitHub.</p></div>}
      {activity==='commands'&&<div className="space-y-2 p-3"><p className="text-sm text-secondary">مساعد البرمجة من الشات الأساسي فقط — اختار أمر علشان يرجعك للشات.</p><Button size="sm" variant="secondary" onClick={planAgent}>جهّز خطة تنفيذ بموافقة من الشات</Button>{['/explain','/fix','/refactor','/test','/docs','/commit'].map(cmd=><button key={cmd} className="studio-search-result" dir="ltr" onClick={()=>sendToMainChat(`${cmd} ${activeFile||''} في المشروع ${tree?.root||workspace}`)}>{cmd}</button>)}<p className="text-xs text-secondary">تنفيذ أوامر النظام يحتاج موافقة من لوحة الأدوات. لا يتم تشغيل Shell تلقائيًا.</p></div>}
      {activity==='guardian'&&<div className="guardian-side-info"><ShieldCheck size={22}/><strong>BARQ Guardian</strong><p>فحوصات محلية، تفاصيل واضحة، وأي إصلاح لازم توافق عليه.</p><Button variant="secondary" size="sm" onClick={showMonitor}>افتح مركز المراقبة</Button></div>}
      {activity==='run'&&<div className="space-y-2 p-3"><Button variant="secondary" disabled={!tree||loading} onClick={()=>void runDiagnostics()}>فحص المشروع</Button><p className="text-xs text-secondary">تشغيل الاختبارات والبناء متاح من أدوات المشروع بعد الموافقة.</p></div>}
      {oldSection&&<div className="text-xs"><WorkspaceTools open inside onClose={onClose} activeSection={oldSection} workspacePath={tree?.root||workspace} /></div>}
    <div className="studio-resize-side" role="separator" title="اسحب لتغيير العرض" onMouseDown={e=>resize('side',e)}/></aside>}
    <main className="studio-editor min-h-0 min-w-0 overflow-hidden" dir="ltr">
      {editorView==='work'?<WorkCenter mission={mission} projectName={tree?.root||''} workspaceReady={!!tree} hasPendingApproval={!!approval} audit={uiAudit} auditBusy={uiAuditBusy} auditError={uiAuditError} onAudit={()=>void runUiAudit()} onChat={reviewMission} onPlan={planAgent} onPickFolder={()=>void chooseFolder()} onOpenFile={file=>void openFile(file)} onEditor={()=>setEditorView('editor')} onDiagnostics={()=>void runDiagnostics()} onContinue={continueAgent}/>:!tree&&editorView!=='live'&&editorView!=='guardian'?<div className="studio-empty" dir="rtl"><LayoutGrid size={40} className="text-accent"/><h2 className="text-xl font-bold">مساحة برمجة برق</h2><p className="text-sm text-secondary">الشات الأساسي هو مركز الأوامر. هنا بتشوف الملفات ونتائج التنفيذ وبتراجع أي تعديل قبل الحفظ.</p><div className="flex flex-wrap justify-center gap-2"><Button variant="primary" onClick={()=>void chooseFolder()} icon={<FolderOpen size={16}/>}>فتح مجلد مشروع</Button><Button variant="secondary" onClick={()=>sendToMainChat('ابنيلي برنامج جديد في مساحة العمل')} icon={<Code2 size={16}/>}>اطلب برنامج من الشات</Button></div>{recent.length>0&&<div className="studio-recent"><strong>المشاريع الأخيرة</strong>{recent.slice(0,5).map(item=><button key={item} dir="ltr" onClick={()=>void openProject(item)} title={item}>{item}</button>)}</div>}</div>:
      <>
       <div className="studio-editor-modes" dir="rtl">
        {/* The 'work' view is rendered by the first ternary branch above. The
            button remains available to navigate back, but cannot be active
            in this branch. Avoid TS2367's impossible-state comparison. */}
        <button type="button" onClick={()=>setEditorView('work')}><LayoutGrid size={15}/> متابعة المهمة</button>
        <button type="button" className={editorView==='editor'?'active':''} onClick={()=>setEditorView('editor')}><FileCode2 size={15}/> المحرر</button>
        <button type="button" className={editorView==='live'?'active':''} onClick={()=>setEditorView('live')}><Code2 size={15}/> كتابة برق {aiLoading&&<span className="studio-live-dot"/>}</button>
        <button type="button" className={editorView==='guardian'?'active':''} onClick={showMonitor}><ShieldCheck size={15}/> مراقب المشروع</button>
        <button type="button" className={editorView==='preview'?'active':''} disabled={!previewSource&&!active} onClick={()=>previewSource?setEditorView('preview'):active&&openPreview(active.content,active.path,'الشكل النهائي')}><Monitor size={15}/> المعاينة</button>
        {active&&<button type="button" className={editorView==='split'?'active':''} onClick={()=>setEditorView('split')}><Columns2 size={15}/> تقسيم</button>}
        {preview&&<button type="button" className={editorView==='diff'?'active':''} onClick={()=>setEditorView('diff')}><FileDiff size={15}/> مقارنة التعديل</button>}
       </div>
       {editorView==='guardian'?<GuardianDashboard workspace={tree?.root||''} onBack={()=>setEditorView('editor')} onFix={f=>sendToMainChat(`راجع ${f.title_ar} في ${f.file} عند السطر ${f.line}. جهّز إصلاحًا للموافقة وبعدها اختبره.`)} onOpen={f=>{void openFile(f.file).then(()=>{setEditorView('editor');setJumpTo({file:f.file,line:f.line})})}} onPlan={()=>sendToMainChat('افحص المشروع وحدد المشاكل وجهّز خطوات إصلاح وتنفيذ واختبارات للموافقة')} onRestore={(id,path)=>{if(!window.confirm(`ترجع التعديل السابق للملف ${path}؟ ممكن يتم الرفض لو الملف اتغير بعد الحفظ.`))return;void requestJSON('/v1/workspace/edit/undo',{method:'POST',body:JSON.stringify({approval_id:id,confirmed:true})}).then(()=>{message('تمت الاستعادة. جاري تحديث الملفات مع الحفاظ على المسودات.');void refreshProject()}).catch(e=>message(errorText(e),true))}}/>:
       editorView==='live'?(liveDraft&&(!plannedCode||liveDraft.code||liveDraft.status==='streaming')?<AgentCodePanel draft={liveDraft} canReview={!!approval} onReview={reviewMission} onStop={stopAgentCode}/>:<LiveCodePanel answer={reply} streaming={aiLoading} proposed={plannedCode} target={codeTarget} onTarget={setCodeTarget} onReview={(content,path)=>void proposeSave(content,path)} onPreview={(content,path)=>openPreview(content,path,'شكل الكود المقترح')} onOpenEditor={()=>setEditorView('editor')} onStop={stopAI}/>):
       editorView==='preview'?(<PreviewPanel path={previewSource?.path||active?.path||''} content={previewSource?.content||active?.content||''} title={previewSource?.label||'الشكل النهائي'}/>):
       editorView==='split'&&active?<div className="studio-split-view" dir="ltr"><section className="studio-split-editor"><div className="studio-code-header"><span dir="ltr" className="truncate">{active.path}</span><span className="ms-auto" dir="rtl">ملف المشروع</span></div><textarea dir="ltr" className="studio-code-editor" aria-label="المحرر المقسم" spellCheck={false} value={active.content} onChange={e=>updateContent(e.target.value)} onSelect={e=>{const el=e.currentTarget;setSelection(el.value.slice(el.selectionStart,el.selectionEnd))}}/></section><div className="studio-split-preview"><PreviewPanel path={previewSource?.path||active.path} content={previewSource?.content||active.content} title="المعاينة الجانبية"/></div></div>:
       editorView==='diff'&&preview?<div className="studio-diff-full" dir="rtl"><div className="studio-diff-title"><strong>مراجعة قبل تطبيق التعديل</strong><span dir="ltr">{preview.path}</span></div>{!!((previewSafety?.summary.critical||0)+(previewSafety?.summary.high||0))&&<div className="studio-critical-notice"><ShieldAlert size={17}/> المراقب رصد مخاطر في الكود المقترح. راجع تبويب الأمان قبل ما توافق على الحفظ. <button onClick={showMonitor}>عرض التحذيرات</button></div>}<div className="studio-diff-code" dir="ltr">{preview.diff.split('\n').map((line,index)=><div key={index} className={line.startsWith('+')?'add':line.startsWith('-')?'remove':line.startsWith('@@')?'hunk':''}>{line||' '}</div>)}</div><div className="studio-diff-actions"><Button variant="primary" disabled={loading} onClick={()=>void applySave()} icon={<Check size={15}/>}>الموافقة والحفظ</Button><Button variant="secondary" onClick={()=>{setPreview(null);setPreviewContent(null);setEditorView('live')}}>رفض</Button></div></div>:
       <><div className="studio-tabs">{files.map(f=><div className={`studio-tab ${f.path===activeFile?'active':''}`} key={f.path}>
         <button title={f.path} onClick={()=>setActiveFile(f.path)} className="min-w-0 flex-1 truncate text-start"><span dir="ltr">{titleOf(f.path)}</span>{f.content!==f.original&&<span className="ms-1 text-warning">●</span>}</button>
         <button aria-label={`إغلاق ${f.path}`} className="studio-tab-close" onClick={()=>closeFile(f.path)}><X size={13}/></button></div>)}
        {active&&<button title="حفظ بعد مراجعة التغييرات" className="studio-icon ms-auto" disabled={!dirty||loading} onClick={()=>void proposeSave()}><Save size={17}/></button>}
      </div>
      {active?<div className="studio-code-wrap">
       {(active.disk||active.syncError)&&<div className="border-b border-warning bg-surface p-3 text-sm" dir="rtl" role="alert">
        <p>{active.syncError|| (active.disk?.exists?'الملف اتغير على القرص. مسودتك محفوظة في المحرر؛ راجع النسختين قبل الحفظ.':'الملف اتحذف من القرص. محتوى المحرر لسه موجود.')}</p>
        {active.disk&&<div className="mt-2 flex gap-2"><Button size="sm" variant="secondary" onClick={()=>resolveDisk(false)}>استخدام نسخة القرص</Button><Button size="sm" variant="secondary" onClick={()=>resolveDisk(true)}>احتفظ بمسودتي للمراجعة</Button></div>}
        {active.disk&&<details className="mt-2"><summary>عرض نسخة القرص للمقارنة</summary><pre className="max-h-40 overflow-auto whitespace-pre-wrap" dir="ltr">{active.disk.content||'ملف فارغ أو محذوف'}</pre></details>}
       </div>}
       <div className="studio-code-header"><span dir="ltr" className="truncate">{active.path}</span><div className="ms-auto flex gap-1"><button title="شوف الشكل النهائي" className="studio-icon" onClick={()=>openPreview(active.content,active.path,'الشكل النهائي')}><Monitor size={17}/></button><button title="شرح الملف" className="studio-icon" onClick={()=>sendToMainChat(`راجع الملف ${active.path} في المشروع، واقترح التحسينات للموافقة`)}><Bot size={17}/></button><button title="معاينة الحفظ" className="studio-icon" disabled={!dirty} onClick={()=>void proposeSave()}><FileDiff size={17}/></button></div></div>
       <textarea ref={editorTextRef} dir="ltr" className="studio-code-editor" spellCheck={false} aria-label="محرر الكود" value={active.content} onChange={e=>updateContent(e.target.value)} onClick={e=>{const el=e.currentTarget;const pos=el.selectionStart;const preceding=el.value.slice(0,pos);setLineInfo({line:preceding.split('\n').length,col:preceding.split('\n').at(-1)!.length+1});setSelection(el.value.slice(el.selectionStart,el.selectionEnd))}} onSelect={e=>{const el=e.currentTarget;const preceding=el.value.slice(0,el.selectionStart);setLineInfo({line:preceding.split('\n').length,col:preceding.split('\n').at(-1)!.length+1});setSelection(el.value.slice(el.selectionStart,el.selectionEnd))}} onKeyDown={e=>{if(e.key==='Tab'){e.preventDefault();const el=e.currentTarget;const p=el.selectionStart;updateContent(active.content.slice(0,p)+'  '+active.content.slice(el.selectionEnd));requestAnimationFrame(()=>{el.selectionStart=el.selectionEnd=p+2})}}}/>
       {dirty&&<div className="studio-unsaved" dir="rtl"><ShieldCheck size={16}/> تغييرات غير محفوظة — لازم معاينة وموافقة قبل الكتابة على القرص.</div>}
      </div>:<div className="studio-empty" dir="rtl"><Code2 size={40}/><p>اختار ملف من المستكشف علشان تبدأ، أو افتح تبويب «كتابة برق».</p></div>}</>} </>}
    </main>

   </div>
  </div>
  {!layout.zen&&<><div className="studio-bottom" style={{height:layout.showBottom?layout.bottom:38}} dir="rtl">
   {layout.showBottom&&<div className="studio-resize-bottom" role="separator" title="اسحب لتغيير ارتفاع اللوحة" onMouseDown={e=>resize('bottom',e)}/>}
   <div className="studio-bottom-tabs">{([['output','المخرجات'],['problems','المشاكل'],['operations','العمليات'],['tasks','المهام'],['terminal','الطرفية'],['security','الأمان']] as const).map(([id,label])=><button key={id} className={bottom===id?'active':''} onClick={()=>{setBottom(id);setLayout(l=>({...l,showBottom:true}));if(id==='operations'&&tree)void refreshLog(tree.root)}}>{label}</button>)}<button className="ms-auto" title={layout.showBottom?'إخفاء اللوحة':'إظهار اللوحة'} onClick={()=>setLayout(l=>({...l,showBottom:!l.showBottom}))}>{layout.showBottom?<PanelBottomClose size={17}/>:<PanelBottomOpen size={17}/>}</button></div>
   {layout.showBottom&&<div className="studio-bottom-body">
     {bottom==='output'&&(preview?<section className="space-y-2"><div className="flex flex-wrap items-center justify-between gap-2"><strong>مراجعة التغييرات · {preview.path}</strong><div className="flex gap-2"><Button variant="primary" size="sm" disabled={loading} onClick={()=>void applySave()} icon={<Check size={15}/>}>أوافق على الحفظ</Button><Button variant="secondary" size="sm" onClick={()=>{setPreview(null);setPreviewContent(null);setEditorView('editor')}}>رفض التعديل</Button></div></div><pre dir="ltr" className="studio-log">{preview.diff||'مفيش فرق بين النسختين.'}</pre></section>:<div className="space-y-2"><pre dir="auto" className="studio-log">{output||'مفيش عمليات لسه.'}</pre>{lastUndo&&<Button size="sm" variant="secondary" onClick={()=>void undo()} icon={<RotateCcw size={14}/>}>تراجع عن آخر حفظ</Button>}</div>)}
     {bottom==='operations'&&<div className="space-y-1">{timeline.length?timeline.map((op,i)=><div key={`${op.time}-${i}`} className="studio-timeline"><time>{new Date(op.time*1000).toLocaleString('ar-EG')}</time><span>{op.actor} · {op.type}</span><span dir="ltr" className="truncate">{op.details}</span><span>{op.status==='ok'?'✓':'!'}</span></div>):<p>مفيش تعديلات مسجلة على المشروع.</p>}</div>}
     {bottom==='problems'&&<div className="space-y-2">
      <div className="flex gap-2"><Button size="sm" variant="secondary" disabled={!tree||loading} onClick={()=>void runDiagnostics()}>تحديث الفحص</Button><button className="studio-chip studio-chip-action" onClick={showMonitor}>فحص الأمان · {monitorCount}</button></div>
      {diagnostics?<><p>فحص صياغة {diagnostics.python_files_checked} ملف Python · {diagnostics.syntax_errors.length} ملف به أخطاء · {diagnostics.test_files.length} ملف اختبارات مكتشف. الاختبارات لم تُشغّل بهذا الفحص.</p>
       {diagnostics.syntax_errors.map(issue=><div key={issue.file} className="rounded border border-stroke p-2"><button className="font-semibold text-accent" dir="ltr" onClick={()=>{void openFile(issue.file).then(()=>setJumpTo({file:issue.file,line:issue.line||1}))}}>{issue.file}:{issue.line||1}</button><pre dir="ltr" className="whitespace-pre-wrap text-xs">{issue.errors.join('\n')}</pre><button className="text-xs underline" onClick={()=>sendToMainChat(`أصلح الخطأ في ${issue.file} عند السطر ${issue.line||1}، ثم افحص التعديل واختبره. تفاصيل الفحص: ${issue.errors.join('; ')}`)}>جهّز إصلاحًا مع برق</button></div>)}
       {diagnostics.suggested_checks.map(check=><p key={check} dir="ltr" className="text-xs">{check}</p>)}
       <Button size="sm" variant="secondary" onClick={()=>sendToMainChat('راجع اختبارات المشروع وجهّز تشغيل الاختبارات المناسبة للموافقة، واعرض النتيجة الفعلية وأصلح أسباب الفشل.')}>اختبر المشروع مع برق</Button>
      </>:<p>شغّل فحص المشروع لعرض الملفات والمشاكل هنا.</p>}
     </div>}
     {bottom==='tasks'&&(mission?<div className="space-y-2"><strong>{mission.goal}</strong><p>{mission.phase==='planning_next'?'الخطوة خلصت، وبرق بيجهز التالية.':mission.phase==='saving'?'جاري حفظ التعديل الموافق عليه.':mission.phase==='executing'?'جاري تنفيذ الخطوة الموافق عليها.':mission.summary||'راجع حالة المهمة في المحادثة.'}</p><div className="flex gap-2"><Button size="sm" variant="secondary" onClick={reviewMission}>{approval?'مراجعة الخطوة الحالية':'فتح المحادثة'}</Button></div>{mission.evidence&&<details><summary>نتائج التنفيذ المسجلة</summary><pre dir="auto" className="studio-log whitespace-pre-wrap">{mission.evidence}</pre></details>}</div>:<p>لسه مفيش مهمة في المحادثة الحالية. اطلب تنفيذًا من الشات علشان تتابعه هنا.</p>)}
     {bottom==='security'&&<SafetyMonitor report={monitorReport} scanning={monitorBusy} projectScanning={projectScanBusy} onProjectScan={()=>void runSecurityProjectScan()} onFix={fixFinding} onOpen={f=>void openFinding(f)} workspace={!!tree} source={monitorSource} onSource={value=>setMonitorSource(value==='project'?'project':'draft')}/>}
     {bottom==='terminal'&&<div className="space-y-1"><Terminal size={17} className="inline"/><p>الطرفية التفاعلية بنظام PTY لسه قيد التطوير. أدوات المشروع الحالية لا تزال متاحة وتتطلب الموافقة قبل التنفيذ.</p></div>}
   </div>}
  </div>
  <footer className="studio-status" dir="ltr"><span>{git?.branch||'—'}</span><span>{fileLang(activeFile||'')}</span><span>Ln {lineInfo.line}, Col {lineInfo.col}</span><span className="ms-auto">{active?(dirty?'● غير محفوظ':'✓ محفوظ'):'لا يوجد ملف مفتوح'}</span><span>{loading?'جاري العمل…':'جاهز'}</span></footer></>}
  {layout.zen&&<button className="studio-zen-exit" onClick={()=>setLayout(l=>({...l,zen:false}))}>الخروج من وضع التركيز</button>}
  {palette&&<div className="studio-palette-overlay" role="presentation" onMouseDown={()=>setPalette(false)}><div className="studio-palette" role="dialog" aria-label="الانتقال السريع" onMouseDown={e=>e.stopPropagation()} dir="rtl"><input ref={paletteInputRef} className="ui-input" value={paletteText} onChange={e=>setPaletteText(e.target.value)} placeholder="اسم ملف أو أمر..." onKeyDown={e=>{if(e.key==='Enter'){const matching=tree?.items.find(item=>!item.is_dir&&item.path.toLowerCase().includes(paletteText.toLowerCase()));if(matching){void openFile(matching.path);setPalette(false)}}}}/>
    <div className="max-h-72 overflow-auto">{tree?.items.filter(i=>!i.is_dir&&i.path.toLowerCase().includes(paletteText.toLowerCase().replace(/^:/,''))).slice(0,30).map(i=><button key={i.path} dir="ltr" className="studio-search-result" onClick={()=>{void openFile(i.path);setPalette(false)}}>{i.path}</button>)}<button className="studio-search-result" onClick={()=>{reset();setPalette(false)}}>إعادة ضبط التخطيط</button><button className="studio-search-result" onClick={()=>{setLayout(l=>({...l,zen:!l.zen}));setPalette(false)}}>وضع التركيز</button></div>
    </div></div>}
 </section>;
}

