import {stopSpeechPlayback} from './lib/speechGlow';
import {useCallback,useEffect,useState} from 'react';
import {Trash2} from 'lucide-react';
import {ApprovalDialog} from './components/chat/ApprovalDialog';
import {ComputerControlStatus} from './components/workspace/ComputerControlStatus';
import {startDataSync} from './lib/sync';
import {deleteConversation, type RouterProvider} from './lib/backend';
import {useApp} from './store';import {useT} from './i18n';
import {RightPanel} from './components/layout/RightPanel';
import {OperationsHeader,OperationsRail,ConversationHeader} from './components/layout/OperationsFrame';import {SettingsModal,shortcuts} from './components/layout/SettingsModal';
import {EmptyState} from './components/chat/EmptyState';import {MessageList} from './components/chat/MessageList';import {BrainStatus} from './components/chat/BrainStatus';import {Composer} from './components/chat/Composer';
import {HandsFreeVoice,isHandsFreeActive} from './components/chat/HandsFreeVoice';
import {BarqOne,sections,type OnePage} from './pages/BarqOne';
import './styles/experienceRefresh.css';
import './styles/barqVisualSystem.css';
import {keepAppContextFresh,publishBookCatalogue,trackSection,type AppAction} from './lib/appContext';
import {publishedBooks} from './pages/publishedBooks';
import {VoiceResultsStrip} from './components/chat/VoiceResultsStrip';
import {Modal} from './components/ui/Modal';import {Button} from './components/ui/Button';import {ToastViewport} from './components/ui/Toast';import {LauncherPalette} from './components/launcher/LauncherPalette';import {CommandPalette} from './components/ui/CommandPalette';import {Playground} from './pages/Playground';
// Permission snapshot is kept up to date while the app is alive. We start
// the microphone synchronously in the user's click/key event so browsers do
// not block AudioContext after awaiting an HTTP permission request.
let consentedComputerVoice=false;
async function refreshComputerVoiceConsent(){
 let allowed=false;
 try{
  const [pc,wake]=await Promise.all([
   fetch('/v1/computer/status',{cache:'no-store'}),
   fetch('/v1/voice/wake/control',{cache:'no-store'})
  ]);
  if(pc.ok&&wake.ok){
   const p=await pc.json() as {supported?:boolean;settings?:{enabled?:boolean}};
   const w=await wake.json() as {wake_computer_enabled?:boolean};
   allowed=!!(p.supported&&p.settings?.enabled&&w.wake_computer_enabled);
  }
 }catch{/* Fail closed. */}
 consentedComputerVoice=allowed;
}
function openConsentedVoiceSession(){
 window.dispatchEvent(new CustomEvent('barq-handsfree-start',{detail:{computerEnabled:consentedComputerVoice}}));
}
export default function App(){
 const theme=useApp(s=>s.theme),language=useApp(s=>s.language),id=useApp(s=>s.activeId),chat=useApp(s=>s.chats.find(c=>c.id===s.activeId)),newChat=useApp(s=>s.newChat),deleteChat=useApp(s=>s.deleteChat),setSidebarOpen=useApp(s=>s.setSidebarOpen),streaming=useApp(s=>s.streaming);
 const [onePage,setOnePage]=useState<OnePage>('center');
 const [lastMedia,setLastMedia]=useState<'watch'|'music'>();
 const media=onePage==='watch'||onePage==='music'?onePage:lastMedia;
 useEffect(()=>{if(onePage==='watch'||onePage==='music')setLastMedia(onePage)},[onePage]);
 const [providers,setProviders]=useState<RouterProvider[]>([]);
 const [settingsTab,setSettingsTab]=useState<'general'|'models'|'voice'|'workspace'|'performance'|'assistant'>('general');const [settings,setSettings]=useState(false),[palette,setPalette]=useState(false),[shortcutsOpen,setShortcutsOpen]=useState(false),[deleteId,setDeleteId]=useState<string|null>(null),[prefill,setPrefill]=useState('');
 const [launcherOpen,setLauncherOpen]=useState(false),[launcherQuery,setLauncherQuery]=useState('');
 const [playground,setPlayground]=useState(window.location.pathname==='/playground');const t=useT();
 useEffect(()=>startDataSync(setProviders),[]);
 useEffect(()=>keepAppContextFresh(),[]);
 useEffect(()=>{
  const names=Object.fromEntries(sections.map(([key,ar,en])=>[key,language==='ar'?ar:en]));
  trackSection(playground?'playground':settings?'settings':onePage,{...names,playground:'Playground'});
 },[onePage,playground,language,settings]);
 useEffect(()=>{
  publishBookCatalogue([
   ...publishedBooks.map(book=>({title:book.title,label:book.author})),
  ]);
 },[]);
 useEffect(()=>{
  const open=(event:Event)=>{
   const action=(event as CustomEvent<AppAction>).detail;
   if(!action||!sections.some(([key])=>key===action.section))return;
   setSettings(false);setPlayground(false);setOnePage(action.section as OnePage);
   if(action.section==='settings')setSettingsTab('general');
   if(action.section==='music'&&action.mode)window.dispatchEvent(new CustomEvent('barq-music-mode',{detail:action.mode}));
  };
  window.addEventListener('barq-app-navigate',open);
  return()=>window.removeEventListener('barq-app-navigate',open);
 },[]);

 useEffect(()=>{
  void refreshComputerVoiceConsent();
  const onFocus=()=>{void refreshComputerVoiceConsent()};
  const onConsent=(event:Event)=>{
   // Server checks desktop permissions again when the Live connection opens.
   consentedComputerVoice=!!(event as CustomEvent<{enabled:boolean}>).detail?.enabled;
  };
  window.addEventListener('focus',onFocus);
  window.addEventListener('barq-voice-computer-permission-updated',onConsent);
  return()=>{window.removeEventListener('focus',onFocus);window.removeEventListener('barq-voice-computer-permission-updated',onConsent)};
 },[]);
 useEffect(()=>{
  const show=()=>{setPlayground(false);setOnePage('chat');};
  const route=(event:Event)=>{
   const text=(event as CustomEvent<{text?:string}>).detail?.text;
   setPlayground(false);setOnePage('chat');if(text?.trim())setPrefill(text);
  };
  window.addEventListener('barq-open-workspace',show);
  const openModels=()=>{setSettingsTab('models');setSettings(true)};
  window.addEventListener('barq-model-settings',openModels);
  window.addEventListener('barq-chat-prefill',route);
  return()=>{window.removeEventListener('barq-model-settings',openModels);window.removeEventListener('barq-open-workspace',show);window.removeEventListener('barq-chat-prefill',route)};
 },[]);
 useEffect(()=>{
  let alive=true, fetching=false, sequence=0;
  const stopSpeech=()=>stopSpeechPlayback();window.addEventListener('barq-handsfree-stop',stopSpeech);
  const open=()=>{if(!isHandsFreeActive())openConsentedVoiceSession()};
  window.addEventListener('barq-start-live-voice',open);
  const check=async()=>{
   if(!alive||fetching)return;fetching=true;
   try{
    const res=await fetch(`/v1/voice/wake/pending?since=${sequence}`,{cache:'no-store'});
    if(!res.ok)return;
    const event=await res.json() as {sequence:number;wake:boolean;computer_enabled?:boolean};
    if(!alive)return;
    sequence=Math.max(sequence,event.sequence);
    if(event.wake&&!isHandsFreeActive()){setSettings(false);setPlayground(false);setOnePage('voice');window.dispatchEvent(new CustomEvent('barq-handsfree-start',{detail:{computerEnabled:!!event.computer_enabled}}))}
   }catch{/* Local server may be restarting. */}finally{fetching=false}
  };
  const nativeWake=()=>{void check()};window.addEventListener('barq-native-wake',nativeWake);
  void check();const timer=window.setInterval(()=>{if(!isHandsFreeActive())void check();},1200);
  return()=>{alive=false;window.clearInterval(timer);window.removeEventListener('barq-start-live-voice',open);window.removeEventListener('barq-native-wake',nativeWake);window.removeEventListener('barq-handsfree-stop',stopSpeech)};
 },[]);
 useEffect(()=>{
  let alive=true,busy=false;
  const poll=async()=>{if(busy)return;busy=true;try{const response=await fetch('/v1/personal/notifications');if(response.ok){const data=await response.json() as {items:Array<{id:string;text:string}>};if(alive){for(const note of data.items)useApp.getState().toast('info','برق',note.text);if(data.items.length)await fetch('/v1/personal/notifications/ack',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:data.items.map(n=>n.id)})});}}}catch{}finally{busy=false}};
  const timer=window.setInterval(()=>void poll(),3000);return()=>{alive=false;window.clearInterval(timer)};
 },[]);
 const openPlayground=useCallback(()=>{history.pushState({},'', '/playground');setPlayground(true)},[]);
 const closePlayground=useCallback(()=>{history.pushState({},'','/');setPlayground(false)},[]);
 useEffect(()=>{const pop=()=>setPlayground(window.location.pathname==='/playground');window.addEventListener('popstate',pop);return()=>window.removeEventListener('popstate',pop)},[]);
 useEffect(()=>{document.documentElement.dataset.theme=theme;document.documentElement.lang=language;document.documentElement.dir=language==='ar'?'rtl':'ltr';document.querySelector('meta[name="theme-color"]')?.setAttribute('content',theme==='dark'?'#100D14':'#F8F4F6')},[theme,language]);
 useEffect(()=>{const handle=(e:Event)=>{setLauncherQuery((e as CustomEvent<{query?:string}>).detail?.query||'');setLauncherOpen(true)};window.addEventListener('barq-launcher-open',handle);return()=>window.removeEventListener('barq-launcher-open',handle)},[]);
 useEffect(()=>{const key=(e:KeyboardEvent)=>{
  if(e.ctrlKey&&e.altKey&&e.key.toLowerCase()==='b'){e.preventDefault();setSettings(false);if(isHandsFreeActive())window.dispatchEvent(new Event('barq-handsfree-stop'));else openConsentedVoiceSession();return}
  if((e.ctrlKey||e.metaKey)&&e.code==='Space'){e.preventDefault();setLauncherQuery('');setLauncherOpen(v=>!v)}
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();setPalette(v=>!v)}
  if((e.ctrlKey||e.metaKey)&&e.shiftKey&&e.key.toLowerCase()==='o'){e.preventDefault();newChat();setOnePage('chat');setSidebarOpen(false)}
  if((e.ctrlKey||e.metaKey)&&e.key==='/'){e.preventDefault();setShortcutsOpen(true)}
  if(e.key==='Escape'){setLauncherOpen(false);setPalette(false);setSidebarOpen(false)}
 };window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key)},[newChat,setSidebarOpen]);
 const confirmDelete=useCallback(()=>{if(deleteId&&!streaming){const target=deleteId;void deleteConversation(target).then(()=>{deleteChat(target);setDeleteId(null)}).catch(error=>useApp.getState().toast('error','Could not delete chat',error instanceof Error?error.message:'API unavailable'))}},[deleteId,streaming,deleteChat]);
 const navigateOne=(page:OnePage)=>{
  if(page==='settings'){setSettingsTab('general');setSettings(false);}
  setOnePage(page);setPlayground(false);
 };
 const renderSection=(page:Exclude<OnePage,'chat'|'settings'>)=><BarqOne page={page} providers={providers} onVoice={openConsentedVoiceSession} onNavigate={navigateOne}
   onModels={()=>{setSettingsTab('models');setSettings(true)}} onAssistantSettings={()=>{setSettingsTab('assistant');setSettings(true)}}
   onQuick={command=>{navigateOne('chat');setPrefill(command)}}/>;
 return <div data-release-marker="v2.41.14-build-gated-ui" className="ops-shell" dir={language==='ar'?'rtl':'ltr'}>
  <OperationsHeader page={onePage} navigate={navigateOne} search={()=>setPalette(true)} settings={()=>navigateOne('settings')}/>
  <div className={playground?'hidden':'ops-body'} dir="ltr">
   <OperationsRail page={onePage} navigate={navigateOne} newChat={()=>{newChat();navigateOne('chat')}} onDelete={setDeleteId} onPlayground={openPlayground}/>
   <main className={onePage==='chat'?'ops-stage ops-chat-stage':'ops-stage'} dir={language==='ar'?'rtl':'ltr'} aria-label={language==='ar'?'مساحة التطبيق':'Application workspace'}>
    {media&&<div hidden={onePage!==media} className="ops-media-page" key={media}>{renderSection(media)}</div>}
    {onePage==='settings'?<SettingsModal embedded open initialTab={settingsTab} onWorkspace={()=>navigateOne('chat')} onClose={()=>navigateOne('center')}/>
    :onePage!=='chat'?<>
      {onePage!=='watch'&&onePage!=='music'&&renderSection(onePage)}
      <VoiceResultsStrip/>
    </>:<>
      <ConversationHeader onDelete={()=>{if(id)setDeleteId(id)}} onVoice={()=>navigateOne('voice')} onNew={()=>{newChat();navigateOne('chat')}}/>
      <BrainStatus/>
      {chat&&chat.messages.length?<MessageList key={id} id={id!}/>:<EmptyState onSuggestion={setPrefill} onHologram={()=>navigateOne('voice')}/>}
      <VoiceResultsStrip/>
      <Composer prefill={prefill} onPrefillUsed={()=>setPrefill('')}/>
    </>}
   </main>
   {onePage==='chat'&&<RightPanel/>}
  </div>
  {playground&&<main className="min-w-0 flex-1"><Playground onBack={closePlayground}/></main>}
  <ComputerControlStatus/>
  <HandsFreeVoice/>
  <ToastViewport/>
  <ApprovalDialog enabled={!settings&&!shortcutsOpen&&!deleteId&&!launcherOpen&&!palette&&!playground}/>
  <SettingsModal open={settings} initialTab={settingsTab} onWorkspace={()=>{setSettings(false);setPlayground(false)}} onClose={()=>setSettings(false)}/>
  <LauncherPalette open={launcherOpen} initial={launcherQuery} onClose={()=>setLauncherOpen(false)}/>
  <CommandPalette open={palette} onClose={()=>setPalette(false)} onSettings={()=>setSettings(true)} onShortcuts={()=>setShortcutsOpen(true)} onPlayground={openPlayground}/>
  <Modal open={shortcutsOpen} onClose={()=>setShortcutsOpen(false)} title={t('shortcutsTitle')}><div className="space-y-3">{shortcuts.map(([shortcut,description])=><div key={shortcut} className="flex items-center justify-between gap-3 border-b border-stroke pb-2 text-sm"><span>{description}</span><kbd className="whitespace-nowrap rounded-sm border border-stroke bg-elevated px-2 py-1 font-mono text-xs">{shortcut}</kbd></div>)}</div></Modal>
  <Modal open={!!deleteId} onClose={()=>setDeleteId(null)} title={t('removeConfirm')} footer={<><Button variant="secondary" onClick={()=>setDeleteId(null)}>{t('cancel')}</Button><Button variant="danger" disabled={streaming} icon={<Trash2 size={16}/>} onClick={confirmDelete}>{t('confirm')}</Button></>}><p className="text-sm text-secondary">{t('removeDescription')} <strong>{useApp.getState().chats.find(c=>c.id===deleteId)?.title||''}</strong></p></Modal>
 </div>
}

