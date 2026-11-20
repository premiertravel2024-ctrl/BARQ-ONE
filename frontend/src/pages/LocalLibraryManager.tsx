import {useEffect,useState,type FormEvent} from 'react';
import {BookOpen,Database,RefreshCw} from 'lucide-react';
import {requestJSON} from '../lib/backend';
type Book={id:string;title:string;folder_name:string;published:number;active:number;series_id:string|null;issue_number:number|null;position:number;};
type Series={id:string;title:string;description:string};
type Snapshot={books:Book[];series:Series[]};
const base='/v1/reading/library';

export function LocalLibraryManager({ar}:{ar:boolean}){
 const [items,setItems]=useState<Snapshot>({books:[],series:[]});
 const [status,setStatus]=useState<{database:string;count:number}>();
 const [search,setSearch]=useState('');
 const [newSeries,setNewSeries]=useState('');
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [open,setOpen]=useState(false);
 const label=(arabic:string,english:string)=>ar?arabic:english;
 async function reload(){
  const [snapshot,information]=await Promise.all([
   requestJSON<Snapshot>(base+'/items'),requestJSON<{database:string;count:number}>(base+'/status'),
  ]);
  setItems(snapshot);setStatus(information);
 }
 useEffect(()=>{void reload().catch(()=>setError(label('تعذّر قراءة قاعدة البيانات المحلية.','Local catalogue could not be loaded.')));},[ar]);
 async function refresh(){
  setBusy(true);setError('');
  try{
   await requestJSON(base+'/refresh',{method:'POST'});
   await reload();
   window.dispatchEvent(new Event('barq:library-changed'));
  }catch{setError(label('تعذّر تحديث القائمة من درايف.','Could not sync books from Drive.'));}
  finally{setBusy(false);}
 }
 async function createSeries(event:FormEvent){
  event.preventDefault();
  if(!newSeries.trim())return;
  setBusy(true);setError('');
  try{
   await requestJSON(base+'/series',{method:'POST',body:JSON.stringify({title:newSeries.trim()})});
   setNewSeries('');await reload();
   window.dispatchEvent(new Event('barq:library-changed'));
  }catch{setError(label('تعذّر إنشاء السلسلة.','Could not create series.'));}
  finally{setBusy(false);}
 }
 async function edit(id:string,values:Partial<Omit<Book,'published'>>&{published?:boolean}){
  setBusy(true);setError('');
  try{
   await requestJSON(base+'/book',{method:'POST',body:JSON.stringify({id,...values})});
   await reload();
   window.dispatchEvent(new Event('barq:library-changed'));
  }catch{setError(label('تعذّر حفظ تعديل الكتاب.','Could not save book change.'));}
  finally{setBusy(false);}
 }
 const filtered=items.books.filter(item=>item.active===1&&
  (item.title+' '+item.folder_name).toLocaleLowerCase().includes(search.toLocaleLowerCase()));
 return <section className="bs-local-manager">
  <button className="bs-muted-btn" type="button" aria-expanded={open} onClick={()=>setOpen(value=>!value)}>
   <Database size={16}/>{label('إدارة المكتبة المحلية والسلاسل','Manage local library and series')}</button>
  {open&&<div className="bs-local-manager-panel">
   <h3>{label('قاعدة بيانات مكتبتك','Your library database')}</h3>
   <p>{status?.database||label('جاري تحديد مكان قاعدة البيانات','Locating local database')}</p>
   <p>{label('عدد الكتب المفهرسة','Indexed books')}: {status?.count??'—'}</p>
   <button className="bs-muted-btn" type="button" disabled={busy} onClick={()=>void refresh()}>
    <RefreshCw size={15}/>{label('افهرس فولدر درايف','Index Drive folder')}</button>
   <form onSubmit={event=>void createSeries(event)} className="bs-local-series-form">
    <label>{label('اسم كارت السلسلة','Series card title')}
     <input value={newSeries} maxLength={120} onChange={event=>setNewSeries(event.target.value)}
      placeholder={label('مثال: ما وراء الطبيعة','Example: Paranormal')}/></label>
    <button className="bs-muted-btn" type="submit" disabled={busy||!newSeries.trim()}><BookOpen size={15}/>{label('إنشاء سلسلة','Create series')}</button>
   </form>
   <label className="bs-local-manager-search">{label('ابحث في رواياتك','Find your books')}
    <input type="search" value={search} onChange={event=>setSearch(event.target.value)}
     placeholder={label('عنوان أو اسم فولدر','Title or folder')}/></label>
   {error&&<p className="bs-alert" role="alert">{error}</p>}
   <p className="bs-local-manager-summary">{filtered.length} {label('كتاب','books')}</p>
   <div className="bs-local-manager-list">
    {filtered.slice(0,100).map(book=><div key={book.id} className="bs-local-manager-item">
      <div><strong dir="auto">{book.title}</strong><small dir="auto">{book.folder_name}</small></div>
      <select aria-label={label('تعيين سلسلة','Assign series')+' '+book.title} disabled={busy}
       value={book.series_id||''} onChange={event=>void edit(book.id,{series_id:event.target.value||null})}>
       <option value="">{label('بدون سلسلة','No series')}</option>
       {items.series.map(series=><option key={series.id} value={series.id}>{series.title}</option>)}
      </select>
      <label>{label('رقم العدد','Issue')}<input type="number" min={1} max={100000}
       defaultValue={book.issue_number||''} key={book.issue_number??'none'}
       onBlur={event=>{const next=event.target.value?Number(event.target.value):null;
        if(next!==book.issue_number)void edit(book.id,{issue_number:next});}}/></label>
      <button type="button" disabled={busy} onClick={()=>void edit(book.id,{published:!Boolean(book.published)})}>
       {book.published?label('إلغاء النشر المحلي','Unpublish locally'):label('نشر محليًا','Publish locally')}</button>
     </div>)}
   </div>
   {filtered.length>100&&<p>{label('اعرض نتائج أقل بالبحث لتعديل كتاب محدد.','Search to manage books beyond the first 100.')}</p>}
   <small>{label('النشر على الإنترنت مستقل، ولا يتم مشاركة أي كتاب تلقائيًا.','Online publication is separate. No books are shared automatically.')}</small>
  </div>}
 </section>;
}
