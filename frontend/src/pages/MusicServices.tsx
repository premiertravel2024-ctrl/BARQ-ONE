import {FormEvent,useState} from 'react';
import {ExternalLink,Headphones,Link2,Music2,Play} from 'lucide-react';
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
export function MusicServices({provider,ar}:{provider:Provider;ar:boolean}){
 const [link,setLink]=useState('');
 const [embed,setEmbed]=useState<Embed>();
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 async function openTrack(event:FormEvent<HTMLFormElement>){
  event.preventDefault();setError('');setBusy(true);
  try{
   let match=officialEmbed(link,provider);
   if(!match&&provider==='anghami')try{match=await resolveAnghami(link)}catch{/* Short URL service may be unavailable. */}
   if(!match){
    setEmbed(undefined);
    setError(ar?'الرابط مش مدعوم للمشغّل الداخلي. استخدم رابط الأغنية أو الألبوم الكامل من التطبيق الرسمي. روابط أنغامي المختصرة محتاجة خدمة الغرف تكون شغّالة.':'Unsupported embed URL. Use the full official track or album link; Anghami short links need the room service.');
    return;
   }
   setEmbed(match);
  }catch{setEmbed(undefined);setError(ar?'الرابط غير صحيح. انسخ رابط الأغنية الرسمي.':'Invalid link. Paste an official song URL.');}
  finally{setBusy(false);}
 }
 return <section className="bm-service" aria-label={provider==='spotify'?'Spotify player':'Anghami player'}>
  <div className="bm-service-intro">
    <span className="bm-service-icon"><Music2 size={23}/></span>
    <div><span className="bm-service-kicker">BARQ MUSIC · {provider.toUpperCase()}</span>
      <h3>{provider==='spotify'?'Spotify':'Anghami'}</h3>
      <p>{ar?'شغّل من المشغّل الرسمي داخل برق؛ التسجيل والاشتراك والصلاحيات بتفضل تابعة للخدمة نفسها.':'Listen through the official player inside BARQ. Login, subscription and playback availability are controlled by the provider.'}</p>
    </div>
  </div>
  <form className="bm-service-form" onSubmit={e=>void openTrack(e)}>
    <label htmlFor={'barq-'+provider+'-url'}><Link2 size={17}/>{ar?'رابط الأغنية أو القائمة':'Track or playlist link'}</label>
    <div><input id={'barq-'+provider+'-url'} type="url" inputMode="url" required dir="ltr" placeholder={provider==='spotify'?'https://open.spotify.com/track/...':'https://play.anghami.com/song/...'}
      value={link} onChange={e=>setLink(e.target.value)}/>
      <button disabled={busy||!link.trim()} type="submit"><Play size={16}/>{busy?(ar?'جاري الفتح':'Loading'):(ar?'فتح المشغّل':'Open player')}</button>
    </div>
  </form>
  {error&&<p className="bm-service-error" role="alert">{error}</p>}
  {embed?<div className="bm-service-player">
    <div className="bm-service-player-title"><span><Headphones size={16}/>{ar?'المشغّل الرسمي':'Official player'} · {embed.title}</span>
      <a href={embed.page} target="_blank" rel="noopener noreferrer"><ExternalLink size={15}/>{ar?'افتح في الخدمة':'Open in service'}</a>
    </div>
    <iframe src={embed.src} title={embed.title+' '+embed.kind+' player'} allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
      referrerPolicy="strict-origin-when-cross-origin" loading="lazy"/>
  </div>:<div className="bm-service-empty"><Music2 size={35}/><strong>{ar?'موسيقاك جوا برق':'Your music, in BARQ'}</strong>
    <p>{ar?'انسخ رابط من الخدمة واختر «فتح المشغّل» علشان يظهر هنا.':'Paste a supported service link to load its embedded player here.'}</p></div>}
  <small className="bm-service-disclaimer">{ar?'الأغاني مش بيتم نسخها أو تحميلها من Spotify أو أنغامي. التشغيل ممكن يحتاج حساب وتفاعل من المستخدم.':'No music is downloaded or copied from Spotify or Anghami; playback may require login and user interaction.'}</small>
 </section>;
}
