import {appSectionLabel,describeAppView,openAppSection,type AppAction,type AppEntry} from './appContext';
import {confirmLaunch,resolveLaunch,isLaunchCommand} from './launcher';
import {preparationStatus} from './agentOutcome';
import {performTaskAction,retryTaskPlan as retryAgentPlan} from './taskActions';
import {notifyUI} from './uiEvents';
import {streamChat,requestJSON,taskMessages,APIError} from './backend';
import {getAttachment,releaseAttachment} from './attachmentRegistry';
import {useApp,uid,type Message,type ToolRequest,type UploadedAttachment,type AgentPlan,type PendingCommand} from '../store';
let controller:AbortController|null=null;
let activeGenerationChat:string|null=null;
/** Opening a panel is a best-effort UI notification, never an agent operation.
 * Node-based smoke tests have no window; a broken view listener must not
 * turn an already prepared task into a failed task.
 */
function openWorkspaceSafely():void{notifyUI('barq-open-workspace')}

/**
 * Only short, single-purpose CPU temperature requests take the local fast
 * sensor path. Multi-part questions remain in the normal conversation flow
 * so no second question is accidentally discarded.
 */
function isStandaloneCpuTemperatureRequest(text:string):boolean{
 const normalized=text.normalize('NFKC').replace(/[أإآ]/g,'ا').trim().toLowerCase();
 if(!normalized||normalized.length>180||/[\r\n;؛]/.test(normalized))return false;
 if(!/(?:حرار|سخون|temperature|\btemp\b)/i.test(normalized))return false;
 if(!/(?:معالج|بروسيسور|\bcpu\b|processor)/i.test(normalized))return false;
 if((normalized.match(/[؟?]/g)||[]).length>1)return false;
 // Further commands and second questions are not consumed by a one-sensor route.
 if(/(?:\sو\s*(?:كمان|عايز|عاوز|قول|قولي|اشرح|ازاي|افتح|شغل|هات|و|هل|ايه|كم|قيس|اقرا|كام)|وبعدين|بعد كده|\b(?:and|then|also)\b)/i.test(normalized))return false;
 if(/(?:كارت الشاشة|كرت الشاشة|\bgpu\b|الرام|\bram\b|\bfps\b)/i.test(normalized))return false;
 return true;
}

type FeatureCommand={feature:'wallpapers'|'resources'|'watch';action:string};
function exactDesktopFeatureCommand(text:string):FeatureCommand|null {
 const normalized=text.normalize('NFKC').replace(/[أإآ]/g,'ا').replace(/ى/g,'ي')
  .toLowerCase().trim().replace(/^يا\s*برق[\s،,]*/,'').replace(/[.!؟?]+$/,'').trim();
 if(!normalized||normalized.length>90||/[\n\r;؛]/.test(normalized))return null;
 const patterns:[RegExp,FeatureCommand][]=[
  [/^(?:افتح|شغل|شغلي|شغللي|ابدأ|ابدء|open|start)\s+(?:الخلفيه الحيه|خلفيه حيه|lively|live wallpapers?)$/i,{feature:'wallpapers',action:'show'}],
  [/^(?:شغل|استأنف|كمل|resume|play)\s+(?:الخلفيه|الخلفيه الحيه|wallpaper)$/i,{feature:'wallpapers',action:'play'}],
  [/^(?:وقف|اوقف|اقفل|pause|stop)\s+(?:الخلفيه|الخلفيه الحيه|wallpaper)$/i,{feature:'wallpapers',action:'stop'}],
  [/^(?:اختار|حط|set|choose)\s+(?:خلفيه عشوائيه|random wallpaper)$/i,{feature:'wallpapers',action:'random'}],
  [/^(?:وريني|اعرض|شوف|show)\s+(?:العمليات|البرامج اللي شغاله|processes)$/i,{feature:'resources',action:'status'}],
  [/^(?:رجع|استرجع|استعيد|restore)\s+(?:البرامج|كل البرامج|all|everything)$/i,{feature:'resources',action:'restore'}],
  [/^(?:فعل|ابدأ|شغل|enable|start)\s+(?:وضع الالعاب|gaming mode)$/i,{feature:'resources',action:'gaming'}],
  [/^(?:فعل|ابدأ|شغل|enable|start)\s+(?:وضع التركيز|focus mode)$/i,{feature:'resources',action:'focus'}],
  [/^(?:فعل|ابدأ|شغل|enable|start)\s+(?:وضع توفير الموارد|وضع البطاريه|battery saver)$/i,{feature:'resources',action:'battery'}],
  [/^(?:فعل|ابدأ|شغل|enable|start)\s+(?:وضع الافلام|movie mode)$/i,{feature:'resources',action:'movie'}],
  [/^(?:ابدأ|افتح|شغل|start|open)\s+(?:غرفه مشاهده|watch room)$/i,{feature:'watch',action:'start'}],
 ];
 for(const [pattern,result] of patterns)if(pattern.test(normalized))return result;
 return null;
}

export async function submitChat(text:string,attachments:UploadedAttachment[]=[]){
  const state=useApp.getState();if(state.streaming||(!text.trim()&&!attachments.length))return;
  const id=state.activeId||state.newChat();
  const user:Message={id:uid(),role:'user',content:text.trim(),createdAt:Date.now(),attachments:attachments.map(a=>({...a,progress:100}))};
  state.addMessage(id,user);
  await generate(id);
}
export async function generate(id:string,retryCommandId?:string){
  const state=useApp.getState();if(state.streaming)return;
  const activeController=new AbortController();controller=activeController;const signal=activeController.signal;const assistantId=uid();
  const current=useApp.getState();const chat=current.chats.find(c=>c.id===id);if(!chat)return;
  activeGenerationChat=id;
  let brainRouted=false;
  const messages=chat.messages.filter(m=>!m.isStreaming);
  // Route only the USER'S explicit desktop/project action to a real agent.
  // This classification endpoint never executes commands; a separate explicit
  // commands, MCP calls and source changes still stop for approval; source
  // inspection follows a server-enforced read-only allowlist.
  current.setStreaming(true,assistantId);
  try{
  const last=messages.at(-1);
  if(last?.role==='user'&&!last.attachments?.length&&last.content.length<=240&&
     /^(?:(?:يا برق|برق|ممكن|لو سمحت|من فضلك|please)\s+)*(?:افتح|إفتح|روح|وديني|اعرض|ابحث|دور|هات|open|show|go to|find|search)/i.test(last.content.trim())){
    const decision=await requestJSON<{action?:AppAction;search?:{catalogue:string;query:string}}>('/v1/app-context/command?'+new URLSearchParams({text:last.content}),{signal}).catch(()=>null);
    if(signal.aborted)return;
    const ar=current.language==='ar';
    const reply=(content:string)=>current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),model:'BARQ-AI/local',offline:true,content});
    if(decision?.action&&openAppSection(decision.action)){
      const label=appSectionLabel(decision.action.section);
      reply(ar?'فتحت '+label+'.':'Opened '+label+'.');return;
    }
    if(decision?.search){
      const {catalogue,query}=decision.search;
      const result=await requestJSON<{status:string;items:AppEntry[]}>('/v1/app-context/search?'+new URLSearchParams({catalogue,q:query}),{signal}).catch(()=>null);
      if(signal.aborted)return;
      if(!result||result.status==='unavailable')reply(ar?'مصدر البحث ده مش متاح دلوقتي.':'This catalogue is currently unavailable.');
      else if(!result.items.length)reply(ar?'مفيش نتائج مطابقة في الكتالوج ده.':'No matches in this catalogue.');
      else reply((ar?'النتائج المتاحة':'Matching titles')+'\n'+result.items.map(item=>'- '+item.title+(item.label?' · '+item.label:'')).join('\n'));
      return;
    }
  }
  if(last?.role==='user'&&!last.attachments?.length&&
     /^(?:(?:يا برق|برق)\s+)*(?:انا|أنا)?\s*(?:فاتح [اإأ]يه|كنت فاتح [اإأ]يه|في قسم [اإأ]يه|what (?:section|page) (?:am i|was i) (?:in|on))(?:\s+(?:جوه برق|في برق|in BARQ))?[؟?!]*$/i.test(last.content.trim())){
    current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),model:'BARQ-AI/local',offline:true,
      content:describeAppView(current.language==='ar')});
    return;
  }
  const featureAction=last?.role==='user'&&!last.attachments?.length?exactDesktopFeatureCommand(last.content):null;
  if(featureAction){
    try{
      const response=await requestJSON<{status:string;message:string}>('/v1/features/command',{
        method:'POST',signal,body:JSON.stringify(featureAction)});
      if(signal.aborted)return;
      current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),model:'BARQ-AI/local',offline:true,content:response.message});
    }catch(error){
      if(signal.aborted)return;
      const info=error instanceof Error?error.message:String(error);
      current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),model:'BARQ-AI/local',offline:true,
        content:(current.language==='ar'?'الطلب محتاج صلاحية أو حصل خطأ في تنفيذ الميزة: ':'Feature requires authorization or failed: ')+info.slice(0,170)});
    }
    return;
  }
  if(last?.role==='user'&&!last.attachments?.length&&isStandaloneCpuTemperatureRequest(last.content)){
    try{
      const reading=await requestJSON<{cpu_c:number|null;cpu_sensor?:string|null;provider?:string|null;reason?:string|null}>('/v1/openhub/cpu-temperature',{signal});
      if(signal.aborted)return;
      const temperature=reading.cpu_c;
      const valid=typeof temperature==='number'&&Number.isFinite(temperature)&&temperature>0&&temperature<125;
      const ar=current.language==='ar';
      const result=valid
        ?(ar?`حرارة المعالج دلوقتي ${temperature.toFixed(1)} درجة مئوية، من ${reading.cpu_sensor||'حساس CPU'} عبر ${reading.provider||'LibreHardwareMonitor'}.`
          :`CPU temperature is ${temperature.toFixed(1)} °C (${reading.cpu_sensor||'CPU sensor'}, ${reading.provider||'LibreHardwareMonitor'}).`)
        :(ar?'مش لاقي قراءة مؤكدة لحرارة المعالج رغم إن الأداة ممكن تكون شغالة. افتح LibreHardwareMonitor ثم Options > Remote Web Server > Run مرة واحدة، وخليه شغال. برق هيقرأ CPU Package محليًا بدون WMI أو صلاحيات متكررة.'
          :'CPU temperature is unavailable. In LibreHardwareMonitor, enable Options > Remote Web Server > Run once and leave it running; BARQ will read the live CPU Package locally.');
      current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),model:'BARQ-AI/local',offline:true,content:result});
      return;
    }catch(error){
      if(signal.aborted)return;
      current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),model:'BARQ-AI/local',offline:true,
        content:current.language==='ar'?'واجهة قراءة الحرارة المحلية مش متاحة في نسخة برق الشغالة. حدّث التطبيق، وبعدها جرّب تاني. مش هخمن درجة حرارة المعالج.'
          :'The local sensor API is unavailable in this BARQ build. Update the app and retry; no temperature was guessed.'});
      return;
    }
  }
  if(last?.role==='user'&&!last.attachments?.length&&last.content.length<=420&&
     /(?:ثبت|ثبّت|سطب|نزل|نزّل|حمل|حمّل|install|download)/i.test(last.content)){
    try{
      const tool=await requestJSON<{matched:boolean;status?:string;message?:string}>('/v1/openhub/command',{
        method:'POST',signal,body:JSON.stringify({text:last.content})});
      if(tool.matched){
        current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),model:'BARQ-AI/local',content:tool.message||''});
        return;
      }
    }catch(error){if(!(error instanceof APIError)||error.status!==404)throw error;}
  }
  const personalText=(last?.content||'').normalize('NFKC').replace(/[أإآ]/g,'ا').replace(/ى/g,'ي').replace(/[\u064b-\u065fـ]/g,'');
  if(last?.role==='user'&&!last.attachments?.length&&last.content.length<=500&&/(?:احفظ المفضل|احفظ المفضلة|افتكر المفضل|افتكر المفضلة|افتكر ان اسمي|افتكر إن اسمي|افتكر اسمي|احفظ اسمي|راقب اداء|وقف مراقبة اللعب|جهزني|وضع اللعب|روتين|المفضل|المحدد|الحافظة|اخر تغيير|آخر تغيير|رجع اللي|وقف كل|التنزيل|التنزيلات|فكرني|المهام وصلت|حالة المهام|متابعة المهام|تابع البناء|اقرا الاشعارات|مكتوب فيه|محتواه|جواه|محتوي الملفات|وقف الاغني|وقف الأغني|كمل الاغني|كمل الأغني|الاغني.*(?:بعدها|السابقة)|الأغني.*(?:بعدها|السابقة)|^التالي$)/i.test(personalText)){
   const result=await requestJSON<{matched:boolean;status?:string;message?:string}>('/v1/personal/command',{method:'POST',signal,body:JSON.stringify({text:last.content})});
   if(result.matched){current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),model:'BARQ-AI/personal',content:result.message||'مفيش نتيجة مؤكدة.'});return;}
  }
  // Deterministic companion commands complete before any generic planning/model pass.
  if(last?.role==='user'&&!last.attachments?.length&&last.content.length<=500&&!/^(?:(?:يا برق|برق|ممكن|لو سمحت)\s+)*(?:افتح(?:لي)?|open)\s+(?:يوتيوب|اليوتيوب|youtube)[.!؟?\s]*$/i.test(last.content.trim())&&/^(?:(?:يا برق|برق|ممكن|لو سمحت|عاوزك|عايزك|please)\s+)*(?:شغل(?:لي|ي)?|افتح(?:لي)?|play|open|قيس(?:لي)?|تقيس(?:لي)?|احسب(?:لي)?|اسمع|عاوز اسمع|عايز اسمع|نفسي اسمع|تسمعني|حطلي|معدل|متوسط|اعرف|وريني|هات|كام|الفريمات|measure|show|check|what|بص|شوف|حلل|ساعدني|اديني|انصحني|تنصحني|رايك|رأيك|ايه رايك|ايه رأيك|help|analy[sz]e|advise)(?:\s|$)/i.test(last.content.trim())&&/(?:يوتيوب|youtube|أ?غني|اغاني|أغاني|موسيقى|موسيقي|مزيكا|song|music|فريم|fps|لعب|game|gaming)/i.test(last.content)){
   const companion=await requestJSON<{matched:boolean;status?:string;message?:string;model?:string;local?:boolean}>('/v1/computer/companion-command',{method:'POST',signal,body:JSON.stringify({text:last.content})});
   if(companion.matched){current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),model:companion.model||'BARQ-AI/local',offline:companion.local!==false,content:companion.message||'مفيش نتيجة مؤكدة.'});return;}
  }
  // A short direct command can approve the exact action already displayed in
  // this chat. The backend still validates its opaque pending-plan identifier.
  const previous=messages.at(-2);
  const pending=previous?.role==='assistant'?previous.agentTask:undefined;
  const runWord=/^(?:نفذ|نفّذ|نفذه|نفّذه|execute|do it)[.!؟?\s]*$/i;
  const saveWord=/^(?:احفظ|احفظه|احفظها|save|save it)[.!؟?\s]*$/i;
  const retryWord=/^(?:كمل|كمّل|حاول(?: تاني)?|جرّ?ب(?: تاني)?|استكمل|تابع|تابعها|كملها|كمّلها|استمر|continue|resume|retry)[.!؟?\s]*$/i;
  if(last?.role==='user'&&!last.attachments?.length&&pending&&
     ((pending.plan&&runWord.test(last.content.trim()))||(pending.pendingEdit&&saveWord.test(last.content.trim()))||((pending.retryId||pending.savedEdit)&&retryWord.test(last.content.trim())))){
    if(pending.retryId&&retryWord.test(last.content.trim()))await retryAgentPlan(id,previous!.id,true);
    else if(pending.savedEdit&&retryWord.test(last.content.trim()))await performTaskAction(id,previous!.id,'save',true);
    else if(pending.pendingEdit&&saveWord.test(last.content.trim()))await performTaskAction(id,previous!.id,'save',true,pending.pendingEdit.approval_id);
    else await performTaskAction(id,previous!.id,'execute',true,pending.plan!.plan_id);
    return;
  }

  // "افتح مساحة العمل" is an internal BARQ action, never a Windows app search.
  if(last?.role==='user'&&!last.attachments?.length &&
      /(?:افتح|افتحلي|وريني|اظهر|إظهار|روح|open|show)\s+(?:مساحة\s+(?:العمل|البرمجة)|الاستوديو|barq\s+studio|workspace)/i.test(last.content) &&
      !/(?:ابني|تبني|اعمل|تعمل|أنشئ|انشئ|اصنع|برمج|نفذ|نفّذ|build|create|make)/i.test(last.content)){
    openWorkspaceSafely();
    current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),content:'فتحتلك مساحة العمل. الأوامر والتعديلات بتفضل من الشات الأساسي، وهنا هتشوف الملفات والنتائج.',model:'BARQ-AI/local',offline:true});
    return;
  }
  // A user-pasted GitHub repository URL is a first-class coding handoff.
  // This opens an explicit preview; importing or installing never runs from chat text alone.
  if(last?.role==='user'&&!last.attachments?.length){
    const input=last.content.trim();
    const urls=input.match(/https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+(?:\.git)?\/?/gi)||[];
    // Tracking query strings (e.g. ?utm_source=chatgpt.com) do not turn
    // a direct GitHub URL into an unrelated chat prompt. Only the canonical
    // owner/repo URL is passed to the review UI; no automatic code execution.
    const directLink=/^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+(?:\.git)?\/?(?:\?[A-Za-z0-9_=%&.-]{1,200})?(?:#[A-Za-z0-9_-]+)?$/i.test(input);
    const importRequest=/(?:نزل|نزّل|حمل|حمّل|ثبت|ثبّت|استورد|استخدم|انسخ|clone|install|import|use this repo)/i.test(input);
    if(urls.length===1&&(directLink||importRequest)){
      current.setToolHandoff({integration:'coding',goal:urls[0],tab:'github'});
      openWorkspaceSafely();
      current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),model:'BARQ-AI/local',offline:true,
        content:'وصلني رابط GitHub. فتحت مدير المستودعات في مساحة العمل؛ هراجع الرابط والمكان الأول، وبعد موافقتك أنسخ الملفات، أفحص المتطلبات، وأجهز بيئة تشغيل منفصلة لو متاحة. مش هشغّل سكربتات المستودع من غير إذنك.'});
      return;
    }
  }
  if(last?.role==='user'&&!last.attachments?.length&&last.content.length<=500&&
     /^(?:(?:يا برق)\s+)?(?:دور|ابحث|شوف|هات|فين|find|search)/i.test(last.content.trim())&&/(?:ملف|فايل|فولدر|مجلد|جهاز|كمبيوتر|هارد|\bfile\b|\bfolder\b)/i.test(last.content)){
   const named=await requestJSON<{matched:boolean;message?:string}>('/v1/device/name-command',{method:'POST',signal,body:JSON.stringify({text:last.content,conversation_id:id})});
   if(named.matched){current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),content:named.message||'البحث لم يصل لنتيجة مؤكدة.',model:'BARQ-AI/local',offline:true});return;}
  }
  if(last?.role==='user'&&!last.attachments?.length&&/(?:شاش|screen)/i.test(last.content)&&/^(?:(?:يا برق|برق|ممكن|لو سمحت|please)\s+)*(?:شوف|اقرا|اقرأ|اعرض|read|look|see)(?:\s|$)/i.test(last.content.trim())){
   const screen=await requestJSON<{status:string;window:string;text:string;error?:string}>('/v1/computer/read-screen',{method:'POST',signal});
   current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),model:'BARQ-AI/local',offline:true,
    content:screen.status==='ok'?`النافذة: ${screen.window}\n\nالنص الظاهر:\n${screen.text}`:'لم أقدر أقرأ نصًا من النافذة الحالية. '+(screen.error||'')});return;
  }
  // Local movie workflows execute before generic agent classification so
  // search -> recommendation -> exact playback remains one grounded request.
  if(last?.role==='user'&&!last.attachments?.length&&last.content.length<=600&&
      (/(?:فيلم|افلام|أفلام|movie|video)/i.test(last.content)||(previous?.role==='assistant'&&previous.content.startsWith('اقتراحي من الموجود عندك:')&&/^(?:شغله|شغل (?:الاول|التاني|الثاني)|غيره|فيلم تاني|اختار غيره)$/i.test(last.content.trim())))){
   const media=await requestJSON<{matched:boolean;status?:string;message?:string;cards?:Array<{label:string;kind?:string;description?:string}>}>('/v1/device/media-command',{
    method:'POST',signal,body:JSON.stringify({text:last.content,conversation_id:id})});
   if(media.matched){if(media.cards?.length)notifyUI('barq-voice-local-cards',{cards:media.cards});current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),content:media.message||'مفيش نتيجة مؤكدة.',model:'BARQ-AI/local',offline:true});return;}
  }
  // User-written launch commands are resolved locally BEFORE the brain/router or any cloud call.
  // A missing path is never leaked as model context.
  if(last?.role==='user' && !last.attachments?.length && isLaunchCommand(last.content)){
    try{
      const launch=await resolveLaunch(last.content,'text');
      if(signal.aborted)return;
      if(launch.decision!=='not_command'&&(launch.decision!=='not_found'||['folder','file'].includes(launch.intent?.target_kind||''))){
        let reply=launch.text_ar||'مش قادر أحدّد المطلوب.';
        if(launch.decision==='auto'||launch.decision==='ask_approval'){
          const choice=launch.candidates[0];
          if(choice){const outcome=await confirmLaunch(choice.id);
            reply=outcome.status==='opened'?`تمام، فتحتلك ${choice.label}.`:outcome.reason||'التشغيل محتاج موافقة.';
          }
        }else if(launch.decision==='choose'){
          notifyUI('barq-launcher-open',{query:(launch.intent?.target_kind==='folder'?'فولدر ':launch.intent?.target_kind==='file'?'ملف ':'')+(launch.intent?.target_text||last.content)});
          reply+='\n'+launch.candidates.map((item,i)=>`${i+1}. ${item.label}${['folder','file'].includes(item.kind)?' — '+item.path_or_appid:''}`).join('\n');
        }
        current.addMessage(id,{id:uid(),role:'assistant',content:reply,createdAt:Date.now(),model:'BARQ-AI/local',offline:true});
        return;
      }
    }catch(error){
      current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),model:'BARQ-AI/local',offline:true,
        content:'مش قادر أشغّل الأمر دلوقتي. '+(error instanceof Error?error.message:'راجع إعدادات التحكم في الكمبيوتر.')});
      return;
    }
  }
  if((last?.role==='user'||retryCommandId)&&!last?.attachments?.length){
    const requestText=last?.content||'';
    const userAskedForAction=!!retryCommandId||retryWord.test(requestText.trim())||/(?:rea|ريا|الهندس[ةه]|حلله|حلّله|ابني|تبني|اعمل|اعملي|اعمللي|تعمل|تعملي|أنشئ|انشئ|اصنع|برمج|صمم|صمّم|نفّذ|نفذ|صلح|أصلح|افتح|شغل|عدّل|عدل|كمل|كمّل|طور|طوّر|ظبط|جهز|ابدأ|ابدا|اشتغل عليه|create|build|make|fix|run|execute|continue)/i.test(requestText);
    try{
      type Decision={intent:{kind:'coding'|'rea'|'computer';goal:string;requires_approval:boolean}|null;command_id?:string;pending_command?:PendingCommand;clarification?:string|null;reply?:string;tool_request?:ToolRequest|null};
      // Local rules are a fast path, never a vocabulary gate. Unrecognized
      // wording goes to contextual understanding before a normal chat reply.
      let decision:Decision={intent:null};
      try{
        const savedId=retryCommandId||(retryWord.test(requestText.trim())?previous?.pendingCommand?.id:undefined);
        decision=await requestJSON<Decision>(savedId?'/v1/brain/command/retry':'/v1/brain/command',{method:'POST',signal,body:JSON.stringify(savedId
          ?{conversation_id:id,command_id:savedId,model:current.options.localOnly?'local-only':current.selectedModel}
          :{conversation_id:id,workspace:current.workspace,model:current.options.localOnly?'local-only':current.selectedModel,
            messages:messages.slice(-24).map(m=>({role:m.role,content:m.content}))})});
        brainRouted=true;
        if(savedId){for(const item of messages){if(item.pendingCommand?.id===savedId)current.updateMessage(id,item.id,{pendingCommand:undefined})}}
      }catch(error){
        if(!(error instanceof APIError)||error.status!==404)throw error;
        // Compatibility with older backends; current releases use one durable intake.
        decision=await requestJSON<Decision>('/v1/agent/task-intent',{method:'POST',signal,body:JSON.stringify({
          text:requestText.slice(0,12000),previous_user_texts:messages.slice(0,-1).filter(m=>m.role==='user').slice(-8).map(m=>m.content.slice(0,4000))})});
        if(!decision.intent&&!decision.clarification){
        try{
          decision=await requestJSON<Decision>('/v1/brain/route',{method:'POST',signal,body:JSON.stringify({
            conversation_id:id,workspace:current.workspace,model:current.options.localOnly?'local-only':current.selectedModel,
            messages:messages.slice(-24).map(m=>({role:m.role,content:m.content}))})});
          brainRouted=true;
        }catch(error){if(!(error instanceof APIError)||error.status!==404)throw error;}
        }
      }
      if(decision.pending_command){
        current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),
          content:current.language==='ar'?'حفظت طلبك. السبب اللي موقف الخطوة ظاهر هنا، وتقدر تستكمل نفس الطلب.':'Your request is saved. Review the cause below and resume the same request.',pendingCommand:decision.pending_command});
        return;
      }
      if(decision.reply){current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),content:decision.reply,toolRequest:decision.tool_request||undefined});return}
      if(signal.aborted)return;
      if(decision.clarification){current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),content:current.language==='ar'?decision.clarification:'Which task should I continue? Specify the program or project.'});return}
      const intent=decision.intent;
      if(intent?.kind==='computer'){
        const started=await requestJSON<{id?:string;status?:string;message?:string}>('/v1/computer/start',{
          method:'POST',signal,body:JSON.stringify({conversation_id:id,goal:intent.goal,model:current.options.localOnly?'local-only':current.selectedModel})});
        current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),content:started.message||'بدأت تنفيذ الأمر على الكمبيوتر؛ التقدم الفعلي ظاهر في حالة المهمة.',
          agentTask:{commandId:decision.command_id,kind:'computer',taskId:started.id,goal:intent.goal,status:'running'}});
        return;
      }
      if(intent&&(intent.kind==='coding'||intent.kind==='rea')){
        // One command surface: pick a real workspace once, then prepare the task.
        // Opening the folder picker is not permission to edit or run code.
        let projectRoot=useApp.getState().workspace.trim();
        if(intent.kind==='coding'&&!projectRoot){
          try{
            const automatic=await requestJSON<{path:string}>('/v1/computer/work-area',{method:'POST',signal}).catch(()=>null);
            const selected=automatic||await requestJSON<{path:string}>('/v1/studio/pick-folder',{method:'POST',signal});
            if(selected.path?.trim()){
              projectRoot=selected.path.trim();
              useApp.getState().setWorkspace(projectRoot);
            }
          }catch(error){
            // Folder selection may be cancelled or unavailable outside Windows.
            if(signal.aborted)return;
          }
        }
        if(projectRoot){
          openWorkspaceSafely();
          try{
            type Prepared=AgentPlan&{preparation_results?:Array<{tool:string;success:boolean;result?:string;error?:string}>;failed?:boolean};
            const init={method:'POST',body:JSON.stringify({conversation_id:id,command_id:decision.command_id,workspace:projectRoot,model:current.options.localOnly?'local-only':current.selectedModel,
              messages:taskMessages(messages.slice(-24))}),signal};
            let plan:Prepared;
            try{plan=await requestJSON<Prepared>('/v1/agent/prepare',init)}
            catch(error){if(!(error instanceof APIError)||error.status!==404)throw error;
              plan=await requestJSON<Prepared>('/v1/agent/plan',init)}
            if(signal.aborted)return;
            const evidence=JSON.stringify(plan.preparation_results||[]).slice(0,32000);
            current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),content:plan.plan.steps.length
              ?(current.language==='ar'?'بدأت تجهيز البرنامج وفتحت مساحة العمل. أول خطوة جاهزة؛ راجعها ووافق عليها من الشات الأساسي.':'The workspace is ready. Review the first action in the main chat before approval.')
              :(plan.plan.answer||plan.plan.reason||''),
              agentTask:{commandId:decision.command_id,kind:'coding',autopilot:true,goal:intent.goal,status:preparationStatus(plan),retryId:plan.retry_id,
                taskId:plan.task_id,evidence,summary:plan.plan.answer,missionProgress:plan.mission_progress,plan:plan.plan.steps.length?plan:undefined}});
            // The code editor is a read-only visual workspace, not a second chat.
            return;
          }catch(error){
            if(signal.aborted)return;
            const reason=error instanceof Error?error.message:'Agent planning unavailable';
            current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),content:current.language==='ar'
              ?'لم يكتمل تجهيز المهمة. راجع السبب وتأكد من المشروع والأدوات المتصلة.'
              :'Task preparation did not finish. Check the cause, workspace and enabled tools.',
              agentTask:{kind:'coding',goal:intent.goal,status:'failed',summary:reason}});
            return;
          }
        }
        if(intent.kind==='coding'){
          current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),content:current.language==='ar'
            ?'اختار مجلد المشروع من بطاقة المهمة علشان أبدأ التنفيذ من الشات الأساسي. مش هكتفي بشرح الخطوات.'
            :'Choose a project folder first so I can inspect it and prepare actionable steps.',
            agentTask:{commandId:decision.command_id,kind:'coding',goal:intent.goal,status:'workspace_needed'}});
          return;
        }
      }
    }catch(error){
      // Never silently turn a failed execution request into an explanatory LLM reply.
      if(userAskedForAction){
        const reason=error instanceof Error?error.message:'تعذّر الاتصال بمنفّذ المهام';
        current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),content:current.language==='ar'
          ?'حاولت أجهّز التنفيذ لكن العملية اتوقفت قبل ما أغيّر أي ملف. راجع الخطأ وحاول تاني.'
          :'The task could not start. No files were changed.',
          agentTask:{kind:'coding',goal:requestText,status:'failed',summary:reason}});
        return;
      }
      if(signal.aborted)return;
      current.addMessage(id,{id:uid(),role:'assistant',createdAt:Date.now(),incomplete:true,
        content:current.language==='ar'?'تعذّر فهم الطلب دلوقتي. طلبك محفوظ؛ جرّب تاني لما الاتصال يرجع.':'Request understanding is unavailable. Your message is saved; please retry.',
        reasoning:error instanceof Error?error.message:'Understanding unavailable'});
      return;
    }
    // Compatibility with legacy REA capability card: never infer tools from LLM text.
    if(!signal.aborted&&!brainRouted && /(?:rea|ريا|هندسة\s*عكسية|الهندسه|الهندسة)/i.test(requestText)){
      try{
        const decision=await requestJSON<{tool_request:(ToolRequest&{message_ar:string;message_en:string})|null}>('/v1/integrations/intent',
          {method:'POST',body:JSON.stringify({text:requestText.slice(0,12000),previous_user_texts:messages.slice(0,-1).filter(m=>m.role==='user').slice(-8).map(m=>m.content.slice(0,4000))}),signal});
        if(decision.tool_request){
          const ar=current.language==='ar';
          current.addMessage(id,{id:uid(),role:'assistant',content:ar?decision.tool_request.message_ar:decision.tool_request.message_en,
            createdAt:Date.now(),toolRequest:decision.tool_request});
          return;
        }
      }catch{/* Do not claim that REA ran on unavailable API. */}
    }
  }
  if(signal.aborted)return;
  current.addMessage(id,{id:assistantId,role:'assistant',content:'',model:current.selectedModel,createdAt:Date.now(),isStreaming:true});
  current.setStreaming(true,assistantId);
  let output='';let batch='';let lastFlush=Date.now();
  try{
    const latest=messages.at(-1);
    const files=(latest?.role==='user'?latest.attachments||[]:[]).map(a=>({attachment:a,file:getAttachment(a.id)}));
    if(files.some(item=>!item.file))throw new Error('Some original attachments are no longer available. Please attach them again.');
    // Keep router diagnostics internal; the chat only presents the final answer.
    for await (const event of streamChat(messages,current.selectedModel,current.options,signal,files as {attachment:UploadedAttachment;file:File}[],id)){
      if(signal.aborted)break;
      // No visible routing chatter; diagnostics remain in message metadata.
      if(event.type==='model')useApp.getState().updateMessage(id,assistantId,{model:event.value.model,provider:event.value.provider,dataUse:event.value.data_use,attempts:event.value.attempts,offline:event.value.offline,cached:event.value.cached});
      if(event.type==='metrics')useApp.getState().updateMessage(id,assistantId,{metrics:event.value});
      if(event.type==='token'){
        batch+=event.value;
        if(Date.now()-lastFlush>65){output+=batch;batch='';useApp.getState().updateMessage(id,assistantId,{content:output});if(/```(?:[\w.+#-]*)\s*\n[\s\S]{1,}/.test(output)){const app=useApp.getState();if(app.studioCodeHandoff?.messageId!==assistantId){app.setStudioCodeHandoff({chatId:id,messageId:assistantId});openWorkspaceSafely();}}lastFlush=Date.now()}
      }
    }
    files.forEach(item=>releaseAttachment(item.attachment.id));
    output+=batch;batch='';
    useApp.getState().updateMessage(id,assistantId,{content:output,isStreaming:false,reasoning:undefined});
    if(/```(?:[\w.+#-]*)\s*\n[\s\S]{1,}/.test(output)){const app=useApp.getState();if(app.studioCodeHandoff?.messageId!==assistantId){app.setStudioCodeHandoff({chatId:id,messageId:assistantId});openWorkspaceSafely();}}
  }catch(error){
    if(!signal.aborted){
      output+=batch;batch='';const reason=error instanceof Error?error.message:'Unknown error';
      const ar=useApp.getState().language==='ar';
      const hint=ar?'تعذّر الرد من النماذج المهيّأة. افتح إدارة النماذج واختبر Gemini أو Groq أو OpenRouter. Ollama احتياطي في الوضع التلقائي.':'All configured models failed. Check Gemini, Groq or OpenRouter in Model Center; Auto uses Ollama as a backup.';
      useApp.getState().toast('error',ar?'تعذّر توليد الرد':'Generation interrupted',reason);
      useApp.getState().updateMessage(id,assistantId,{content:output||`${hint}\n\n${reason}`,reasoning:output?reason:undefined,isStreaming:false,incomplete:true});
    }
  }finally{if(batch){output+=batch;batch='';useApp.getState().updateMessage(id,assistantId,{content:output})}useApp.getState().updateMessage(id,assistantId,{isStreaming:false})}
  }finally{if(controller===activeController){useApp.getState().setStreaming(false);controller=null;activeGenerationChat=null}}
}
export function stopGeneration(){controller?.abort();if(activeGenerationChat)void requestJSON('/v1/brain/cancel',{method:'POST',body:JSON.stringify({conversation_id:activeGenerationChat})}).catch(()=>{});useApp.getState().setStreaming(false);}
export async function retrySavedCommand(chatId:string,messageId:string){
 const chat=useApp.getState().chats.find(c=>c.id===chatId);
 const command=chat?.messages.find(m=>m.id===messageId)?.pendingCommand;
 if(command)await generate(chatId,command.id);
}
export async function editAndRegenerate(id:string,messageId:string,newText:string){
  const state=useApp.getState();if(state.streaming||!newText.trim())return;
  const chat=state.chats.find(c=>c.id===id);
  const target=chat?.messages.find(m=>m.id===messageId);
  if(!target||target.role!=='user')return;
  state.editMessage(id,messageId,newText.trim());
  state.trimAfter(id,messageId);
  await generate(id);
}
export async function regenerate(id:string){
  const state=useApp.getState();if(state.streaming)return;
  const chat=state.chats.find(c=>c.id===id);if(!chat)return;
  const lastUser=[...chat.messages].reverse().find(m=>m.role==='user');if(!lastUser)return;
  state.trimAfter(id,lastUser.id);await generate(id);
}
