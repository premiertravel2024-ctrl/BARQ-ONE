export type DiskFile={path:string;content:string;revision:string;exists:boolean};
export type EditorFile={path:string;content:string;original:string;revision?:string;disk?:DiskFile;syncError?:string};
export type FileSnapshot=DiskFile|{path:string;error:string};

/** Merge against the latest editor state, never against the state at request start. */
export function reconcileFiles(files:EditorFile[],snapshots:FileSnapshot[]):EditorFile[]{
 const byPath=new Map(snapshots.map(file=>[file.path,file]));
 return files.map(file=>{
  const next=byPath.get(file.path);if(!next)return file;
  if('error' in next)return {...file,syncError:next.error};
  if(next.revision===file.revision)return {...file,disk:undefined,syncError:undefined};
  if(next.exists&&file.content===file.original)return {path:file.path,content:next.content,original:next.content,revision:next.revision};
  // Dirty/deleted files stay in memory until the user resolves the difference.
  return {...file,disk:next,syncError:undefined};
 });
}

/** At capacity only a clean, available tab can be replaced. Never evict drafts. */
export function addEditorFile(files:EditorFile[],file:EditorFile):EditorFile[]{
 if(files.some(item=>item.path===file.path))return files;
 if(files.length<18)return [...files,file];
 const clean=files.findIndex(item=>item.content===item.original&&!item.disk&&!item.syncError);
 if(clean<0)throw new Error('كل التبويبات فيها تعديلات أو تعارضات. احفظ أو اقفل ملفًا قبل فتح ملف جديد.');
 return [...files.slice(0,clean),...files.slice(clean+1),file];
}

export function announceWorkspaceChange(workspace?:string,path?:string){
 if(workspace&&typeof window!=='undefined')window.dispatchEvent(new CustomEvent('barq-workspace-changed',{detail:{workspace,path}}));
}

export function announceToolOutput(workspace:string|undefined,results:Array<{tool:string;success:boolean;result?:string;error?:string}>|undefined){
 if(!workspace||!results?.length||typeof window==='undefined')return;
 const lines=results.map(item=>{
  let details=item.error||'';
  if(item.result){try{const value=JSON.parse(item.result);details=[value.stdout,value.stderr,value.log,Array.isArray(value.artifacts)?value.artifacts.join('\n'):'',value.path,value.project_path,typeof value.exit_code==='number'?`exit ${value.exit_code}`:''].filter(Boolean).join('\n')}catch{details=item.result.slice(0,2000)}}
  return `${item.success?'✓':'×'} ${item.tool}\n${details}`;
 });
 window.dispatchEvent(new CustomEvent('barq-tool-output',{detail:{workspace,text:lines.join('\n\n')}}));
}
