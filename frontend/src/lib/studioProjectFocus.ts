import type {AgentTask} from '../store';

type Entry = {path:string;is_dir:boolean};
const source = /\.(?:py|tsx?|jsx?|html|css|json|rs|go|java|cs|vue|svelte|yaml|yml)$/i;
/** Prefer newly created real source; never open secrets or folders. */
export function chooseWorkspaceSource(before:Entry[], after:Entry[], suggested?:string):string{
 const old=new Set(before.filter(e=>!e.is_dir).map(e=>e.path));
 const candidates=after.filter(e=>!e.is_dir&&source.test(e.path)&&!/(?:^|\/)(?:\.env[^/]*|secrets?[^/]*)$/i.test(e.path));
 if(suggested&&candidates.some(e=>e.path===suggested))return suggested;
 const newer=candidates.filter(e=>!old.has(e.path));
 const score=(name:string)=>/\/(?:main|app|index|App)\.(?:py|tsx?|jsx?|html)$/.test('/'+name)?0:/\.(?:py|tsx?|jsx?|html)$/.test(name)?1:2;
 return (newer.length?newer:candidates).sort((a,b)=>score(a.path)-score(b.path)||a.path.localeCompare(b.path))[0]?.path||'';
}
export type ApprovedCode = {path:string;content:string};
/** Read-only draft of real agent output. Do not manufacture typed source text. */
export function pendingSource(task?:AgentTask):ApprovedCode|null{
 if(task?.status!=='plan_ready')return null;
 const step=task.plan?.plan?.steps.find(step=>step.tool==='workspace_edit');
 const path=step?.args?.path||task.proposedCode?.path;
 const content=step?.args?.content||task.proposedCode?.content;
 return typeof path==='string'&&typeof content==='string'&&content.length>0&&content.length<=250000
  ? {path,content}:null;
}
