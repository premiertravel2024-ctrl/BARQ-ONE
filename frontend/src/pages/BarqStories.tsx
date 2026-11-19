import {lazy,Suspense,useCallback,useRef,useState,type ChangeEvent} from 'react';
import {ArrowLeft,BookOpen,ExternalLink,Heart,Search,Upload,X} from 'lucide-react';
import {ButtonGroup, ButtonGroupItem} from '../components/ui/ButtonGroup';
import {Modal} from '../components/ui/Modal';
import {useAppView} from '../lib/appContext';
import {useApp} from '../store';
import {publishedBooks,type PublishedBook} from './publishedBooks';
import {paranormalCollection,paranormalEbooks,paranormalIssues} from './paranormalIssues';
import {DriveBooks,DriveFolderButton,type DriveBook} from './DriveBooks';
import {CloudReading} from './CloudReading';
import './barqStories.css';

const BookReader=lazy(()=>import('./BookReader'));
import type {ReadingEdition} from './BookReader';

const genres=[
 ['الكل','All'],['سلاسل مصرية','Egyptian series'],['روايات مصرية','Egyptian books'],['روايات عالمية','World literature'],
 ['رعب','Horror'],['أدب كلاسيكي','Classics'],['فانتازيا','Fantasy'],['غموض','Mystery'],
 ['خيال علمي','Science fiction'],['مغامرة','Adventure'],['كوميكس','Comics'],['مكتبتي','My library'],
];
function searchKey(value:string){
 return value.toLowerCase().replace(/[\u064b-\u065f\u0670\u0640]/g,'').replace(/[أإآ]/g,'ا').replace(/ى/g,'ي');
}
function savedFavorites():string[]{
 try{
  const saved=JSON.parse(localStorage.getItem('barq-stories-v1')||'{}');
  return Array.isArray(saved?.favorites)?saved.favorites.filter((id:unknown)=>typeof id==='string'):[];
 }catch{return [];}
}
function Cover({book}:{book:PublishedBook}){
 const [failed,setFailed]=useState(false);
 return <div className="bs-real-cover" aria-hidden="true">
  {book.cover&&!failed?<img src={book.cover} alt="" loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={()=>setFailed(true)}/>:
   <><BookOpen size={24}/><strong>{book.title.split(' / ')[0]}</strong><small>{book.author}</small></>}
 </div>;
}

export function BarqStories(){
 const ar=useApp(s=>s.language)==='ar';
 const [query,setQuery]=useState('');
 const [genre,setGenre]=useState('الكل');
 const [favorites,setFavorites]=useState(savedFavorites);
 const [series,setSeries]=useState<PublishedBook>();
 const [issueQuery,setIssueQuery]=useState('');
 const closeSeries=useCallback(()=>setSeries(undefined),[]);
 const issueTerm=searchKey(issueQuery.trim()).replace(/[٠-٩]/g,digit=>String(digit.charCodeAt(0)-0x660)).replace(/[۰-۹]/g,digit=>String(digit.charCodeAt(0)-0x6f0));
 const issues=series?.issues?.filter(issue=>/^\d+$/.test(issueTerm)
  ?issue.number===Number(issueTerm):searchKey(issue.title).includes(issueTerm))||[];

 const [driveBooks,setDriveBooks]=useState<DriveBook[]>();
 const [cloudBooks,setCloudBooks]=useState<DriveBook[]>();
 const [edition,setEdition]=useState<ReadingEdition>();
 const [error,setError]=useState('');
 const upload=useRef<HTMLInputElement>(null);
 const [seriesLimit,setSeriesLimit]=useState(12);
 const localTarget=useRef<Pick<ReadingEdition,'id'|'title'>>();
 const label=(arabic:string,english:string)=>ar?arabic:english;
 const terms=searchKey(query.trim()).split(/\s+/);
 const availableDriveBooks=[...(cloudBooks||[]),...(driveBooks||[])].map(item=>{
  const name=item.edition.title;
  const folders=item.group.split(' / ').map(value=>searchKey(value).replace(/الفئرات/g,'الفئران'));
  if(folders.includes('ما وراء الطبيعة')){
   const issue=/^KAT(SP)?(\d{1,3})$/i.exec(name);
   if(issue){
    const number=Number(issue[2]);
    const title=issue[1]?label('عدد خاص','Special issue')+' '+number:paranormalIssues[number-1]?.title;
    if(title)return {...item,edition:{...item.edition,title:issue[1]?title:number+'. '+title}};
   }
  }
  if(folders.includes('في ممر الفئران'))return {...item,edition:{...item.edition,title:'في ممر الفئران'}};
  return item;
 }).sort((a,b)=>a.edition.title.localeCompare(b.edition.title,undefined,{numeric:true}));
 const matchesDrive=(book:PublishedBook)=>availableDriveBooks.filter(item=>{
  const names=[item.edition.title,...item.group.split(' / ')];
  const titles=book.title.split(' / ').map(searchKey);
  return names.some(name=>titles.includes(searchKey(name).replace(/الفئرات/g,'الفئران')));
 });
 const driveSeries=series?matchesDrive(series):[];
 const visibleSeries=driveSeries.filter(item=>searchKey(item.edition.title).includes(searchKey(issueQuery.trim())));
 const visibleDrive=availableDriveBooks.filter(item=>terms.every(term=>searchKey(item.edition.title+' '+item.group).includes(term)));

 const results=publishedBooks.filter(book=>{
  const visible=genre==='الكل'||genre===book.category||genre===book.genre||
   (genre==='سلاسل مصرية'&&book.series)||(genre==='مكتبتي'&&favorites.includes(book.id));
  return visible&&terms.every(term=>searchKey([book.title,book.author,book.description,book.genre].join(' ')).includes(term));
 });
 useAppView('stories',{mode:edition?'reader':series?'series':'catalogue',item:edition?.file?undefined:edition?.title||series?.title,count:results.length});

 function favorite(id:string){
  const next=favorites.includes(id)?favorites.filter(value=>value!==id):[...favorites,id];
  setFavorites(next);
  try{
   const prior=JSON.parse(localStorage.getItem('barq-stories-v1')||'{}');
   localStorage.setItem('barq-stories-v1',JSON.stringify({...prior,favorites:next}));
  }catch{/* A storage error should not block the library. */}
 }
 function pickFile(target?:Pick<ReadingEdition,'id'|'title'>){
  setError('');localTarget.current=target;upload.current?.click();
 }
 function openFile(event:ChangeEvent<HTMLInputElement>){
  const file=event.currentTarget.files?.[0];
  event.currentTarget.value='';
  if(!file)return;
  if(!/\.pdf$/i.test(file.name)||file.size>64*1024*1024){
   setError(label('اختار ملف PDF حجمه أقل من 64 ميجابايت.','Choose a PDF under 64 MB.'));return;
  }
  const target=localTarget.current;
  setSeries(undefined);
  setEdition({id:'local:'+file.name+':'+file.size+':'+file.lastModified,
   title:target?.title||file.name.replace(/\.pdf$/i,''),format:'pdf',file});
 }
 function openBook(book:PublishedBook){
  if(book.series){setIssueQuery('');setSeriesLimit(12);setSeries(book);return;}
  const cloudEdition=matchesDrive(book)[0]?.edition;
  if(cloudEdition){setEdition(cloudEdition);return;}
  if(book.format){setEdition({id:book.id,title:book.title,format:book.format});return;}
  pickFile(book);
 }
 return <div className="bs-hub" dir={ar?'rtl':'ltr'}>
  <input ref={upload} type="file" accept="application/pdf,.pdf" hidden onChange={openFile}/>
  {error&&<p className="bs-alert" role="alert">{error}</p>}
  {edition?<Suspense fallback={<p role="status">{label('جاري فتح القارئ…','Opening reader…')}</p>}>
   <BookReader key={edition.id} book={edition} ar={ar} onClose={()=>setEdition(undefined)}/>
  </Suspense>:<>
   <header className="bs-header">
    <div className="bs-brand"><span className="bs-brand-mark"><BookOpen size={22}/></span><h1>{label('مكتبة القراءة','Reading Library')}</h1></div>
    <div className="bs-drive-header"><DriveFolderButton ar={ar} onSelect={setDriveBooks}/>
    <button className="bs-muted-btn" type="button" onClick={()=>pickFile()}><Upload size={16}/>{label('افتح PDF من جهازك','Open local PDF')}</button></div>
   </header>
   <CloudReading ar={ar} onBooks={setCloudBooks}/>
   {(cloudBooks||driveBooks)&&<DriveBooks books={visibleDrive} ar={ar} onOpen={setEdition}/>}
   <section className="bs-collection">
    <div className="bs-title-row"><h2>{label('الكتب والسلاسل','Books and series')}</h2>
     <div className="bs-search"><Search size={18} aria-hidden="true"/><input type="search" dir="auto" aria-label={label('ابحث في الكتب','Search books')}
      placeholder={label('اسم كتاب، سلسلة، مؤلف…','Book, series, author…')} value={query} onChange={event=>setQuery(event.target.value)}/>
      {query&&<button type="button" className="bs-clear-search" aria-label={label('امسح البحث','Clear search')} onClick={()=>setQuery('')}><X size={16}/></button>}
     </div>
    </div>
    <ButtonGroup className="bs-filters" size="sm" aria-label={label('تصنيف الكتب','Book categories')}>
     {genres.map(([id,en])=><ButtonGroupItem key={id} aria-pressed={genre===id} onClick={()=>setGenre(id)}>{label(id,en)}</ButtonGroupItem>)}
    </ButtonGroup>
    <p className="bs-result-count" role="status">{label('عدد الكتب والسلاسل','Books and series')}{' · '}{results.length.toLocaleString(ar?'ar-EG':'en')}</p>
    {results.length?<div className="bs-real-grid">{results.map(book=><article className="bs-real-card bs-published-card" key={book.id} data-genre={book.genre}>
     <Cover book={book}/>
     <div className="bs-real-copy"><span>{book.genre}</span><h3 dir="auto">{book.title}</h3><strong dir="auto">{book.author}</strong><p>{book.description}</p>
      <div className="bs-published-actions">
       <button className="bs-series-open" type="button" onClick={()=>openBook(book)}
        aria-label={book.series?label('أعداد السلسلة','Browse issues'):(book.format||matchesDrive(book).length)?label('اقرأ في برق','Read in BARQ'):label('افتح نسختك PDF','Open your PDF')}>
        {book.series?label('الأعداد','Issues'):(book.format||matchesDrive(book).length)?label('اقرأ','Read'):label('افتح PDF','Open PDF')}<ArrowLeft size={15}/>
       </button>
       <button className="bs-favorite" type="button" aria-label={label('احفظ ','Save ')+book.title} aria-pressed={favorites.includes(book.id)} onClick={()=>favorite(book.id)}>
        <Heart size={17} fill={favorites.includes(book.id)?'currentColor':'none'}/>
       </button>
      </div>
      {!book.format&&!book.series&&!matchesDrive(book).length&&<a href={book.url} target="_blank" rel="noopener noreferrer" className="bs-publisher-link"><ExternalLink size={13}/>{label('الطبعة الرسمية','Official edition')}</a>}
     </div>
    </article>)}</div>:<p className="bs-empty">{label('مفيش كتب مطابقة للبحث.','No matching books.')}</p>}
   </section>
  </>}
  <Modal open={!!series} onClose={closeSeries} title={series?.title||''} wide bodyClassName="bs-series-scroll"
   footer={series&&!driveSeries.length&&<div className="bs-reading-options">
    {series.id==='paranormal'&&<a className="bs-primary" href={paranormalEbooks} target="_blank" rel="noopener noreferrer">
     {label('النسخ الإلكترونية على Google Play','Ebooks on Google Play')}
    </a>}
    <a className="bs-primary" href={series.id==='paranormal'?paranormalCollection:series.url} target="_blank" rel="noopener noreferrer">
    {series.id==='paranormal'?label('المجموعة الكاملة عند الناشر','Complete set from the publisher'):label('كل الأعداد عند الناشر','All issues at the publisher')}
    </a>
   </div>}>
   {series&&driveSeries.length>0&&<section className="bs-series-detail" dir={ar?'rtl':'ltr'}>
    <input className="bs-search" type="search" value={issueQuery} onChange={event=>setIssueQuery(event.target.value)}
     placeholder={label('ابحث في روايات السلسلة…','Search series books…')}/>
    <DriveBooks ar={ar} heading={false} books={visibleSeries.slice(0,seriesLimit)}
     onOpen={item=>{closeSeries();setEdition(item);}}/>
    {visibleSeries.length>seriesLimit&&<button className="bs-muted-btn" type="button" onClick={()=>setSeriesLimit(n=>n+12)}>{label('اعرض أعداد أكتر','Show more issues')}</button>}
   </section>}
   {series&&!driveSeries.length&&<section className="bs-series-detail"  dir={ar?'rtl':'ltr'}>
    <strong>{series.author}</strong><p>{series.description}</p>
    <p>{label('لو عندك نسخة PDF من العدد، افتحها هنا في برق.','If you have a PDF of an issue, open it here in BARQ.')}</p>
    {!!series.issues?.length&&<>
     <label className="bs-search"><Search size={17}/><input value={issueQuery} onChange={event=>setIssueQuery(event.target.value)}
      aria-label={label('ابحث عن عدد','Find an issue')} placeholder={label('اسم العدد أو رقمه…','Issue title or number…')}/></label>
     <p role="status">{issues.length} / {series.issues.length} {label('عدد','issues')}</p>
     <ol>{issues.map(issue=><li key={issue.number}>
     <span>{issue.number}. {issue.title}</span>
     <div><button type="button" onClick={()=>pickFile({id:series.id+'-'+issue.number,title:issue.title})}>{label('افتح PDF','Open PDF')}</button>
      <a href={issue.url} target="_blank" rel="noopener noreferrer"><ExternalLink size={14}/>{label('الناشر','Publisher')}</a></div>
    </li>)}</ol></>}
    {!series.issues?.length&&<button type="button" onClick={()=>pickFile(series)}>{label('افتح نسخة PDF','Open a PDF')}</button>}
   </section>}
  </Modal>
 </div>;
}
