import {useEffect,useMemo,useState,type FormEvent} from 'react';
import {BookOpen,Database,RefreshCw,Settings2,Sparkles,Search,Layers,ArrowUp,ArrowDown,EyeOff,CheckSquare} from 'lucide-react';
import {requestJSON} from '../lib/backend';
import {EditableCover} from './EditableCover';

type Book={
 id:string;title:string;source_title:string;folder_name:string;cover_id:string|null;
 published:number;hidden:number;active:number;series_id:string|null;issue_number:number|null;
 position:number;review_reason:string;manual_series:number;manual_issue:number;
};
type Series={id:string;title:string;description:string;genre:string;position:number;source_key:string|null};
type Snapshot={books:Book[];series:Series[]};
type Stats={count:number;grouped:number;review:number;series:number;database:string;automatic:boolean;persistent:boolean;db_bytes:number;custom_covers:number;reading_records:number;last_saved_at:string|null;journal_mode:string};
type Report={books:number;series:number;assigned:number;numbered:number;review:number;new_series:number;preview:boolean};
type Filter='all'|'review'|'ungrouped'|'hidden'|'series';
const base='/v1/reading/library';

export function LocalLibraryManager({ar}:{ar:boolean}){
 const [data,setData]=useState<Snapshot>({books:[],series:[]});
 const [stats,setStats]=useState<Stats>();
 const [open,setOpen]=useState(false);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const [report,setReport]=useState<Report>();
 const [query,setQuery]=useState('');
 const [tab,setTab]=useState<Filter>('all');
 const [selected,setSelected]=useState<string[]>([]);
 const [dragging,setDragging]=useState<string|null>(null);
 const [bulkSeries,setBulkSeries]=useState('');
 const [newSeries,setNewSeries]=useState('');
 const [editing,setEditing]=useState<string|null>(null);
 const [editingSeries,setEditingSeries]=useState<string|null>(null);
 const [mergeTarget,setMergeTarget]=useState('');
 const [draft,setDraft]=useState({title:'',series_id:'',issue_number:'',position:'',hidden:false});
 const [seriesDraft,setSeriesDraft]=useState({title:'',description:'',genre:'',position:'0'});
 const t=(a:string,e:string)=>ar?a:e;
 const books=data.books.filter(book=>book.active===1);
 const groups=useMemo(()=>new Map(data.series.map(s=>[s.id,s])),[data.series]);
 const filtered=books.filter(book=>{
  const term=query.trim().toLocaleLowerCase();
  if(term&&!(book.title+' '+book.source_title+' '+book.folder_name+' '+(groups.get(book.series_id||'')?.title||'')).toLocaleLowerCase().includes(term))return false;
  if(tab==='review')return !!book.review_reason;
  if(tab==='ungrouped')return !book.series_id;
  if(tab==='hidden')return !!book.hidden;
  if(tab==='series')return !!book.series_id;
  return true;
 });
 const shown=filtered.slice(0,160);
 async function reload(){
  const [items,status]=await Promise.all([
   requestJSON<Snapshot>(base+'/items'),requestJSON<Stats>(base+'/status')]);
  setData(items);setStats(status);
 }
 useEffect(()=>{
  void reload().catch(()=>setError(t('تعذّر فتح فهرس المكتبة المحلية','Could not load local catalogue')));
  const manage=(event:Event)=>{
   setOpen(true);
   const id=(event as CustomEvent<string|null>).detail;
   const group=data.series.find(s=>s.id===id);
   if(group)beginSeries(group);
  };
  const storageChanged=()=>{void requestJSON<Stats>(base+'/status').then(setStats).catch(()=>{});};
  window.addEventListener('barq:library-manage',manage);
  window.addEventListener('barq:library-storage-changed',storageChanged);
  return()=>{
   window.removeEventListener('barq:library-manage',manage);
   window.removeEventListener('barq:library-storage-changed',storageChanged);
  };
 },[ar,data.series]);
 async function action(url:string,body?:object,method='POST'){
  setBusy(true);setError('');setNotice('');
  try{
   const result=await requestJSON<Report|{updated?:number;merged?:boolean}>(base+url,{
    method,body:body===undefined?undefined:JSON.stringify(body)});
   await reload();
   window.dispatchEvent(new Event('barq:library-changed'));
   setNotice(t('اتحفظت تغييرات المكتبة.','Library updated.'));
   return result;
  }catch{
   setError(t('التعديل ما اتحفظش. تأكد من اتصال Drive ثم جرّب تاني.','Could not save. Check Drive connection and retry.'));
   return undefined;
  }finally{setBusy(false);}
 }
 async function backup(){
  setBusy(true);setError('');setNotice('');
  try{
   const result=await requestJSON<{saved:boolean;file:string;bytes:number}>(base+'/backup',{method:'POST'});
   if(!result.saved)throw new Error('Backup not saved');
   setNotice(t('النسخة الاحتياطية اتحفظت: ','Backup saved: ')+result.file);
   await reload();
  }catch{setError(t('تعذّر إنشاء نسخة احتياطية، راجع صلاحية الكتابة على القرص.','Could not create backup; check disk write permissions.'));}
  finally{setBusy(false);}
 }
 async function scan(){
  const result=await action('/refresh');
  if(result&&'assigned' in result)setReport(result as Report);
 }
 async function organize(){
  const result=await action('/organize');
  if(result&&'assigned' in result)setReport(result as Report);
 }
 async function preview(){
  try{
   setError('');setReport(await requestJSON<Report>(base+'/preview'));
  }catch{setError(t('تعذّر حساب اقتراحات التنظيم.','Could not preview organization.'));}
 }
 async function addSeries(event:FormEvent){
  event.preventDefault();
  if(!newSeries.trim())return;
  const result=await action('/series',{title:newSeries.trim()});
  if(result)setNewSeries('');
 }
 function beginBook(book:Book){
  setEditing(book.id);setEditingSeries(null);
  setDraft({title:book.title,series_id:book.series_id||'',
   issue_number:book.issue_number===null?'':String(book.issue_number),position:String(book.position),hidden:!!book.hidden});
 }
 function beginSeries(group:Series){
  setEditingSeries(group.id);setEditing(null);setMergeTarget('');
  setSeriesDraft({title:group.title,description:group.description,genre:group.genre,position:String(group.position)});
 }
 async function saveBook(event:FormEvent){
  event.preventDefault();
  if(!editing||!draft.title.trim())return;
  const result=await action('/book',{
   id:editing,title:draft.title,series_id:draft.series_id||null,
   issue_number:draft.issue_number?Number(draft.issue_number):null,
   position:Number(draft.position),hidden:draft.hidden,
  });
  if(result)setEditing(null);
 }
 async function saveSeries(event:FormEvent){
  event.preventDefault();
  if(!editingSeries||!seriesDraft.title.trim())return;
  const result=await action('/series/'+editingSeries,{
   title:seriesDraft.title,description:seriesDraft.description,
   genre:seriesDraft.genre,position:Number(seriesDraft.position),
  });
  if(result)setEditingSeries(null);
 }
 async function bulk(payload:object){
  if(!selected.length)return;
  const response=await action('/bulk',{ids:selected,...payload});
  if(response)setSelected([]);
 }
 async function move(book:Book,delta:number){
  const peers=books.filter(other=>other.series_id===book.series_id)
   .sort((a,b)=>(a.position-b.position)||(Number(a.issue_number||99999)-Number(b.issue_number||99999))||
    a.title.localeCompare(b.title,undefined,{numeric:true}));
  const at=peers.findIndex(other=>other.id===book.id);
  const target=peers[at+delta];if(!target)return;
  const order=peers.map(item=>item.id);
  const exchange=order[at];order[at]=order[at+delta];order[at+delta]=exchange;
  await action('/reorder',{ids:order});
 }
 async function dropBook(targetId:string){
  const source=books.find(book=>book.id===dragging);
  const target=books.find(book=>book.id===targetId);
  setDragging(null);
  if(!source||!target||source.id===target.id)return;
  if(source.series_id!==target.series_id){
   setError(t('لنقل كتاب لسلسلة تانية استخدم اختيار السلسلة؛ السحب لترتيب نفس السلسلة.','Use the series selector to move between series. Drag to reorder within one series.'));
   return;
  }
  const siblings=books.filter(book=>book.series_id===source.series_id)
   .sort((a,b)=>(a.position-b.position)||
    (Number(a.issue_number||99999)-Number(b.issue_number||99999))||
    a.title.localeCompare(b.title,undefined,{numeric:true}));
  const order=siblings.map(book=>book.id).filter(id=>id!==source.id);
  const index=order.indexOf(target.id);
  order.splice(index,0,source.id);
  await action('/reorder',{ids:order});
 }
 async function merge(){
  if(!editingSeries||!mergeTarget||editingSeries===mergeTarget)return;
  if(!window.confirm(t('دمج السلسلتين ونقل الأعداد؟','Merge series and move their books?')))return;
  const result=await action('/merge',{source:editingSeries,target:mergeTarget});
  if(result)setEditingSeries(null);
 }
 async function removeSeries(){
  if(!editingSeries)return;
  if(!window.confirm(t('حذف الكارت وفصل كتبه؟ ملفات PDF نفسها مش هتتحذف.','Remove the card and detach its books? PDFs stay untouched.')))return;
  const result=await action('/series/'+editingSeries,undefined,'DELETE');
  if(result)setEditingSeries(null);
 }
 const toggle=(id:string,checked:boolean)=>setSelected(previous=>checked?[...new Set([...previous,id])]:previous.filter(x=>x!==id));
 return <section className="bs-organizer" aria-label={t('إدارة مكتبة برق','BARQ library manager')}>
  <div className="bs-organizer-tools">
   <button className="bs-muted-btn" type="button" onClick={()=>setOpen(x=>!x)} aria-expanded={open}>
    <Settings2 size={16}/>{t('إدارة المكتبة','Manage library')}</button>
   <button className="bs-muted-btn" type="button" disabled={busy} onClick={()=>void scan()}>
    <RefreshCw size={15}/>{t('تحديث الفهرس','Refresh index')}</button>
   <button className="bs-muted-btn bs-auto-btn" type="button" disabled={busy} onClick={()=>void organize()}>
    <Sparkles size={16}/>{t('تنظيم تلقائي','Auto organize')}</button>
   {!!stats&&<div className="bs-organizer-counter" role="status" title={stats.database}>
    <Database size={14}/>
    <strong>{stats.persistent?t('محفوظ محليًا','Saved locally'):t('فحص القاعدة مطلوب','Check database')}</strong>
    <span>{stats.count} {t('كتاب','books')} · {stats.series} {t('سلسلة','series')} · {stats.custom_covers} {t('غلاف','covers')} · {stats.reading_records} {t('سجل قراءة','reading records')}</span>
   </div>}
  </div>
  {(notice||error)&&<p role="status" className={error?'bs-alert':'bs-organizer-ok'}>{error||notice}</p>}
  {!!report&&<p className="bs-organizer-report" role="status">
   {report.preview?t('معاينة بدون تغيير:','Preview only:'):t('تم التنظيم:','Organized:')}
   {' '}{report.books} {t('كتاب','books')} · {report.assigned} {t('داخل سلاسل','grouped')} · {report.numbered} {t('رقم عدد','numbered')} · {report.review} {t('يحتاج مراجعة','need review')}
  </p>}
  {open&&<div className="bs-organizer-panel">
   <div className="bs-organizer-heading"><div><h3><Database size={17}/>{t('منظم مكتبة برق','BARQ library organizer')}</h3>
    <p>{t('برق بيقرأ أسماء الملفات والمجلدات من Drive، يحدد السلاسل وأرقام الأعداد، وبيراجع غير الواضح. تعديلاتك اليدوية لها الأولوية دائمًا.','BARQ scans Drive filenames and folders, groups series and extracts issue numbers. Owner edits always take priority.')}</p>
    <small dir="ltr">{stats?.database}</small></div>
    <button className="bs-muted-btn" type="button" disabled={busy} onClick={()=>void preview()}>{t('معاينة التنظيم','Preview changes')}</button></div>
   {stats&&<details className="bs-organizer-storage">
    <summary><Database size={15}/>{t('تفاصيل قاعدة البيانات المحلية','Local database details')}</summary>
    <div>
     <span>{t('الملف','File')} <code dir="ltr">{stats.database}</code></span>
     <span>{t('سلامة القاعدة','Database integrity')}: {stats.persistent?'OK':t('بحاجة مراجعة','Needs attention')}</span>
     <span>{t('آخر حفظ','Last saved')}: {stats.last_saved_at?new Date(stats.last_saved_at).toLocaleString(ar?'ar-EG':'en-US'):t('لا توجد تغييرات محفوظة بعد','No saved changes yet')}</span>
     <span>{t('الحجم','Size')}: {(stats.db_bytes/1024).toFixed(0)} KB</span>
     <span>{t('ملفات WAL و SHM مؤقتة ومن الطبيعي اختفاؤها بعد إغلاق الاتصال.','WAL and SHM are temporary SQLite files and may disappear when connections close.')}</span>
     <button type="button" className="bs-muted-btn" disabled={busy} onClick={()=>void backup()}>
      {t('حفظ نسخة احتياطية على القرص','Create local database backup')}
     </button>
    </div>
   </details>}
   <div className="bs-organizer-summary">
    <span><Layers size={15}/>{stats?.grouped||0} {t('كتاب ضمن سلاسل','books grouped')}</span>
    <span><Search size={15}/>{stats?.review||0} {t('يحتاج مراجعة','need review')}</span>
    <span><BookOpen size={15}/>{stats?.count||0} {t('كتاب في الفهرس','indexed books')}</span>
   </div>
   <div className="bs-organizer-bar">
    <label className="bs-organizer-search">{t('ابحث','Search')}
     <input value={query} type="search" onChange={event=>setQuery(event.target.value)}
      placeholder={t('اسم الكتاب أو السلسلة أو المجلد','Book, series or folder')}/></label>
    <div className="bs-organizer-tabs">
     {([['all','الكل','All'],['series','داخل سلسلة','Grouped'],['ungrouped','غير مصنف','Ungrouped'],['review','مراجعة','Review'],['hidden','مخفي','Hidden']] as const).map(([id,arLabel,en])=>
      <button key={id} type="button" data-selected={tab===id} onClick={()=>setTab(id)}>{t(arLabel,en)}</button>)}
    </div>
   </div>
   <form className="bs-organizer-create" onSubmit={event=>void addSeries(event)}>
    <input value={newSeries} onChange={event=>setNewSeries(event.target.value)} maxLength={120}
     placeholder={t('اسم سلسلة جديدة...','New series name...')}/>
    <button className="bs-muted-btn" disabled={busy||!newSeries.trim()} type="submit"><BookOpen size={15}/>{t('إنشاء كارت سلسلة','Create series card')}</button>
   </form>
   <div className="bs-organizer-series">
    {data.series.map(group=><div key={group.id} className="bs-organizer-series-item">
     <EditableCover id={'library-series:'+group.id} title={group.title} ar={ar}>
      <div className="bs-real-cover"><BookOpen size={22}/></div>
     </EditableCover>
     <div><strong>{group.title}</strong><small>{books.filter(book=>book.series_id===group.id).length} {t('عدد','issues')}</small></div>
     <button type="button" disabled={busy} onClick={()=>beginSeries(group)}><Settings2 size={15}/>{t('تعديل','Edit')}</button>
    </div>)}
   </div>
   {editingSeries&&<form className="bs-organizer-edit" onSubmit={event=>void saveSeries(event)}>
    <h4>{t('تعديل السلسلة','Edit series')}</h4>
    <label>{t('اسم المجموعة','Series title')}<input value={seriesDraft.title} maxLength={120} onChange={e=>setSeriesDraft(v=>({...v,title:e.target.value}))}/></label>
    <label>{t('الوصف','Description')}<input value={seriesDraft.description} maxLength={500} onChange={e=>setSeriesDraft(v=>({...v,description:e.target.value}))}/></label>
    <label>{t('التصنيف','Genre')}<input value={seriesDraft.genre} maxLength={60} onChange={e=>setSeriesDraft(v=>({...v,genre:e.target.value}))}/></label>
    <label>{t('ترتيب المجموعة','Display order')}<input type="number" min="0" max="100000" value={seriesDraft.position} onChange={e=>setSeriesDraft(v=>({...v,position:e.target.value}))}/></label>
    <button className="bs-muted-btn" type="submit" disabled={busy}>{t('حفظ السلسلة','Save series')}</button>
    <button className="bs-muted-btn" type="button" onClick={()=>setEditingSeries(null)}>{t('إغلاق','Close')}</button>
    <label>{t('دمج مع سلسلة أخرى','Merge into another series')}<select value={mergeTarget} onChange={e=>setMergeTarget(e.target.value)}>
      <option value="">{t('اختار السلسلة','Choose series')}</option>
      {data.series.filter(s=>s.id!==editingSeries).map(s=><option key={s.id} value={s.id}>{s.title}</option>)}
     </select></label>
    <button className="bs-muted-btn" type="button" disabled={!mergeTarget||busy} onClick={()=>void merge()}>{t('دمج السلسلتين','Merge')}</button>
    <button className="bs-muted-btn" type="button" disabled={busy} onClick={()=>void removeSeries()}>{t('حذف الكارت فقط','Remove card only')}</button>
   </form>}
   <div className="bs-organizer-bulk" role="group" aria-label={t('عمليات جماعية','Bulk actions')}>
    <span><CheckSquare size={15}/>{selected.length} {t('محدد','selected')}</span>
    <select aria-label={t('نقل الكتب إلى سلسلة','Move books to series')} value={bulkSeries} onChange={e=>setBulkSeries(e.target.value)}>
     <option value="">{t('كُتب مستقلة','Standalone books')}</option>
     {data.series.map(s=><option key={s.id} value={s.id}>{s.title}</option>)}
    </select>
    <button type="button" disabled={!selected.length||busy} onClick={()=>void bulk({series_id:bulkSeries||null})}>{t('نقل المحدد','Move selected')}</button>
    <button type="button" disabled={!selected.length||busy} onClick={()=>void bulk({hidden:true})}><EyeOff size={14}/>{t('إخفاء','Hide')}</button>
    <button type="button" disabled={!selected.length||busy} onClick={()=>void bulk({hidden:false})}>{t('إظهار','Show')}</button>
    <button type="button" disabled={!selected.length} onClick={()=>setSelected([])}>{t('إلغاء التحديد','Clear')}</button>
   </div>
   <div className="bs-organizer-list">
    {shown.map(book=><div className="bs-organizer-book" key={book.id} draggable
     data-dragging={dragging===book.id} title={t('اسحب لترتيب العدد','Drag to reorder issue')}
     onDragStart={event=>{setDragging(book.id);event.dataTransfer.effectAllowed='move';}}
     onDragOver={event=>{if(dragging)event.preventDefault();}}
     onDrop={event=>{event.preventDefault();void dropBook(book.id);}}
     onDragEnd={()=>setDragging(null)}>
     <input aria-label={t('تحديد','Select')+' '+book.title} type="checkbox" checked={selected.includes(book.id)}
      onChange={event=>toggle(book.id,event.target.checked)}/>
     <div className="bs-organizer-book-info">
      <strong dir="auto">{book.title}</strong>
      <small>{groups.get(book.series_id||'')?.title||t('كتاب مستقل','Standalone')}
       {book.issue_number?' · #'+book.issue_number:''} · {book.folder_name||t('الجذر','Root')}
       {book.review_reason?' · '+t('يراجع','Review'):''}{book.hidden?' · '+t('مخفي','Hidden'):''}
      </small>
     </div>
     <button type="button" disabled={busy} onClick={()=>beginBook(book)}>{t('تعديل','Edit')}</button>
     <button type="button" disabled={busy} title={t('قبل','Move earlier')} onClick={()=>void move(book,-1)}><ArrowUp size={15}/></button>
     <button type="button" disabled={busy} title={t('بعد','Move later')} onClick={()=>void move(book,1)}><ArrowDown size={15}/></button>
     <button type="button" disabled={busy} title={t('إرجاع التنسيق التلقائي','Return to auto')} onClick={()=>void action('/book/'+book.id+'/auto')}>{t('تلقائي','Auto')}</button>
    </div>)}
   </div>
   {filtered.length>shown.length&&<p>{t('استخدم البحث للوصول لباقي الكتب.','Use search to reach the remaining books.')} ({filtered.length})</p>}
   {editing&&<form className="bs-organizer-edit" onSubmit={event=>void saveBook(event)}>
    <h4>{t('تعديل الرواية','Edit book')}</h4>
    <label>{t('اسم العرض','Display title')}<input maxLength={250} value={draft.title} onChange={e=>setDraft(v=>({...v,title:e.target.value}))}/></label>
    <label>{t('السلسلة','Series')}<select value={draft.series_id} onChange={e=>setDraft(v=>({...v,series_id:e.target.value}))}>
      <option value="">{t('كتاب مستقل','Standalone')}</option>
      {data.series.map(s=><option key={s.id} value={s.id}>{s.title}</option>)}
    </select></label>
    <label>{t('رقم العدد','Issue number')}<input type="number" min="1" max="100000" value={draft.issue_number} onChange={e=>setDraft(v=>({...v,issue_number:e.target.value}))}/></label>
    <label>{t('الترتيب','Order')}<input type="number" min="0" max="100000" value={draft.position} onChange={e=>setDraft(v=>({...v,position:e.target.value}))}/></label>
    <label className="bs-organizer-check"><input type="checkbox" checked={draft.hidden} onChange={e=>setDraft(v=>({...v,hidden:e.target.checked}))}/>{t('إخفاء من مكتبتي','Hide in my library')}</label>
    <button className="bs-muted-btn" type="submit" disabled={busy}>{t('حفظ التعديلات','Save changes')}</button>
    <button className="bs-muted-btn" type="button" onClick={()=>setEditing(null)}>{t('إغلاق','Close')}</button>
   </form>}
   <p className="bs-organizer-footnote">{t('الفهرس بيحفظ البيانات بس؛ مش بينقل أو يمسح ملفات Google Drive. نشر الكتب أونلاين له موافقة مستقلة من حساب المالك.','The index stores metadata only; it never moves or deletes Drive files. Online publication requires separate owner approval.')}</p>
  </div>}
 </section>;
}
