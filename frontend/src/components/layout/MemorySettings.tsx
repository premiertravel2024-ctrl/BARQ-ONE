import {useCallback,useEffect,useState} from 'react';
import {BookOpen,Plus,Search,Trash2} from 'lucide-react';
import {requestJSON} from '../../lib/backend';
import {useApp} from '../../store';
import {Button} from '../ui/Button';

type Note={id:string;project:string;text:string;created:number};

export function MemorySettings(){
 const ar=useApp(s=>s.language)==='ar',L=(a:string,b:string)=>ar?a:b;
 const [notes,setNotes]=useState<Note[]>([]),[project,setProject]=useState('BARQ');
 const [content,setContent]=useState(''),[query,setQuery]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const refresh=useCallback(async(q='')=>{try{const result=await requestJSON<{notes:Note[]}>(`/v1/memory/notes?query=${encodeURIComponent(q)}&limit=40`);setNotes(result.notes)}catch(e){setError(String(e))}},[]);
 useEffect(()=>{void refresh()},[refresh]);
 async function save(){setBusy(true);setError('');try{await requestJSON('/v1/memory/notes',{method:'POST',body:JSON.stringify({project,text:content})});setContent('');await refresh(query)}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}}
 async function remove(id:string){if(!window.confirm(L('حذف المعلومة دي من ذاكرة برق المحلية؟','Delete this local note?')))return;
  setBusy(true);setError('');try{await requestJSON(`/v1/memory/notes/${id}`,{method:'DELETE'});await refresh(query)}catch(e){setError(String(e))}finally{setBusy(false)}}
 return <section className="barq-settings-card space-y-3">
   <div className="flex items-center gap-2"><BookOpen size={18}/><h3 className="text-sm font-semibold">{L('ذاكرة برق الاختيارية','Optional BARQ memory')}</h3></div>
   <p className="text-xs text-secondary">{L('اللي تكتبه هنا بس هو اللي بيتحفظ. الملاحظات بتفضل على جهازك وما بتتبعتش للنماذج أوتوماتيك. ما تخزنش كلمات سر أو بيانات حساسة.','Only notes you enter are saved. They stay on your PC and are not automatically shared with models. Never store secrets.')}</p>
   <label className="block text-xs">{L('المشروع','Project')}<input className="ui-input mt-1 w-full" maxLength={80} value={project} onChange={e=>setProject(e.target.value)}/></label>
   <label className="block text-xs">{L('معلومة عايز برق يحتفظ بيها','Note to remember')}<textarea className="ui-input mt-1 w-full" maxLength={1000} rows={3} value={content} onChange={e=>setContent(e.target.value)}/></label>
   <Button variant="primary" icon={<Plus size={15}/>} size="sm" disabled={busy||!project.trim()||content.trim().length<3} onClick={()=>void save()}>{L('حفظ محلي','Save locally')}</Button>
   <div className="flex items-center gap-2"><Search size={15} className="text-secondary"/><input className="ui-input w-full" value={query} maxLength={100} placeholder={L('ابحث في الملاحظات','Search notes')} onChange={e=>{setQuery(e.target.value);void refresh(e.target.value)}}/></div>
   <div className="max-h-80 space-y-2 overflow-auto" aria-label={L('الملاحظات المحفوظة','Saved notes')}>{notes.map(note=><div className="flex items-start justify-between gap-2 rounded-lg border border-stroke bg-elevated p-3" key={note.id}><div className="min-w-0"><p className="text-xs font-semibold">{note.project}</p><p className="whitespace-pre-wrap break-words text-sm text-secondary">{note.text}</p></div><Button variant="ghost" size="sm" disabled={busy} icon={<Trash2 size={15}/>} aria-label={L('حذف الملاحظة','Delete note')} onClick={()=>void remove(note.id)}/></div>)}</div>
   {error&&<p role="alert" className="rounded-md border border-danger p-2 text-xs text-danger">{error}</p>}
  </section>
}
