import {useMemo,useState} from 'react';
import {ArrowUpRight,Clapperboard,Play,Search} from 'lucide-react';
import './cinema.css';
type Kind='film'|'series'|'anime';
type Film={id:string;title:string;year:string;kind:Kind;genre:string;img:string;url:string};
const works:Film[]=[
{id:'interstellar',title:'Interstellar',year:'2014',kind:'film',genre:'Sci-Fi',img:'https://image.tmdb.org/t/p/w780/gEU2QniE6E77NI6lCU6MxlNBvIx.jpg',url:'https://www.themoviedb.org/movie/157336-interstellar'},
{id:'dune',title:'Dune: Part Two',year:'2024',kind:'film',genre:'Adventure',img:'https://image.tmdb.org/t/p/w780/1pdfLvkbY9ohJlCjQH2CZjjYVvJ.jpg',url:'https://www.themoviedb.org/movie/693134-dune-part-two'},
{id:'oppenheimer',title:'Oppenheimer',year:'2023',kind:'film',genre:'Drama',img:'https://image.tmdb.org/t/p/w780/8Gxv8gSFCU0XGDykEGv7zR1n2ua.jpg',url:'https://www.themoviedb.org/movie/872585-oppenheimer'},
{id:'lastofus',title:'The Last of Us',year:'2023',kind:'series',genre:'Drama',img:'https://i0.wp.com/icecreamconvos.com/wp-content/uploads/2022/12/The-Last-Of-Us-Key-Art.jpg?ssl=1&w=1080',url:'https://www.hbo.com/the-last-of-us'},
{id:'yourname',title:'Your Name',year:'2016',kind:'anime',genre:'Anime film',img:'https://www.kiminona.com/images/news/news_161121.jpg',url:'https://www.kiminona.com/'},
{id:'attackontitan',title:'Attack on Titan',year:'2013',kind:'anime',genre:'Anime series',img:'https://i0.wp.com/codigoespagueti.com/wp-content/uploads/2022/07/Attack-on-Titan-temporada-final-Eren.jpg?quality=80&resize=1280%2C1709&ssl=1',url:'https://shingeki.tv/final/'}
];
export function CinemaDiscovery({ar,onRoom,roomActive}:{ar:boolean;onRoom:()=>void;roomActive:boolean}){
 const [filter,setFilter]=useState<'all'|Kind>('all');
 const [query,setQuery]=useState('');
 const [selected,setSelected]=useState('dune');
 const featured=works.find(x=>x.id===selected)||works[1];
 const shown=useMemo(()=>works.filter(x=>(filter==='all'||x.kind===filter)&&x.title.toLowerCase().includes(query.toLowerCase().trim())),[filter,query]);
 return <section className="barq-cinema">
  <div className="bc-top"><div><span className="bc-kicker"><Clapperboard size={15}/> BARQ CINEMA</span><h2>{ar?'اكتشف حكايتك الجاية':'Discover your next story'}</h2><p>{ar?'أفلام ومسلسلات وأنمي — اختار العمل اللي يعجبك وابدأ غرفة المشاهدة.':'Film, series and anime inspiration. Create a watch room for your own media.'}</p></div>
   <label className="bc-search"><Search size={17}/><input value={query} onChange={e=>setQuery(e.target.value)} aria-label={ar?'بحث العناوين':'Search titles'} placeholder={ar?'ابحث عن عمل…':'Search titles…'}/></label>
  </div>
  <div className="bc-feature" style={{backgroundImage:'linear-gradient(90deg,#130f18 6%,#130f18e8 35%,#130f1840 100%), url("'+featured.img+'")'}}>
   <div className="bc-feature-body"><span className="bc-highlight">{ar?'من اختيارات سينما برق':'FEATURED MOVIE'}</span><h3>{featured.title}</h3>
     <p>{featured.year} · {featured.genre}</p>
     <div className="bc-cta"><button type="button" onClick={onRoom}><Play size={17}/>{roomActive?(ar?'افتح مشغّل الغرفة':'Open room player'):(ar?'إنشاء غرفة مشاهدة':'Create watch room')}</button>
     <a href={featured.url} target="_blank" rel="noopener noreferrer"><ArrowUpRight size={16}/>{ar?'التفاصيل':'About'}</a></div>
   </div>
  </div>
  <div className="bc-tabs"><div role="group" aria-label={ar?'تصنيف':'Filter'}>
    {([['all',ar?'الكل':'All'],['film',ar?'أفلام':'Movies'],['series',ar?'مسلسلات':'Series'],['anime',ar?'أنمي':'Anime']] as const).map(([key,label])=>
    <button type="button" key={key} aria-pressed={filter===key} onClick={()=>setFilter(key)}>{label}</button>)}
   </div><small>{shown.length} {ar?'أعمال':'titles'}</small></div>
  {shown.length?<div className="bc-grid">{shown.map(item=><button type="button" aria-pressed={selected===item.id} key={item.id} onClick={()=>setSelected(item.id)} className="bc-tile">
     <span className="bc-image"><img src={item.img} alt={item.title} loading="lazy" onError={e=>{e.currentTarget.style.display='none'}}/><b>{item.genre}</b></span>
     <span className="bc-info"><strong dir="auto">{item.title}</strong><small>{item.year} · {item.kind==='anime'?'Anime':item.kind==='series'?'Series':'Movie'}</small></span>
    </button>)}</div>:<p className="bc-empty">{ar?'مفيش أعمال مطابقة للبحث.':'No matching titles.'}</p>}
  <p className="bc-fineprint">{ar?'البوسترات للعرض والاستكشاف فقط؛ تشغيل الأعمال يحتاج ملفك أو رابط وسائط مصرح به. حقوق الصور لأصحابها.':'Poster art is for discovery only. Playback requires your own file or authorized direct media link.'}</p>
 </section>;
}
