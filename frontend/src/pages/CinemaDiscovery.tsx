import {useCallback,useEffect,useState} from 'react';
import {Bookmark,Clapperboard,Heart,KeyRound,Play,MonitorUp,Search,Star,UsersRound} from 'lucide-react';
import {useAppView} from '../lib/appContext';
import {requestJSON} from '../lib/backend';
import {Modal} from '../components/ui/Modal';
import './cinema.css';
type Title={id:number;kind:'movie'|'tv';title:string;overview:string;date:string;rating:number|null;poster:string|null;backdrop:string|null;genres:number[]};
type Detail=Title&{genre_names:string[];cast:{name:string;character:string;photo:string|null}[];runtime?:number;seasons?:number;related:Title[]};
type Rail={name:string;items:Title[];tab:string;collection:string};
type Page={results:Title[];page:number;total_pages:number;total_results:number;filtered_page:boolean};
const key=(t:Title)=>t.kind+':'+t.id;
function saved(name:string):Title[]{try{const a=JSON.parse(localStorage.getItem(name)||'[]');return Array.isArray(a)?a.filter(x=>x&&typeof x.id==='number'&&['movie','tv'].includes(x.kind)&&typeof x.title==='string'):[];}catch{return [];}}
function Poster({item}:{item:Title}){const [failed,setFailed]=useState(false);return <span className="bc-image">{item.poster&&!failed?<img src={item.poster} alt="" loading="lazy" onError={()=>setFailed(true)}/>:<Clapperboard size={32}/>}<span className="bc-score"><Star size={12}/>{item.rating===null?'—':item.rating.toFixed(1)}</span></span>;}
const markets=[['SA','السعودية','Saudi Arabia'],['EG','مصر','Egypt'],['AE','الإمارات','UAE'],['GB','بريطانيا','UK'],['US','أمريكا','US']];
type Availability={link:string;groups:Record<string,string[]>};
function WhereToWatch({title,ar}:{title:Title;ar:boolean}){
 const [region,setRegion]=useState('SA');
 const [data,setData]=useState<Availability>();
 const [error,setError]=useState(false);
 useEffect(()=>{
  const controller=new AbortController();
  setData(undefined);setError(false);
  void requestJSON<Availability>('/v1/cinema/providers/'+title.kind+'/'+title.id+'?region='+region,{signal:controller.signal})
   .then(setData).catch(()=>{if(!controller.signal.aborted)setError(true);});
  return()=>controller.abort();
 },[title.id,title.kind,region]);
 const labels:Record<string,string>={flatrate:ar?'اشتراك':'Subscription',free:ar?'مجاني':'Free',ads:ar?'بإعلانات':'With ads',rent:ar?'إيجار':'Rent',buy:ar?'شراء':'Buy'};
 const groups=data?.groups?Object.entries(data.groups).filter(([group,items])=>labels[group]&&items.length):[];
 return <section className="bc-availability">
  <div><h3>{ar?'فين تتفرج؟':'Where to watch'}</h3>
   <select aria-label={ar?'بلد المشاهدة':'Watch region'} value={region} onChange={event=>setRegion(event.target.value)}>
    {markets.map(([code,arabic,english])=><option key={code} value={code}>{ar?arabic:english}</option>)}
   </select>
  </div>
  {error?<p role="status">{ar?'تعذّر تحميل المنصات.':'Provider listings are unavailable.'}</p>:!data?<p role="status">{ar?'جاري تحميل المنصات…':'Loading providers…'}</p>:!groups.length?
    <p>{ar?'مفيش منصات مدرجة للبلد ده.':'No providers are listed for this region.'}</p>:
    <><ul>{groups.map(([group,items])=><li key={group}><strong>{labels[group]}</strong><span>{items.join(' · ')}</span></li>)}</ul>
     <small>{ar?'بيانات المشاهدة من':'Availability data by'} <a href="https://www.justwatch.com/" target="_blank" rel="noopener noreferrer">JustWatch</a></small>
     {data.link&&<a className="bc-join" href={data.link} target="_blank" rel="noopener noreferrer">{ar?'شوف خيارات المشاهدة':'View watch options'}</a>}
    </>}
 </section>;
}
export function CinemaDiscovery({ar,onRoom,onJoin,onScreenShare,roomActive}:{ar:boolean;onScreenShare?:()=>void;onRoom:()=>void;onJoin:()=>void;roomActive:boolean}){
 const [tab,setTab]=useState('home'),[kind,setKind]=useState<'movie'|'tv'>('movie'),[collection,setCollection]=useState('popular');
 const [query,setQuery]=useState(''),[search,setSearch]=useState(''),[genre,setGenre]=useState(''),[year,setYear]=useState(''),[rating,setRating]=useState('0');
 const [genres,setGenres]=useState<{id:number;name:string}[]>([]),[page,setPage]=useState(1),[result,setResult]=useState<Page>(),[rails,setRails]=useState<Rail[]>([]);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[configured,setConfigured]=useState<boolean>(),[retry,setRetry]=useState(0);
 const [setup,setSetup]=useState(false),[token,setToken]=useState(''),[saving,setSaving]=useState(false),[setupError,setSetupError]=useState('');
 const [favorites,setFavorites]=useState(()=>saved('barq-cinema-favorites')),[watchlist,setWatchlist]=useState(()=>saved('barq-cinema-watchlist'));
 const [selected,setSelected]=useState<Title>(),[detail,setDetail]=useState<Detail>(),[detailError,setDetailError]=useState('');
 const language=ar?'ar-SA':'en-US',local=tab==='favorites'||tab==='watchlist';
 const home=tab==='home'&&!search;
 useAppView('watch',{mode:tab,item:selected?.title,count:result?.total_results,status:configured===false?'catalogue setup required':busy?'loading':error?'unavailable':undefined});
 const close=useCallback(()=>setSelected(undefined),[]);
 useEffect(()=>{const t=setTimeout(()=>setSearch(query.trim()),350);return()=>clearTimeout(t);},[query]);
 useEffect(()=>{void requestJSON<{configured:boolean}>('/v1/cinema/status').then(d=>{setConfigured(d.configured);}).catch(e=>setError(String(e)));},[retry]);
 useEffect(()=>{if(!configured)return;const c=new AbortController();setGenres([]);void requestJSON<{genres:{id:number;name:string}[]}>('/v1/cinema/genres?kind='+kind+'&language='+language,{signal:c.signal}).then(d=>setGenres(d.genres)).catch(()=>{});return()=>c.abort();},[kind,language,configured]);
 useEffect(()=>{setPage(1);setResult(undefined);},[tab,kind,collection,search,genre,year,rating,language]);
 useEffect(()=>{
  if(!configured||local){setBusy(false);return;}const c=new AbortController();setBusy(true);setError('');
  const get=(params:Record<string,string>)=>requestJSON<Page>('/v1/cinema/browse?'+new URLSearchParams({language,...params}),{signal:c.signal});
  const run=async()=>{
   if(home){
    const definitions=[
     ['trending','movie','movie',ar?'الرائج دلوقتي':'Trending now'],
     ['popular','movie','movie',ar?'أفلام مشهورة':'Popular movies'],
     ['popular','tv','tv',ar?'مسلسلات مشهورة':'Popular series'],
     ['popular','tv','anime',ar?'عالم الأنمي':'Anime collection'],
     ['recent','movie','movie',ar?'نزلت مؤخرًا':'Recently released'],
    ];
    const rows=await Promise.allSettled(definitions.map(async([collection,kind,tab,name])=>({
     collection,tab,name,items:(await get({collection,kind,anime:String(tab==='anime')})).results,
    })));
    if(c.signal.aborted)return;
    const available=rows.flatMap(row=>row.status==='fulfilled'?[row.value]:[]);
    setRails(available);
    if(!available.length)throw new Error(ar?'كتالوج السينما مش متاح دلوقتي.':'The cinema catalogue is temporarily unavailable.');
   }else{const d=await get({kind,collection,query:search,page:String(page),...(genre?{genre}:{}),...(year?{year}:{}),rating,anime:String(tab==='anime')});if(!c.signal.aborted)setResult(d);}
  };
  void run().catch(e=>{if(!c.signal.aborted)setError(e.message);}).finally(()=>{if(!c.signal.aborted)setBusy(false);});return()=>c.abort();
 },[configured,local,home,tab,kind,collection,search,page,genre,year,rating,language,retry,ar]);
 useEffect(()=>{if(!selected)return;const c=new AbortController();setDetail(undefined);setDetailError('');void requestJSON<Detail>(`/v1/cinema/details/${selected.kind}/${selected.id}?language=${language}`,{signal:c.signal}).then(d=>{if(!c.signal.aborted)setDetail(d);}).catch(e=>{if(!c.signal.aborted)setDetailError(e.message);});return()=>c.abort();},[selected,language]);
 function toggle(item:Title,list:Title[],set:(v:Title[])=>void,name:string){const next=list.some(t=>key(t)===key(item))?list.filter(t=>key(t)!==key(item)):[item,...list];set(next);try{localStorage.setItem(name,JSON.stringify(next));}catch{setError(ar?'مساحة الحفظ ممتلئة؛ التغيير للجلسة دي بس.':'Storage is full; changes last for this session only.');}}
 const actions=(item:Title)=><div className="bc-card-actions"><button aria-label={ar?'المفضلة':'Favorite'} aria-pressed={favorites.some(t=>key(t)===key(item))} onClick={()=>toggle(item,favorites,setFavorites,'barq-cinema-favorites')}><Heart size={17}/></button><button aria-label={ar?'قائمة المشاهدة':'Watchlist'} aria-pressed={watchlist.some(t=>key(t)===key(item))} onClick={()=>toggle(item,watchlist,setWatchlist,'barq-cinema-watchlist')}><Bookmark size={17}/></button></div>;
 const cards=(items:Title[],rail=false)=><div className={rail?'bc-rail':'bc-grid'}>{items.map(item=><article data-spotlight className="bc-tile" key={key(item)}><button className="bc-open" onClick={()=>setSelected(item)} aria-label={item.title}><Poster item={item}/><strong dir="auto">{item.title}</strong><small>{item.date.slice(0,4)||'—'} · {item.kind==='movie'?(ar?'فيلم':'Movie'):(ar?'مسلسل':'Series')}</small></button>{actions(item)}</article>)}</div>;
 function showTab(next:string,sort='popular'){
  setTab(next);setCollection(sort);setGenre('');
  if(next==='movie'||next==='tv'||next==='anime')setKind(next==='anime'?'tv':next);
 }
 const featured=rails[0]?.items.find(t=>t.backdrop),shown=local?(tab==='favorites'?favorites:watchlist).filter(t=>t.title.toLocaleLowerCase().includes(search.toLocaleLowerCase())):result?.results||[];
 return <section className="barq-cinema" dir={ar?'rtl':'ltr'}>
  <header className="bc-top">
   <div><h1>{ar?'سينما برق':'BARQ Cinema'}</h1></div>
   <div className="bc-room-actions">
    <button className="bc-primary" onClick={onRoom}><UsersRound size={17}/>{roomActive?(ar?'غرفتك':'Your room'):(ar?'افتح غرفة مشاهدة':'Host a watch room')}</button>
    {onScreenShare&&<button className="bc-join" type="button" onClick={onScreenShare}><MonitorUp size={17}/>{ar?'شارك شاشة ويندوز':'Share Windows screen'}</button>}
    <button className="bc-join" type="button" onClick={onJoin}><KeyRound size={17}/>{ar?'ادخل بكود':'Join with code'}</button>
   </div>
  </header>
  <div className="bc-discovery-toolbar">
   <nav className="bc-tabs" aria-label={ar?'مكتبة السينما':'Cinema library'}>{[['home',ar?'اكتشف':'Discover'],['movie',ar?'أفلام':'Movies'],['tv',ar?'مسلسلات':'Series'],['anime',ar?'أنمي':'Anime'],['favorites',ar?'المفضلة':'Favorites'],['watchlist',ar?'قائمتي':'Watchlist']].map(([id,label])=><button key={id} aria-pressed={tab===id} onClick={()=>showTab(id)}>{label}</button>)}</nav>
   <label className="bc-search"><Search size={18}/><input type="search" aria-label={ar?'ابحث في الكتالوج':'Search catalogue'} value={query} onChange={e=>setQuery(e.target.value)} placeholder={ar?'فيلم، مسلسل، أو أنمي…':'Movies, series, anime…'}/></label>
  </div>
  {configured===false&&!local&&<div className="bc-state"><Clapperboard size={40}/><h3>{ar?'فعّل مكتبة السينما':'Enable your cinema library'}</h3><p>{ar?'وصّل مصدر بيانات الأفلام والمسلسلات مرة واحدة، وخلّي باقي التجربة داخل برق. مفتاح المصدر بيتخزن بأمان على جهازك.':'Connect a movie and TV metadata source once. Credentials stay in your computer’s secure vault.'}</p><button className="bc-primary" onClick={()=>setSetup(true)}>{ar?'إعداد المكتبة':'Set up catalogue'}</button></div>}
  {error&&!local&&<div className="bc-state" role="alert"><p>{error.replace(/TMDB_READ_TOKEN|TMDB/gi,ar?'خدمة المكتبة':'catalogue service')}</p><button onClick={()=>setRetry(v=>v+1)}>{ar?'حاول تاني':'Retry'}</button></div>}
  {home&&featured&&!error&&<article className="bc-feature" style={{backgroundImage:`linear-gradient(0deg,#0F1115 0%,transparent 95%),url("${featured.backdrop}")`}}><div className="bc-feature-body"><span className="bc-kicker">{ar?'تحت الأضواء':'IN THE SPOTLIGHT'}</span><h3 dir="auto">{featured.title}</h3><p>{featured.date.slice(0,4)} · ★ {featured.rating?.toFixed(1)||'—'}</p><p className="bc-overview">{featured.overview}</p><button className="bc-primary" onClick={()=>setSelected(featured)}>{ar?'اكتشف التفاصيل':'Explore title'}</button></div></article>}
  {!home&&!local&&configured&&<div className="bc-filters"><select aria-label={ar?'نوع العمل':'Media type'} value={kind} onChange={e=>{setKind(e.target.value as 'movie'|'tv');setGenre('');}}><option value="movie">{ar?'أفلام':'Movies'}</option><option value="tv">{ar?'مسلسلات':'Series'}</option></select><select aria-label={ar?'الترتيب':'Collection'} value={collection} disabled={!!search} onChange={e=>setCollection(e.target.value)}>{[['popular',ar?'الأشهر':'Popular'],['trending',ar?'الرائج':'Trending'],['recent',ar?'الأحدث':'Recent'],['top',ar?'الأعلى تقييمًا':'Top rated']].map(([id,label])=><option key={id} value={id}>{label}</option>)}</select><select aria-label={ar?'التصنيف':'Genre'} value={genre} onChange={e=>setGenre(e.target.value)}><option value="">{ar?'كل التصنيفات':'All genres'}</option>{genres.map(g=><option key={g.id} value={g.id}>{g.name}</option>)}</select><input type="number" min="1870" max="2100" value={year} aria-label={ar?'سنة الإصدار':'Release year'} placeholder={ar?'السنة':'Year'} onChange={e=>setYear(e.target.value)}/><select aria-label={ar?'أقل تقييم':'Minimum rating'} value={rating} onChange={e=>setRating(e.target.value)}><option value="0">{ar?'كل التقييمات':'All ratings'}</option>{[5,6,7,8,9].map(r=><option key={r} value={r}>{r}+ ★</option>)}</select></div>}
  {busy&&!local&&<div className="bc-loading" role="status">{ar?'بنجيب العناوين…':'Loading titles…'}<div className="bc-grid">{Array.from({length:6},(_,i)=><div className="bc-skeleton" key={i}/>)}</div></div>}
  {!busy&&home&&!local&&!error&&rails.filter(row=>row.items.length).map(row=><section className="bc-collection" key={row.name}>
   <div className="bc-collection-head"><h3>{row.name}</h3><button onClick={()=>showTab(row.tab,row.collection)}>{ar?'عرض الكل':'View all'}</button></div>
   {cards(row.items,true)}</section>)}
  {(!busy||local)&&!home&&<>{result?.filtered_page&&<p className="bc-muted">{ar?'التصفية على صفحة نتائج البحث الحالية؛ تقدر تكمل باقي الصفحات.':'Filters apply to this search page. Continue browsing subsequent pages.'}</p>}{cards(shown)}{!shown.length&&(local||!error&&configured)&&<p className="bc-state">{ar?'مفيش عناوين هنا لسه. جرّب بحث تاني أو ضيف لقائمتك.':'No titles here. Try another search or save a title.'}</p>}{!local&&result&&result.total_pages>1&&<div className="bc-pagination"><button disabled={page<=1} onClick={()=>setPage(v=>v-1)}>{ar?'السابق':'Previous'}</button><span>{page} / {result.total_pages}</span><button disabled={page>=result.total_pages} onClick={()=>setPage(v=>v+1)}>{ar?'التالي':'Next'}</button></div>}</>}
  
  <Modal open={setup} onClose={()=>setSetup(false)} title={ar?'ربط بيانات المكتبة':'Connect catalogue'}><form onSubmit={async e=>{e.preventDefault();setSaving(true);setSetupError('');try{await requestJSON('/v1/cinema/setup',{method:'POST',body:JSON.stringify({token:token.trim()})});setToken('');setSetup(false);setRetry(v=>v+1);}catch(e){setSetupError(e instanceof Error?e.message:String(e));}finally{setSaving(false);}}}><p>{ar?'لو مكتبة الأفلام مش متفعّلة، أدخل رمز الربط الخاص بمكتبتك واضغط تحقق واحفظ. الرمز بيُحفظ محليًا، ومش بيظهر في الواجهة.':'To activate movie discovery, enter your catalogue access credential and choose Verify and save. It stays in your secure local settings.'}</p><input className="bc-token" type="password" autoComplete="off" value={token} onChange={e=>setToken(e.target.value)} aria-label={ar?'مفتاح مصدر المكتبة':'Catalogue API credential'} required/>{setupError&&<p role="alert">{setupError.replace(/TMDB_READ_TOKEN|TMDB/gi,ar?'خدمة المكتبة':'catalogue service')}</p>}<button className="bc-primary" disabled={saving}>{saving?(ar?'بنتحقق…':'Verifying…'):(ar?'تحقق واحفظ':'Verify and save')}</button></form></Modal>
  <Modal open={!!selected} onClose={close} title={selected?.title||''} wide bodyClassName="bc-detail"><div dir={ar?'rtl':'ltr'}>{selected?.backdrop&&<img className="bc-detail-backdrop" src={selected.backdrop} alt=""/>}<p>{detail?.genre_names.join(' · ')}</p><p>{selected?.overview|| (ar?'الوصف مش متاح باللغة دي.':'No synopsis available in this language.')}</p>{detailError&&<p role="alert">{detailError}</p>}{!detail&&!detailError&&<p role="status">{ar?'بنجيب التفاصيل…':'Loading details…'}</p>}{detail&&<><p>{detail.runtime?`${detail.runtime} ${ar?'دقيقة':'min'}`:''}{detail.seasons?`${detail.seasons} ${ar?'مواسم':'seasons'}`:''}</p><h3>{ar?'طاقم التمثيل':'Cast'}</h3><div className="bc-cast">{detail.cast.map((c,i)=><div key={i}>{c.photo&&<img src={c.photo} alt="" loading="lazy"/>}<strong>{c.name}</strong><small>{c.character}</small></div>)}</div><h3>{ar?'ممكن يعجبك':'You may also like'}</h3>{cards(detail.related,true)}</>}{selected&&<WhereToWatch key={key(selected)} title={selected} ar={ar}/>} {selected&&actions(selected)}<button className="bc-primary" onClick={()=>{close();onRoom();}}><Play size={16}/>{ar?'افتح غرفة لملفك':'Open room for your media'}</button></div></Modal>
 </section>;
}
