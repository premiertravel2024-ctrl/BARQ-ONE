import {FormEvent,useEffect,useRef,useState} from 'react';
import {ExternalLink,Headphones,Music2,Play,Search,X} from 'lucide-react';
import {requestJSON} from '../lib/backend';
import './musicServices.css';

type Provider='spotify'|'anghami';
type Embed={src:string;page:string;title:string;kind:string};
const SPOTIFY_KINDS=new Set(['track','album','playlist','artist','episode','show']);
const ANGHAMI_KINDS=new Set(['song','album','playlist','artist']);

/** All iframe destinations are reconstructed from strict official host/ID allowlists. */
function officialEmbed(raw:string,provider:Provider):Embed|undefined{
 const url=new URL(raw.trim());
 if(url.protocol!=='https:'||url.username||url.password||url.port)return;
 const parts=url.pathname.split('/').filter(Boolean);
 if(parts[0]==='embed')parts.shift();
 if(provider==='spotify'&&url.hostname==='open.spotify.com'&&parts.length===2&&
   SPOTIFY_KINDS.has(parts[0])&&/^[a-zA-Z0-9]{22}$/.test(parts[1]))
   return {src:'https://open.spotify.com/embed/'+parts[0]+'/'+parts[1],page:'https://open.spotify.com/'+parts[0]+'/'+parts[1],kind:parts[0],title:'Spotify'};
 if(provider==='anghami'&&['play.anghami.com','www.anghami.com','anghami.com','widget.anghami.com'].includes(url.hostname)&&
   parts.length===2&&ANGHAMI_KINDS.has(parts[0])&&/^\d{1,15}$/.test(parts[1]))
   return {src:'https://widget.anghami.com/'+parts[0]+'/'+parts[1],page:'https://play.anghami.com/'+parts[0]+'/'+parts[1],kind:parts[0],title:'Anghami'};
}
async function resolveAnghami(raw:string):Promise<Embed|undefined>{
 const u=new URL(raw);
 const parts=u.pathname.split('/').filter(Boolean);
 if(u.protocol!=='https:'||u.hostname!=='open.anghami.com'||parts.length!==1||!/^[A-Za-z0-9_-]{5,60}$/.test(parts[0]))return;
 const res=await fetch('https://barq-one.ashraf-mohamed.workers.dev/api/resolve/anghami/'+encodeURIComponent(parts[0]),{method:'GET',mode:'cors',credentials:'omit',signal:AbortSignal.timeout(6500)});
 if(!res.ok)return;
 const data=await res.json() as {provider?:string;kind?:string;id?:string};
 if(data.provider!=='anghami'||!data.kind||!data.id)return;
 return officialEmbed('https://play.anghami.com/'+data.kind+'/'+data.id,'anghami');
}
type Release={kind:string;id:string;title:string;artist?:string;artwork?:string;alias?:string};
const featured:Record<Provider,Release[]>={
 spotify:[
  {kind:'artist',id:'5abSRg0xN1NV3gLbuvX24M',title:'عمرو دياب',alias:'Amr Diab'},
  {kind:'playlist',id:'37i9dQZF1DWYFV1CnuXO8v',title:'حب وغرام',artist:'Spotify'},
  {kind:'track',id:'4ZXnE6NdKAQMaMzsDuFurd',title:'Single',artist:'عمرو دياب',alias:'Amr Diab'},
 ],
 anghami:[
  {kind:'song',id:'102704',title:'تملى معاك',artist:'عمرو دياب',alias:'Tamally Maak Amr Diab'},
  {kind:'artist',id:'75',title:'أنغام',alias:'Angham'},
  {kind:'artist',id:'8163',title:'كايروكي',alias:'Cairokee'},
  {kind:'album',id:'374',title:'تملى معاك',artist:'عمرو دياب',alias:'Tamally Maak Amr Diab'},
 ],
};
const normalize=(value:string)=>value.toLocaleLowerCase().normalize('NFKD').replace(/[\u064b-\u065f\u0670\u0640]/g,'').replace(/[أإآ]/g,'ا').replace(/ى/g,'ي');
const pageUrl=(provider:Provider,item:Release)=>(provider==='spotify'?'https://open.spotify.com/':'https://play.anghami.com/')+item.kind+'/'+item.id;
const kindLabel=(kind:string,ar:boolean)=>({track:ar?'أغنية':'Track',song:ar?'أغنية':'Track',album:ar?'ألبوم':'Album',artist:ar?'فنان':'Artist',playlist:ar?'قائمة تشغيل':'Playlist'}[kind]||kind);
const itemKey=(item:Release)=>item.kind+'/'+item.id;

export function MusicServices({provider,ar}:{provider:Provider;ar:boolean}){
 const brand=provider==='spotify'?'Spotify':ar?'أنغامي':'Anghami';
 const [query,setQuery]=useState('');
 const [searched,setSearched]=useState('');
 const [matches,setMatches]=useState<Release[]>([]);
 const [busy,setBusy]=useState(false);
 const [indexUnavailable,setIndexUnavailable]=useState(false);
 const [error,setError]=useState('');
 const [selection,setSelection]=useState<{embed:Embed;title:string;artist?:string}>();
 const pending=useRef<AbortController>();
 const player=useRef<HTMLElement>(null);
 useEffect(()=>()=>pending.current?.abort(),[]);

 function select(item:Release){
  const embed=officialEmbed(pageUrl(provider,item),provider);
  if(!embed)return;
  setSelection({embed,title:item.title,artist:item.artist});
  requestAnimationFrame(()=>player.current?.focus());
 }

 async function search(event:FormEvent<HTMLFormElement>){
  event.preventDefault();
  const value=query.trim();
  if(value.length<2)return;
  if(!/^https?:\/\//i.test(value)&&value.length>100){
   setError(ar?'اكتب اسم أقصر للبحث.':'Enter a shorter search term.');return;
  }
  pending.current?.abort();
  const abort=new AbortController();
  pending.current=abort;
  setError('');setIndexUnavailable(false);setBusy(true);
  const isLink=/^https?:\/\//i.test(value);
  if(!isLink){
   const terms=normalize(value).split(/\s+/);
   setSearched(value);
   setMatches(featured[provider].filter(item=>{
    const look=normalize([item.title,item.artist,item.alias].filter(Boolean).join(' '));
    return terms.every(term=>look.includes(term));
   }));
  }
  try{
   if(isLink){
    const embed=officialEmbed(value,provider)||(provider==='anghami'?await resolveAnghami(value):undefined);
    if(abort.signal.aborted)return;
    if(!embed)throw new Error('Invalid link');
    setSelection({embed,title:brand});
    requestAnimationFrame(()=>player.current?.focus());
    return;
   }
   const market=(navigator.language.match(/-([a-z]{2})$/i)?.[1]||'SA').toUpperCase();
   const params=new URLSearchParams({provider,q:value,market});
   const result=await requestJSON<{items:Release[];source:string}>('/v1/music/discover?'+params,{signal:abort.signal});
   if(abort.signal.aborted)return;
   setIndexUnavailable(result.source==='unavailable');
   setMatches(local=>[...new Map([...local,...result.items].map(item=>[itemKey(item),item])).values()]);
  }catch{
   if(!abort.signal.aborted){
    if(isLink)setError(ar?'الرابط مش مدعوم. جرّب البحث باسم الأغنية أو الفنان.':'That link is unsupported. Try a song or artist name.');
    else setIndexUnavailable(true);
   }
  }finally{if(!abort.signal.aborted)setBusy(false);}
 }

 function clear(){
  pending.current?.abort();
  setQuery('');setSearched('');setMatches([]);setBusy(false);setError('');setIndexUnavailable(false);
 }

 const items=searched?matches:featured[provider];
 const providerSearch=provider==='spotify'
  ?'https://open.spotify.com/search/'+encodeURIComponent(searched)
  :'https://www.google.com/search?q='+encodeURIComponent('site:play.anghami.com '+searched);
 return <section className="bm-service" data-provider={provider} aria-label={brand}>
  <header className="bm-service-intro">
   <div className="bm-service-icon" aria-hidden="true"><Headphones size={28}/></div>
   <div><h2>{brand}</h2><p>{ar?'ابحث باسم أغنية أو فنان أو ألبوم.':'Find a song, artist, or album by name.'}</p></div>
  </header>
  <form className="bm-service-form" onSubmit={e=>void search(e)}>
   <label htmlFor={'barq-'+provider+'-search'}>{ar?'البحث في ':'Search '}{brand}</label>
   <div className="bm-service-search"><Search size={20} aria-hidden="true"/>
    <input id={'barq-'+provider+'-search'} dir="auto" type="search" maxLength={650} value={query} onChange={e=>setQuery(e.target.value)}
      placeholder={ar?'أغنية، فنان، ألبوم…':'Song, artist, album…'}/>
    {query&&<button className="bm-search-clear" type="button" onClick={clear} aria-label={ar?'مسح البحث':'Clear search'}><X size={17}/></button>}
    <button className="bm-search-submit" disabled={query.trim().length<2} type="submit">{ar?'ابحث':'Search'}</button>
   </div>
  </form>
  {error&&<p className="bm-service-error" role="alert">{error}</p>}
  <div className="bm-discovery">
   <section className="bm-releases" aria-busy={busy}>
    <h3>{searched?(ar?'نتائج البحث':'Search results'):(ar?'اختيارات للاستماع':'Featured picks')}</h3>
    {busy&&<p className="bm-discovery-status" role="status">{ar?'جاري البحث…':'Searching…'}</p>}
    {!busy&&searched&&!items.length&&<p className="bm-discovery-status">{ar?'مفيش نتائج للاسم ده.':'No results for this name.'}</p>}
    {indexUnavailable&&<p className="bm-discovery-status" role="status">{ar?'البحث الموسّع مش متاح دلوقتي.':'Extended search is temporarily unavailable.'}</p>}
    <div className="bm-release-list">
     {items.map(item=><button type="button" className="bm-release" key={itemKey(item)} aria-pressed={selection?.embed.page===pageUrl(provider,item)} onClick={()=>select(item)}>
      <span className="bm-release-art">{item.artwork?<img src={item.artwork} alt="" loading="lazy"/>:<Music2 size={19} aria-hidden="true"/>}</span>
      <span className="bm-release-copy"><strong dir="auto">{item.title}</strong><small>{item.artist?item.artist+' · ':''}{kindLabel(item.kind,ar)}</small></span>
      <Play size={17} aria-hidden="true"/>
     </button>)}
    </div>
    {searched&&<a className="bm-provider-link" href={providerSearch} target="_blank" rel="noopener noreferrer"><ExternalLink size={15}/>{provider==='spotify'?(ar?'بحث على Spotify':'Search on Spotify'):(ar?'نتائج أنغامي على الويب':'Anghami results on the web')}</a>}
   </section>
   <section ref={player} tabIndex={-1} className="bm-service-player" aria-label={ar?'المشغّل الرسمي':'Official player'}>
    {selection?<><div className="bm-service-player-title">
     <div><strong dir="auto">{selection.title}</strong>{selection.artist&&<small dir="auto">{selection.artist}</small>}</div>
     <a href={selection.embed.page} target="_blank" rel="noopener noreferrer"><ExternalLink size={15}/>{ar?'افتح في الخدمة':'Open in service'}</a>
    </div>
    <iframe key={selection.embed.src} src={selection.embed.src+(provider==='anghami'?'?theme=fulldark&layout=wide&lang='+(ar?'ar':'en'):'')} title={selection.embed.title+' '+selection.embed.kind+' player'}
     allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture" referrerPolicy="strict-origin-when-cross-origin"/>
    </>:<div className="bm-service-empty"><Headphones size={30}/><p>{ar?'اختار نتيجة علشان تفتح المشغّل.':'Select a result to open the player.'}</p></div>}
   </section>
  </div>
 </section>;
}
