import {useEffect,useMemo,useRef,useState,type ChangeEvent} from 'react';
import {ArrowLeft,ArrowRight,BookOpen,Check,ChevronLeft,ChevronRight,Clock3,Feather,Headphones,Heart,Minus,Pause,Play,Plus,Search,Sparkles,Square,Upload,WandSparkles,X} from 'lucide-react';
import {streamChat} from '../lib/backend';
import {useApp,uid,type Message} from '../store';
import {Modal} from '../components/ui/Modal';
import {originals,type BarqStory,type StoryChapter,type StoryMood} from './barqStoriesData';
import './barqStories.css';

type Shelf={stories:BarqStory[];favorites:string[];progress:Record<string,number>};
const KEY='barq-stories-v1';
const genres=['الكل','فانتازيا','غموض','خيال علمي','مغامرة','رعب','مكتبتي'];
const covers:StoryMood[]=['ember','ocean','violet','gold','forest'];
function readShelf():Shelf{
 try{
  const data=JSON.parse(localStorage.getItem(KEY)||'{}') as Partial<Shelf>;
  return {stories:(Array.isArray(data.stories)?data.stories:[]).filter(s=>s&&typeof s.id==='string'&&typeof s.title==='string'&&Array.isArray(s.chapters)&&s.chapters.every(c=>typeof c.body==='string'&&typeof c.title==='string')).slice(0,80),
   favorites:(Array.isArray(data.favorites)?data.favorites:[]).filter((x):x is string=>typeof x==='string'),
   progress:data.progress&&typeof data.progress==='object'?data.progress:{}};
 }catch{return {stories:[],favorites:[],progress:{}}}
}
function Cover({story,mini=false}:{story:BarqStory;mini?:boolean}){
 return <div className={'bs-cover bs-'+story.mood+(mini?' bs-mini':'')} aria-hidden="true">
  <div className="bs-art-horizon"/><div className="bs-art-sun"/><div className="bs-art-arch"/><div className="bs-art-spires"/>
  <div className="bs-cover-copy"><span>BARQ STORIES</span><strong>{story.title}</strong><small>{story.genre}</small></div>
 </div>;
}
function parseChapter(text:string){
 const match=text.match(/\{[\s\S]*\}/);
 if(!match)throw new Error('برق ما رجعش فصل منسّق. جرّب تاني.');
 let data:Record<string,unknown>;
 try{data=JSON.parse(match[0]) as Record<string,unknown>}catch{throw new Error('الفصل اللي رجعه النموذج مش مكتمل. جرّب تاني.')}
 const title=typeof data.title==='string'?data.title.trim().slice(0,95):'فصل جديد';
 const body=typeof data.body==='string'?data.body.trim().slice(0,18000):'';
 const summary=typeof data.summary==='string'?data.summary.trim().slice(0,220):'';
 const choices=Array.isArray(data.choices)?data.choices.filter((x):x is string=>typeof x==='string').map(x=>x.slice(0,120)).slice(0,3):[];
 if(body.length<130)throw new Error('الرد قصير جدًا علشان يكون فصل قصة. جرّب نموذجًا تاني.');
 return {title,body,summary,choices};
}
export function BarqStories(){
 const ar=useApp(s=>s.language)==='ar',model=useApp(s=>s.selectedModel),voice=useApp(s=>s.voiceId);
 const [shelf,setShelf]=useState<Shelf>(readShelf);
 const [query,setQuery]=useState(''),[genre,setGenre]=useState('الكل'),[opened,setOpened]=useState<string|null>(null);
 const [creating,setCreating]=useState(false),[idea,setIdea]=useState(''),[ideaGenre,setIdeaGenre]=useState('فانتازيا');
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 const [font,setFont]=useState(19),[speaking,setSpeaking]=useState(false),[paused,setPaused]=useState(false);
 const fileInput=useRef<HTMLInputElement>(null),reader=useRef<HTMLElement>(null);
 const abortAI=useRef<AbortController|null>(null),abortSpeech=useRef<AbortController|null>(null);
 const playingAudio=useRef<HTMLAudioElement|null>(null),turn=useRef(0);
 const items=useMemo(()=>[...shelf.stories,...originals.filter(x=>!shelf.stories.some(s=>s.id===x.id))],[shelf.stories]);
 const book=items.find(x=>x.id===opened);
 const currentIndex=book?Math.max(0,Math.min(book.chapters.length-1,shelf.progress[book.id]||0)):0;
 const chapter=book?.chapters[currentIndex];
 const matches=items.filter(x=>(genre==='الكل'||(genre==='مكتبتي'?x.source!=='original':x.genre===genre))&&(x.title+' '+x.summary).toLowerCase().includes(query.trim().toLowerCase()));
 const recents=items.filter(s=>(shelf.progress[s.id]||0)>0);
 const label=(a:string,b:string)=>ar?a:b;
 useEffect(()=>{try{localStorage.setItem(KEY,JSON.stringify(shelf))}catch{setError('مش قادر أحفظ المكتبة محليًا. راجع المساحة المتاحة على الجهاز.')}},[shelf]);
 useEffect(()=>()=>{abortAI.current?.abort();abortSpeech.current?.abort();playingAudio.current?.pause()},[]);
 function stopVoice(){
  turn.current++;abortSpeech.current?.abort();abortSpeech.current=null;
  const active=playingAudio.current;
  if(active){active.pause();active.dispatchEvent(new Event('ended'));playingAudio.current=null;}
  setSpeaking(false);setPaused(false);
 }
 function openBook(id:string){stopVoice();setError('');setOpened(id);}
 function changeChapter(delta:number){
  if(!book)return;stopVoice();const next=Math.min(book.chapters.length-1,Math.max(0,currentIndex+delta));
  setShelf(prev=>({...prev,progress:{...prev.progress,[book.id]:next}}));reader.current?.scrollTo({top:0,behavior:'smooth'});
 }
 function fav(id:string){setShelf(prev=>({...prev,favorites:prev.favorites.includes(id)?prev.favorites.filter(x=>x!==id):[...prev.favorites,id]}))}
 function saveStory(story:BarqStory){setShelf(prev=>({...prev,stories:[story,...prev.stories.filter(x=>x.id!==story.id)].slice(0,80),progress:{...prev.progress,[story.id]:0}}));setCreating(false);setOpened(story.id);setNotice('الحكاية اتحفظت في مكتبتك.')}
 async function importText(event:ChangeEvent<HTMLInputElement>){
  const file=event.target.files?.[0];event.target.value='';if(!file)return;
  try{
   if(!/\.txt$/i.test(file.name)||file.size>160000)throw new Error('اختار ملف TXT أصغر من 160 كيلوبايت.');
   const body=(await file.text()).trim();if(body.length<100)throw new Error('الملف قصير جدًا علشان يكون قصة.');
   const chapters:StoryChapter[]=[];
   for(let i=0;i<body.length;i+=6500)chapters.push({title:'الفصل '+(chapters.length+1),body:body.slice(i,i+6500)});
   if(chapters.length>28)throw new Error('الكتاب طويل جدًا. استورد نسخة مختصرة.');
   saveStory({id:uid(),title:file.name.replace(/\.txt$/i,'').slice(0,80),summary:'قصة من مكتبتك الشخصية',genre:'مغامرة',mood:'gold',author:'مكتبتي',source:'imported',chapters});
  }catch(e){setError(e instanceof Error?e.message:'فشل استيراد القصة')}
 }
 async function generate(instruction:string){
  const controller=new AbortController();abortAI.current=controller;setBusy(true);setError('');
  try{
   const message:Message={id:uid(),role:'user',content:instruction,createdAt:Date.now()};
   let answer='';
   for await(const part of streamChat([message],model,{systemPrompt:'أنت مؤلف عربي محترف. التزم بنفس الشخصيات وتسلسل الأحداث. استجب بـ JSON صالح فقط بدون Markdown، المفاتيح: title, summary, body, choices. body فصل قصصي مفصل وchoices ثلاث اختيارات قصيرة.',localOnly:false,temperature:.85,maxTokens:3400},controller.signal)){
    if(part.type==='token')answer+=part.value;
    if(answer.length>70000)throw new Error('الرد أطول من المتوقع');
   }
   return parseChapter(answer);
  }finally{if(abortAI.current===controller)abortAI.current=null;setBusy(false)}
 }
 async function create(){
  if(idea.trim().length<12){setError('اكتب فكرة للقصة من 12 حرف على الأقل.');return}
  try{
   const result=await generate('اكتب الفصل الأول لقصة أصلية نوعها '+ideaGenre+'. الفكرة: '+idea.trim().slice(0,1100)+'. مطلوب فصل غني بالتفاصيل، شخصيات حقيقية، نهاية مشوقة واختيارات تقود لفصول تالية.');
   saveStory({id:uid(),title:result.title,summary:result.summary||idea.slice(0,160),genre:ideaGenre,mood:covers[Math.floor(Math.random()*covers.length)],author:'أنا وبرق',source:'custom',chapters:[{title:'الفصل الأول',body:result.body,choices:result.choices}]});setIdea('');
  }catch(e){if((e as Error).name!=='AbortError')setError(e instanceof Error?e.message:'فشل كتابة القصة');}
 }
 async function continueWith(choice:string){
  if(!book||!chapter)return;
  try{
   const result=await generate('كمّل القصة "'+book.title+'" نوعها '+book.genre+'. آخر فصل: '+chapter.body.slice(-4000)+'. القارئ قرر: '+choice+'. اكتب فصل جديد بمنطق مرتبط بالفصل السابق، وفي النهاية 3 اختيارات.');
   const next=book.chapters.length;
   const updated:BarqStory={...book,source:'custom',chapters:[...book.chapters,{title:result.title,body:result.body,choices:result.choices}]};
   stopVoice();
   setShelf(prev=>({...prev,stories:[updated,...prev.stories.filter(s=>s.id!==book.id)],progress:{...prev.progress,[book.id]:next}}));
   reader.current?.scrollTo({top:0,behavior:'smooth'});setNotice('برق كتب فصل جديد بناءً على اختيارك.');
  }catch(e){if((e as Error).name!=='AbortError')setError(e instanceof Error?e.message:'مش قادر أكمّل الحكاية');}
 }
 async function narrate(){
  if(!chapter)return;stopVoice();const ticket=turn.current;const ctrl=new AbortController();abortSpeech.current=ctrl;setSpeaking(true);setPaused(false);setError('');
  try{
   const pieces=chapter.body.match(/[\s\S]{1,720}/g)||[];
   for(const piece of pieces){
    if(ctrl.signal.aborted||ticket!==turn.current)break;
    const result=await fetch('/v1/voice/speak',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:piece,voice}),signal:ctrl.signal});
    if(!result.ok){const body=await result.json().catch(()=>({detail:'الصوت مش متاح'})) as {detail?:string};throw new Error(body.detail||'الصوت مش متاح')}
    const url=URL.createObjectURL(await result.blob());if(ctrl.signal.aborted){URL.revokeObjectURL(url);break}
    await new Promise<void>((resolve,reject)=>{
     const el=new Audio(url);playingAudio.current=el;let finished=false;
     const done=(issue?:Error)=>{if(finished)return;finished=true;el.onended=null;el.onerror=null;URL.revokeObjectURL(url);if(playingAudio.current===el)playingAudio.current=null;issue?reject(issue):resolve()};
     el.onended=()=>done();el.onerror=()=>done(new Error('تعذّر تشغيل الصوت'));
     el.play().catch(err=>done(err instanceof Error?err:new Error('المتصفح منع الصوت')));
     if(ctrl.signal.aborted)done();
    });
   }
  }catch(e){if(!ctrl.signal.aborted&&ticket===turn.current)setError(e instanceof Error?e.message:'تعذّر قراءة القصة بصوت برق')}
  finally{if(ticket===turn.current){setSpeaking(false);setPaused(false);abortSpeech.current=null}}
 }
 function togglePause(){
  const el=playingAudio.current;if(!el)return;
  if(el.paused)void el.play().then(()=>setPaused(false)).catch(()=>setError('اضغط على تشغيل للسماح بالصوت'));
  else{el.pause();setPaused(true)}
 }
 return <div className="bs-hub" dir={ar?'rtl':'ltr'}>
  <header className="bs-header"><div className="bs-brand"><span className="bs-brand-mark"><BookOpen size={22}/></span><div><small>BARQ ORIGINALS</small><strong>{label('حكايات برق','BARQ STORIES')}</strong></div></div>
   <div className="bs-header-actions">{book&&<button onClick={()=>{stopVoice();setOpened(null)}} className="bs-muted-btn"><ArrowRight size={16}/>{label('رجوع للمكتبة','Back to library')}</button>}
    <button className="bs-muted-btn" onClick={()=>fileInput.current?.click()}><Upload size={16}/>{label('استيراد TXT','Import TXT')}</button>
    <button className="bs-primary" onClick={()=>{setError('');setCreating(true)}}><WandSparkles size={17}/>{label('اكتب مع برق','Create with BARQ')}</button></div>
  </header>
  <input type="file" hidden ref={fileInput} accept=".txt,text/plain" onChange={event=>void importText(event)}/>
  {error&&<div className="bs-alert" role="alert">{error}<button aria-label="Dismiss" onClick={()=>setError('')}><X size={16}/></button></div>}
  {notice&&<div className="bs-alert bs-alert-success" role="status"><Check size={17}/>{notice}<button aria-label="Dismiss" onClick={()=>setNotice('')}><X size={16}/></button></div>}
  {!book?<div className="bs-library">
   <section className="bs-hero">
    <div className="bs-hero-text"><span className="bs-kicker"><Sparkles size={14}/> STORIES BEYOND THE SCREEN</span><h1>{label('كل حكاية،','Every story,')}<br/><em>{label('عالم جديد.','a new world.')}</em></h1>
    <p>{label('اقرأ حكايات أصلية، اسمعها بصوت برق، واختار بنفسك اللي يحصل في الفصل اللي بعده.','Read original stories, listen with BARQ, and decide what happens next.')}</p>
    <div className="bs-hero-actions"><button className="bs-primary" onClick={()=>openBook(originals[0].id)}><Play size={17} fill="currentColor"/>{label('ابدأ الحكاية','Start reading')}</button>
     <button className="bs-outline" onClick={()=>setCreating(true)}><Feather size={17}/>{label('اكتب عالمك','Create your world')}</button></div>
    <div className="bs-hero-caption"><strong>{items.length.toString().padStart(2,'0')}</strong> {label('حكايات في مكتبتك','stories')} <i/><Headphones size={15}/> {label('بصوت برق','BARQ narration')}</div>
    </div>
    <button className="bs-feature" onClick={()=>openBook(originals[0].id)} aria-label={label('افتح قصة الأسبوع','Open featured story')}>
     <div className="bs-feature-book"><Cover story={originals[0]}/></div><span className="bs-feature-label">{label('قصة الأسبوع','FEATURED PICK')}<strong>{originals[0].title}</strong></span>
    </button>
   </section>
   {recents.length>0&&<section className="bs-continue"><div className="bs-title"><span>YOUR READING JOURNEY</span><h2>{label('كمّل من مكانك','Pick up where you left off')}</h2></div><div className="bs-continue-row">
    {recents.map(s=><button onClick={()=>openBook(s.id)} key={s.id} className="bs-resume"><Cover story={s} mini/><span><strong>{s.title}</strong><small>{label('الفصل','Chapter')} {(shelf.progress[s.id]||0)+1} / {s.chapters.length}</small><i><b style={{width:Math.round(((shelf.progress[s.id]||0)+1)/s.chapters.length*100)+'%'}}/></i></span><ChevronLeft size={19}/></button>)}
   </div></section>}
   <section className="bs-collection"><div className="bs-title-row"><div className="bs-title"><span>EXPLORE THE COLLECTION</span><h2>{label('اكتشف حكايتك الجاية','Find your next story')}</h2><p>{label('من الغموض للفانتازيا والخيال العلمي.','Fantasy, mystery, and new worlds.')}</p></div>
    <label className="bs-search"><Search size={18}/><input aria-label={label('ابحث في القصص','Search stories')} placeholder={label('ابحث عن حكاية...','Search stories...')} value={query} onChange={e=>setQuery(e.target.value)}/></label></div>
    <div className="bs-filters" role="group" aria-label={label('تصنيف القصص','Story categories')}>{genres.map(g=><button type="button" key={g} aria-pressed={genre===g} onClick={()=>setGenre(g)}>{g}</button>)}</div>
    {matches.length?<div className="bs-grid">{matches.map(s=><article className="bs-card" key={s.id}>
     <button className="bs-card-cover" type="button" onClick={()=>openBook(s.id)} aria-label={label('افتح ','Open ')+s.title}><Cover story={s}/><span className="bs-card-open"><BookOpen size={19}/></span></button>
     <div className="bs-card-copy"><div className="bs-card-meta"><span>{s.genre}</span><span><Clock3 size={13}/>{s.chapters.length} {label('فصل','chapters')}</span></div>
       <button className="bs-card-title" onClick={()=>openBook(s.id)}>{s.title}</button><p>{s.summary}</p>
       <div className="bs-card-footer"><button onClick={()=>openBook(s.id)}>{label('افتح الحكاية','Read story')}<ArrowLeft size={15}/></button>
        <button className="bs-favorite" aria-label={label('المفضلة','Favorite')} aria-pressed={shelf.favorites.includes(s.id)} onClick={()=>fav(s.id)}><Heart size={17} fill={shelf.favorites.includes(s.id)?'currentColor':'none'}/></button></div>
     </div>
    </article>)}</div>:<div className="bs-empty"><BookOpen size={32}/><strong>{label('مفيش حكايات مطابقة','No stories found')}</strong><p>{label('جرّب تصنيف أو بحث مختلف.','Try another search or category.')}</p></div>}
   </section></div>
  :<section className="bs-reader" ref={reader}>
    <aside className="bs-reader-sidebar"><Cover story={book}/><div className="bs-book-about"><span>{book.genre}</span><h2>{book.title}</h2><p>{book.summary}</p>
     <div className="bs-book-actions"><button onClick={()=>fav(book.id)} aria-pressed={shelf.favorites.includes(book.id)}><Heart size={16} fill={shelf.favorites.includes(book.id)?'currentColor':'none'}/>{label('المفضلة','Favorite')}</button></div>
    </div><div className="bs-chapters"><h3>{label('الفصول','Chapters')}</h3>{book.chapters.map((c,i)=><button type="button" key={i} aria-current={i===currentIndex?'step':undefined} onClick={()=>{stopVoice();setShelf(prev=>({...prev,progress:{...prev.progress,[book.id]:i}}))}}><span>{String(i+1).padStart(2,'0')}</span>{c.title}</button>)}</div>
   </aside>
   <div className="bs-reader-main">
    <div className="bs-reader-toolbar"><span><BookOpen size={16}/>{label('وضع القراءة','READING MODE')}</span>
     <div><button type="button" disabled={font<=15} onClick={()=>setFont(f=>f-1)} aria-label={label('تصغير الخط','Decrease font size')}><Minus size={17}/></button><span>{font}px</span><button type="button" disabled={font>=25} onClick={()=>setFont(f=>f+1)} aria-label={label('تكبير الخط','Increase font size')}><Plus size={17}/></button></div></div>
    <div className="bs-article"><div className="bs-chapter-label">{label('الفصل','CHAPTER')} {String(currentIndex+1).padStart(2,'0')} / {book.chapters.length}</div>
     <h1>{chapter?.title}</h1><div className="bs-chapter-decoration">✦ ━━━ ✦</div>
     <div className="bs-prose" lang="ar" dir="rtl" style={{fontSize:font+'px'}}>{chapter?.body.split(/\n\s*\n/g).map((paragraph,i)=><p key={i}>{paragraph}</p>)}</div>
     {chapter?.choices?.length? <div className="bs-choices"><div><Sparkles size={17}/><strong>{label('اختار طريق الحكاية','Choose what happens next')}</strong><small>{label('برق هيكتب فصل جديد بناءً على قرارك','BARQ writes the next chapter based on your decision')}</small></div>
       {chapter.choices.map(choice=><button key={choice} type="button" disabled={busy} onClick={()=>void continueWith(choice)}>{choice}<ChevronLeft size={17}/></button>)}{busy&&<p role="status">{label('برق بيكتب الفصل الجديد...','BARQ is writing your next chapter...')}</p>}
      </div>:null}
    </div>
    <div className="bs-reader-bottom"><button disabled={currentIndex===0} onClick={()=>changeChapter(-1)}><ChevronRight size={17}/>{label('الفصل السابق','Previous')}</button>
      <div className="bs-chapter-progress"><span style={{width:((currentIndex+1)/book.chapters.length*100)+'%'}}/></div>
      <button disabled={currentIndex===book.chapters.length-1} onClick={()=>changeChapter(1)}>{label('الفصل التالي','Next')}<ChevronLeft size={17}/></button></div>
   </div>
   <aside className="bs-reader-narrator"><div className="bs-narrator-icon"><Headphones size={30}/></div><span className="bs-kicker">BARQ VOICE</span><h3>{label('اسمع الحكاية','Listen to the story')}</h3><p>{label('برق يقرأ الفصل بصوته. تقدر توقف القراءة وتكمل من مكانك.','BARQ narrates your chapter. Pause and resume whenever you like.')}</p>
    <div className="bs-narrator-buttons">{speaking?<><button className="bs-primary" onClick={togglePause}>{paused?<Play size={17}/>:<Pause size={17}/>} {paused?label('كمّل','Resume'):label('إيقاف مؤقت','Pause')}</button><button onClick={stopVoice} className="bs-muted-btn"><Square size={16}/></button></>:<button className="bs-primary" onClick={()=>void narrate()}><Play size={17}/>{label('اسمع بصوت برق','Listen with BARQ')}</button>}</div>
    <div className="bs-voice-hint">{label('التشغيل بيحتاج ضبط خدمة الصوت في برق.','Requires BARQ voice service to be configured.')}</div>
   </aside>
   </section>}
  <Modal open={creating} onClose={()=>{if(!busy)setCreating(false)}} title={label('اصنع حكايتك مع برق','Create a story with BARQ')} wide>
   <form className="bs-create-modal" onSubmit={e=>{e.preventDefault();void create()}}><div className="bs-create-icon"><WandSparkles size={27}/></div>
    <p>{label('اختار نوع الحكاية واحكي لبرق فكرتك. هيكتب الفصل الأول وتقدر تختار مسار الفصول اللي بعده.','Pick a genre and describe your idea. BARQ writes chapter one and offers choices for what happens next.')}</p>
    <label>{label('النوع','Genre')}<select value={ideaGenre} onChange={e=>setIdeaGenre(e.target.value)}>{genres.filter(g=>!['الكل','مكتبتي'].includes(g)).map(g=><option key={g}>{g}</option>)}</select></label>
    <label>{label('فكرة الحكاية','Story idea')}<textarea rows={5} maxLength={1200} placeholder={label('مثلاً: مدينة بتختفي كل ليلة، وأنا آخر شخص فاكرها...','A city disappears every night, and I am the last person who remembers...')} value={idea} onChange={e=>setIdea(e.target.value)} required minLength={12}/></label>
    <div className="bs-create-actions"><button type="button" onClick={()=>{if(!busy)setCreating(false)}} disabled={busy} className="bs-muted-btn">{label('إلغاء','Cancel')}</button>
      <button type="submit" disabled={busy||idea.trim().length<12} className="bs-primary"><Sparkles size={16}/>{busy?label('برق بيكتب...','Writing...'):label('ابدأ التأليف','Create story')}</button></div>
   </form>
  </Modal>
 </div>;
}
