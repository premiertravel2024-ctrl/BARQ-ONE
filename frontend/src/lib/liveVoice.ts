import type {AppAction} from './appNavigation';
import {acquireSpeechGlow} from './speechGlow';
export type VoiceEvent={app_action?:AppAction;elapsedMs?:number;request_id?:string;conversation_id?:string;cards?:Array<{label:string;kind?:string;url?:string;extension?:string;description?:string}>;spoken_ar?:string;needs_approval?:boolean;matches?:Array<{repository:string;url:string;description:string;stars:number}>;task_id?:string;chat_id?:string;type:string;level?:number;text?:string;message?:string;code?:string;data?:string;status?:string;tool?:string;computer_enabled?:boolean;candidate_id?:string;approval_token?:string;label?:string;url?:string};
export type VoiceHistory=Array<{role:string;content:string}>;
export class LiveVoice {
 private socket?:WebSocket;private stream?:MediaStream;private input?:AudioContext;private output?:AudioContext;
 private capture?:AudioWorkletNode;private source?:MediaStreamAudioSourceNode;private silent?:GainNode;
 private playing=new Set<AudioBufferSourceNode>();private next=0;private closed=false;private muted=false;private ready=false;
 private timer?:ReturnType<typeof setTimeout>;private lastMicMeter=0;
 private watchdog?:ReturnType<typeof setInterval>;private lastResponseAt=0;private firstVoiceAt=0;private lastWarningAt=0;private relaySeen=false;private sentAudio=false;
 private releaseGlow?:(()=>void);
 private speechEndedAt?:number;
 private interrupted=false;
 private interruptedTurnPending=false;
 private turnActive=false;
 private directAudioUntil=0;
 private taskAudio?:{abort:AbortController;pcm?:Uint8Array};
 private interruptMs=0;
 private interruptFrames:ArrayBuffer[]=[];
 private playbackFrames=new Map<AudioBufferSourceNode,{start:number;levels:number[]}>();

 private speechEnd(){this.speechEndedAt=performance.now();}

 private measure(status:'execution_start'|'first_audio',delay=0){
  if(this.speechEndedAt===undefined)return;
  this.receive({type:'voice_metric',status,elapsedMs:Math.round(performance.now()-this.speechEndedAt+delay)});
  if(status==='first_audio')this.speechEndedAt=undefined;
 }

 private playbackLevel(){
  if(!this.output)return 0;
  const now=this.output.currentTime;
  for(const {start,levels} of this.playbackFrames.values()){
   const index=Math.floor((now-start)*50);
   if(index>=0&&index<levels.length)return levels[index];
  }
  return 0;
 }
 // A short voice/silence detector finalizes the turn. Continuous PCM without
 // audio_stream_end can leave quiet utterances pending at Gemini Live.
 private speechMs=0;private silenceMs=0;private speechActive=false;private noiseFloor=0.002;
 private awaitingReplyAt=0;private utteranceEndSent=false;
 private speakerUnlockRequired=false;
 private speakerBuffer:string[]=[];
 private speakerGuardUntil=0;
 // Counters only: never persist raw audio, transcripts or user identity.
 private micFrameCount=0;private ignoredMicFrames=0;private malformedMicFrames=0;
 private lastDiagnosticAt=0;
 private reportMicDiagnostics(){
  if(Date.now()-this.lastDiagnosticAt<5000)return;
  this.lastDiagnosticAt=Date.now();
  this.receive({type:'voice_diagnostics',status:`mic_sent=${this.micFrameCount};guarded=${this.ignoredMicFrames};invalid=${this.malformedMicFrames}`});
 }

 private playbackEndTimer?:ReturnType<typeof setTimeout>;
 private static readonly SPEECH_MS=192;
 private static readonly PAUSE_MS=1100;
 private resetSpeech(){this.speechMs=0;this.silenceMs=0;this.speechActive=false;this.utteranceEndSent=false;this.awaitingReplyAt=0;}
 private detectEndOfSpeech(packet:ArrayBuffer,socket:WebSocket,rms=this.micRms(packet)){
  const samples=new Int16Array(packet);
  if(!samples.length)return 0;
  // The worklet now emits 20-ms frames, but calculate from the PCM length
  // so handoffs/older builds cannot make silence detection run 3x too fast.
  const frameMs=samples.length/16;
  const threshold=Math.max(0.007,this.noiseFloor*(this.speechActive?1.9:3.0));
  if(rms>threshold){
   this.speechMs+=frameMs;this.silenceMs=0;
   if(this.speechMs>=LiveVoice.SPEECH_MS&&!this.speechActive){
    this.speechActive=true;this.utteranceEndSent=false;
    if(!this.interruptedTurnPending)this.interrupted=false;
    this.receive({type:'voice_phase',status:'user_speaking'});
   }
   if(this.speechActive)this.speechEnd();
  }else{
   if(!this.speechActive){this.noiseFloor=Math.max(0.001,Math.min(0.018,0.97*this.noiseFloor+0.03*rms));this.speechMs=0;}
   else{
    this.silenceMs+=frameMs;
    if(this.silenceMs>=LiveVoice.PAUSE_MS&&!this.utteranceEndSent){
     // Close a real utterance even in open conversation. Waiting exclusively
     // for the remote VAD left Live sessions silent when the remote end did
     // not detect the local pause. One marker per speech segment, never for
     // ambient silence or speaker playback. Further speech starts a new turn.
     this.utteranceEndSent=true;
     this.speechActive=false;
     this.speechMs=0;
     this.silenceMs=0;
     this.awaitingReplyAt=Date.now();
     if(socket.readyState===WebSocket.OPEN){
      socket.send(JSON.stringify({type:'end_audio'}));
      this.receive({type:'voice_phase',status:'utterance_finalized'});
     }
    }
   }
  }
  return Math.min(100,Math.round(rms*500));
 }
 private micRms(packet:ArrayBuffer){
  const samples=new Int16Array(packet);
  let energy=0;
  for(const sample of samples)energy+=(sample/32768)**2;
  return samples.length?Math.sqrt(energy/samples.length):0;
 }

 private captureInterruption(packet:ArrayBuffer,rms:number){
  if(!this.playing.size||this.stream?.getAudioTracks()[0]?.getSettings?.().echoCancellation!==true){
   this.interruptMs=0;this.interruptFrames=[];return;
  }
  this.interruptFrames.push(packet);
  // Keep enough leading audio for the first syllable, with a bounded buffer.
  this.interruptFrames=this.interruptFrames.slice(-10);
  const threshold=Math.max(0.022,this.noiseFloor*5,this.playbackLevel()*0.12);
  this.interruptMs=rms>=threshold?this.interruptMs+packet.byteLength/32:0;
  if(this.interruptMs<120)return;
  const frames=this.interruptFrames;
  this.interruptPlayback();
  this.speakerGuardUntil=0;
  this.receive({type:'voice_phase',status:'spoken_interrupt'});
  return frames;
 }

 announceTaskResult(text:string,voice:string){
  if(this.closed||!this.ready||this.taskAudio||this.playingTaskResult)return false;
  const announcement={abort:new AbortController(),pcm:undefined as Uint8Array|undefined};
  this.taskAudio=announcement;
  const timeout=setTimeout(()=>announcement.abort.abort(),10000);
  void (async()=>{
   try{
    const response=await fetch('/v1/voice/speak',{method:'POST',headers:{'Content-Type':'application/json'},
     body:JSON.stringify({text,voice}),signal:announcement.abort.signal});
    if(!response.ok)throw new Error('Task speech unavailable');
    const pcm=taskSpeechPcm(await response.arrayBuffer());
    if(this.taskAudio!==announcement)return;
    announcement.pcm=pcm;
    this.playTaskResult();
   }catch{
    if(this.taskAudio===announcement){
     this.taskAudio=undefined;
     this.receive({type:'voice_warning',message:'نتيجة المهمة موجودة في الشات. تعذّر تشغيلها بالصوت.'});
    }
   }finally{clearTimeout(timeout);}
  })();
  return true;
 }

 cancelTaskResult(){
  this.taskAudio?.abort.abort();this.taskAudio=undefined;
  if(this.playingTaskResult){this.clearAudio();this.speakerGuardUntil=Date.now()+150;}
 }

 private playingTaskResult=false;
 private playTaskResult(){
  const pcm=this.taskAudio?.pcm;
  if(!pcm||this.closed||this.muted||this.output?.state!=='running'||this.speechMs||this.speechActive||
     this.awaitingReplyAt||this.turnActive||Date.now()<this.directAudioUntil||this.playing.size||
     this.speakerBuffer.length||Date.now()<this.speakerGuardUntil)return;
  this.taskAudio=undefined;
  this.playingTaskResult=true;
  this.playPcm(pcm);
 }

 // Called from an explicit click if Chromium prevented autoplay after a wake event.
 async unlockSpeaker(){
  if(!this.output||this.closed)return false;
  try{await Promise.race([this.output.resume(),new Promise<never>((_,reject)=>setTimeout(()=>reject(new Error('Autoplay permission required')),2500))]);}
  catch{return false;}
  this.speakerUnlockRequired=this.output.state!=='running';
  if(!this.speakerUnlockRequired){
   this.receive({type:'voice_phase',status:'speaker_ready'});
   const pending=this.speakerBuffer.splice(0);
   for(const chunk of pending)this.play(chunk);
   this.playTaskResult();
  }
  return !this.speakerUnlockRequired;
 }

 private reportSpeaking(active:boolean){
  if(active)this.releaseGlow??=acquireSpeechGlow(()=>this.playbackLevel());
  else{this.releaseGlow?.();this.releaseGlow=undefined;}
 }
 private pendingChatContext:{messages:VoiceHistory;chatId:string}|null=null;
 // Keep the already-open voice call attached to the SAME chat when the user
 // pastes a link while Gemini Live is active. Only text from user turns is sent.
 sendChatContext(messages:VoiceHistory,chatId:string=''){
  const safe=messages.filter(m=>m.role==='user').slice(-16).map(m=>({role:'user' as const,content:m.content.slice(0,900)}));
  this.pendingChatContext={messages:safe,chatId};
  if(!this.closed&&this.ready&&this.socket?.readyState===WebSocket.OPEN){
   this.socket.send(JSON.stringify({type:'chat_context',chat_id:chatId,messages:safe}));
   this.pendingChatContext=null;
  }
 }
 sendWorkState(state:{task_id:string;goal:string;status:string;phase:string;summary:string;progress:string}|null){
  if(!this.closed&&this.socket?.readyState===WebSocket.OPEN){
   this.socket.send(JSON.stringify({type:'work_state',state:state||{}}));
  }
 }
 constructor(private receive:(event:VoiceEvent)=>void){}
 async start(voice:string,history:VoiceHistory,computerEnabled=false,conversationId='',wakeGreeting=false,openConversation=false){
  try{
   // 16kHz is preferred, not mandatory: the AudioWorklet resamples
   // from the real hardware rate (44.1/48kHz on many Windows devices).
   try{this.input=new AudioContext({sampleRate:16000});}
   catch{this.input=new AudioContext();}
   this.output=new AudioContext();
   // Do not await AudioContext.resume() before opening the call: after a
   // background wake, Chromium may defer its promise until a user gesture.
   // Recording can be authorized by the mic permission while playback awaits
   // an explicit unlock; neither should hide the Gemini connection state.
   void this.input.resume().catch(()=>{});
   void this.output.resume().catch(()=>{});
   if(this.output.state==='suspended'){
    this.speakerUnlockRequired=true;
    this.receive({type:'speaker_blocked',message:'إخراج الصوت محتاج تفعيل من داخل نافذة برق؛ اضغط «تفعيل السماعة» مرة واحدة.'});
   }
   if(this.closed)return;
   if(!Number.isFinite(this.input.sampleRate)||this.input.sampleRate<8000||this.input.sampleRate>192000)throw new Error('معدل الميكروفون غير مدعوم');
   // Avoid competing with BARQ's Vosk watcher for the same Windows input device.
   // It resumes after the Live call ends; this does not change wake preferences.
   await fetch('/v1/voice/wake/handoff',{method:'POST'}).catch(()=>null);
   if(this.closed)return;
   const stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
   if(this.closed){stream.getTracks().forEach(t=>t.stop());return;}this.stream=stream;
   await this.input.audioWorklet.addModule('/audio/live-capture.js');if(this.closed)return;
   this.capture=new AudioWorkletNode(this.input,'barq-capture');this.source=this.input.createMediaStreamSource(stream);
   this.silent=this.input.createGain();this.silent.gain.value=0;
   this.source.connect(this.capture);this.capture.connect(this.silent);this.silent.connect(this.input.destination);
   const socket=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/v1/voice/live?voice=${encodeURIComponent(voice)}&computer=${computerEnabled?'1':'0'}&conversation_id=${encodeURIComponent(conversationId)}&wake=${wakeGreeting?'1':'0'}&mode=${openConversation?'open':'standard'}`);this.socket=socket;
   this.timer=setTimeout(()=>this.fail('الاتصال الصوتي اتأخر. جرّب تاني.'),20000);
   socket.onmessage=e=>{if(this.closed)return;try{const event=JSON.parse(e.data) as VoiceEvent;
    if(event.type==='ready'){clearTimeout(this.timer);this.lastResponseAt=Date.now();this.receive({type:'voice_phase',status:'live_connected'});socket.send(JSON.stringify({type:'context',voice_progress:true,messages:history.slice(-12).map(m=>({role:m.role,content:m.content.slice(0,1200)})),reference_messages:history.filter(m=>m.role==='user').slice(-16).map(m=>({role:m.role,content:m.content.slice(0,900)}))}));this.ready=true;if(this.pendingChatContext){const pending=this.pendingChatContext;this.pendingChatContext=null;this.sendChatContext(pending.messages,pending.chatId);}}
    if(event.type==='interrupt'){
     if(!this.interrupted){this.clearAudio();this.speakerGuardUntil=0;this.resetSpeech();}
     this.turnActive=false;this.directAudioUntil=0;this.interruptedTurnPending=false;
    }
    if(event.type==='input_text'&&(this.speechActive||this.awaitingReplyAt)){
     this.interrupted=false;this.interruptedTurnPending=false;
    }
    if(this.interrupted&&(event.type==='audio'||event.type==='output_text'))return;
    if(event.type==='verified_output_text'){
     this.directAudioUntil=Date.now()+9000;
     this.awaitingReplyAt=0;
     this.lastResponseAt=Date.now();
    }
    if(event.type==='voice_warning')this.directAudioUntil=0;
    if(event.type==='audio_relay'){this.relaySeen=true;this.receive({type:'voice_phase',status:'audio_forwarded'});}
    if(event.type==='input_text'||event.type==='output_text'||event.type==='audio'||event.type==='turn_complete'){
     this.lastResponseAt=Date.now();
     if(event.type==='output_text'||event.type==='audio'||event.type==='turn_complete')this.awaitingReplyAt=0;
     if(event.type==='input_text'||event.type==='output_text')this.turnActive=true;
    }
    if(event.type==='voice_phase'&&event.status==='execution_started')this.measure('execution_start');
    if(event.type==='audio'&&event.data){
     this.firstVoiceAt=0;
     if(this.playingTaskResult)this.cancelTaskResult();
     if(!this.directAudioUntil)this.turnActive=true;
     this.directAudioUntil=0;
     this.play(event.data);
    }
    if(event.type==='turn_complete'){this.firstVoiceAt=0;this.interruptedTurnPending=false;this.turnActive=false;}
    if(event.type==='error'){this.fail(event.message||'تعذّر الاتصال الصوتي');return;}
    this.receive(event);
   }catch{this.fail('وصلت بيانات صوت غير صالحة');}};
   socket.onerror=()=>this.fail('الاتصال الصوتي غير متاح. راجع إعدادات Gemini والإنترنت.');
   socket.onclose=()=>{if(!this.closed){this.stop();this.receive({type:'closed',message:'المكالمة انتهت. تقدر تبدأ مكالمة جديدة.'});}};
   this.capture.port.onmessage=e=>{if(this.closed||this.muted||!this.ready||socket.readyState!==WebSocket.OPEN)return;
    if(!(e.data instanceof ArrayBuffer))return;
    if(e.data.byteLength===0||e.data.byteLength%2!==0||e.data.byteLength>32000){
     this.malformedMicFrames++;
     if(this.malformedMicFrames%10===1)this.receive({type:'voice_warning',message:'تم تجاهل حزمة ميكروفون غير سليمة بدون إنهاء المكالمة.'});
     this.reportMicDiagnostics();return;
    }
    // Keep the live stream real time; a temporary network backlog must not
    // close the entire call or accumulate many seconds of stale audio.
    // A temporary upload backlog must not silently remove syllables from
    // the user's speech. Warn early and preserve complete PCM frames. If the
    // network is genuinely stalled, stop explicitly rather than pretend the
    // model heard a complete instruction.
    if(socket.bufferedAmount>128000&&Date.now()-this.lastWarningAt>5000){
     this.lastWarningAt=Date.now();
     this.receive({type:'voice_warning',message:'اتصال الميكروفون بطيء؛ برق بيحافظ على الكلام بدل ما يحذف مقاطع منه.'});
    }
    if(socket.bufferedAmount>1000000){
     this.fail('الاتصال بطيء جدًا ومش قادر ينقل كلامك كاملًا. اتوقفت المكالمة بدل إسقاط أجزاء من صوتك.');
     return;
    }
    const rms=this.micRms(e.data);
    let frames:ArrayBuffer[]=[e.data];
    // Only allow acoustic interruption with echo cancellation confirmed by
    // the capture device. Normal playback still suppresses microphone echo.
    if(this.playing.size>0||this.speakerBuffer.length>0||Date.now()<this.speakerGuardUntil){
     const interruption=this.captureInterruption(e.data,rms);
     if(!interruption){this.ignoredMicFrames++;this.reportMicDiagnostics();return;}
     frames=interruption;
    }else{
     this.interruptMs=0;this.interruptFrames=[];
    }
    let level=0;
    for(const frame of frames){
     level=this.detectEndOfSpeech(frame,socket,frame===e.data?rms:undefined);
     if(!this.sentAudio){this.sentAudio=true;this.receive({type:'voice_phase',status:'mic_streaming'});}
     socket.send(frame);this.micFrameCount++;
    }
    if(Date.now()-this.lastMicMeter>250){
     this.receive({type:'mic_level',level});
     if(this.speechActive&&!this.firstVoiceAt&&this.playing.size===0)this.firstVoiceAt=Date.now();
     this.lastMicMeter=Date.now();
    }
    this.reportMicDiagnostics();
    this.playTaskResult();
   };
   this.watchdog=setInterval(()=>{
    if(this.closed||!this.ready||this.muted)return;
    if(this.input?.state==='suspended'){
     if(Date.now()-this.lastWarningAt>5000){this.lastWarningAt=Date.now();this.receive({type:'mic_activation_required',message:'وصول الميكروفون محتاج تفعيل من داخل برق؛ اضغط تفعيل الميكروفون.'});}
     return;
    }
    this.recoverIdleTurn();
    this.playTaskResult();
   },2000);
  }catch(error){if(!this.closed)this.fail(error instanceof Error?error.message:'الميكروفون غير متاح');}
 }
 private recoverIdleTurn(){
  const now=Date.now();
  const waiting=this.awaitingReplyAt!==0;
  const quietFor=now-Math.max(this.lastResponseAt,this.awaitingReplyAt);
  if(this.speechActive||this.playing.size||quietFor<(waiting?11000:15000))return;
  if(!waiting&&!this.turnActive)return;
  this.awaitingReplyAt=0;
  this.turnActive=false;
  this.interruptedTurnPending=false;
  this.firstVoiceAt=0;
  this.speechEndedAt=undefined;
  this.receive({type:'voice_phase',status:'reply_timed_out'});
  this.interrupted=false;
  if(waiting&&now-this.lastWarningAt>6000){
   this.lastWarningAt=now;
   this.receive({type:'voice_warning',message:this.relaySeen
    ?'Gemini اتأخر في الرد. تقدر تكمل الكلام أو تختبر اتصال الصوت.'
    :'مافيش تأكيد بوصول الكلام. راجع الميكروفون والاتصال.'});
  }
 }
 private play(encoded:string){
  const ctx=this.output;if(!ctx||this.closed)return;
  // Chromium can pause the speaker when a background wake starts a session.
  // Never enqueue unbounded audio into a suspended AudioContext; that used to
  // throw inside socket.onmessage and terminate the entire Live conversation.
  if(ctx.state!=='running'){
   // The output can be initially suspended by Chromium until the user clicks
   // the speaker button. Keep a bounded set of audio chunks instead of silently
   // losing the beginning of the model reply.
   if(this.speakerBuffer.length<120)this.speakerBuffer.push(encoded);
   else if(Date.now()-this.lastWarningAt>5000){
    this.lastWarningAt=Date.now();
    this.receive({type:'voice_warning',message:'السماعة غير مفعّلة وصوت الرد اتراكم؛ فعّل السماعة لإكمال التشغيل.'});
   }
   if(!this.speakerUnlockRequired){
    this.speakerUnlockRequired=true;
    this.receive({type:'speaker_blocked',message:'وصل رد برق لكن إخراج الصوت محتاج تفعيل من داخل التطبيق.'});
   }
   return;
  }
  // Never reset all already scheduled chunks because playback lags behind
  // Gemini's network stream. A forced clear caused whole words to disappear.
  const queuedSeconds=Math.max(0,this.next-ctx.currentTime);
  if(queuedSeconds>8&&Date.now()-this.lastWarningAt>5000){
   this.lastWarningAt=Date.now();
   this.receive({type:'voice_warning',message:'صوت برق بيتخزن مؤقتًا بسبب بطء التشغيل؛ الكلام مش هيتمسح.'});
  }
  let raw:string;
  try{raw=atob(encoded);}catch{
   this.receive({type:'voice_warning',message:'وصلت عينة صوت غير صالحة وتم تجاهلها.'});return;
  }
  if(raw.length%2!==0||raw.length===0){
   this.receive({type:'voice_warning',message:'تم تجاهل عينة صوت غير مكتملة.'});return;
  }
  this.playPcm(Uint8Array.from(raw,c=>c.charCodeAt(0)));
 }

 private playPcm(raw:Uint8Array){
  const ctx=this.output;if(!ctx||this.closed)return;
  try{
   const buffer=ctx.createBuffer(1,raw.length/2,24000),samples=buffer.getChannelData(0);
   const levels:number[]=[];
   for(let offset=0;offset<samples.length;offset+=480){
    const end=Math.min(offset+480,samples.length);
    let energy=0;
    for(let i=offset;i<end;i++){
     const value=raw[i*2]|(raw[i*2+1]<<8);
     const sample=(value>=32768?value-65536:value)/32768;
     samples[i]=sample;
     energy+=sample*sample;
    }
    levels.push(Math.min(1,Math.sqrt(energy/(end-offset))*4));
   }
   if(this.playbackEndTimer){clearTimeout(this.playbackEndTimer);this.playbackEndTimer=undefined;}
   const node=ctx.createBufferSource();node.buffer=buffer;node.connect(ctx.destination);this.playing.add(node);
   if(this.playing.size===1)this.reportSpeaking(true);
   node.onended=()=>{node.disconnect();this.playbackFrames.delete(node);this.playing.delete(node);if(!this.playing.size&&!this.closed){
    // Network chunks can arrive slightly apart; do not repeatedly signal
    // playback completion and cancel speaking between every tiny gap.
    this.playingTaskResult=false;
    this.playbackEndTimer=setTimeout(()=>{if(!this.playing.size&&!this.closed){this.reportSpeaking(false);this.receive({type:'playback_done'});}},320);
   }};
   this.next=Math.max(ctx.currentTime+.02,this.next);
   this.playbackFrames.set(node,{start:this.next,levels});
   node.start(this.next);
   if(!this.playingTaskResult)this.measure('first_audio',(this.next-ctx.currentTime)*1000);
   this.next+=buffer.duration;
   // A brief tail also shields gaps between small PCM chunks from acoustic echo.
   this.speakerGuardUntil=Date.now()+Math.max(700,(this.next-ctx.currentTime)*1000+450);
  }catch{
   this.clearAudio();
   this.receive({type:'voice_warning',message:'تعذر تشغيل جزء من الصوت؛ المكالمة لسه متصلة.'});
  }
 }

 interruptPlayback(){
  if(this.closed)return;
  this.interruptedTurnPending=!!this.awaitingReplyAt;
  this.interrupted=true;
  this.speechEndedAt=undefined;
  this.directAudioUntil=0;
  this.turnActive=false;
  this.cancelTaskResult();
  this.clearAudio();
  this.speakerGuardUntil=Date.now()+150;
  this.resetSpeech();
  if(this.socket?.readyState===WebSocket.OPEN)this.socket.send(JSON.stringify({type:'interrupt_output'}));
  this.receive({type:'voice_phase',status:'manual_interrupt'});
 }
 clearAudio(){this.playingTaskResult=false;this.interruptMs=0;this.interruptFrames=[];if(this.playbackEndTimer)clearTimeout(this.playbackEndTimer);this.playbackEndTimer=undefined;this.speakerBuffer=[];this.reportSpeaking(false);for(const node of this.playing){node.onended=null;try{node.stop();node.disconnect();}catch{}}this.playing.clear();this.playbackFrames.clear();this.next=0;}
 probeReply(){
  if(this.closed||!this.ready||this.socket?.readyState!==WebSocket.OPEN)return;
  this.socket.send(JSON.stringify({type:'probe'}));
  this.receive({type:'voice_phase',status:'probe_sent'});
 }
 async unlockMicrophone(){
  if(!this.input||this.closed)return false;
  try{await Promise.race([this.input.resume(),new Promise<never>((_,reject)=>setTimeout(()=>reject(new Error('Microphone needs a user gesture')),2500))]);}
  catch{return false;}
  return this.input.state==='running';
 }
 finishUtterance(){
  if(this.closed||!this.ready||this.socket?.readyState!==WebSocket.OPEN)return;
  this.resetSpeech();
  this.interrupted=false;
  this.speechEnd();
  this.awaitingReplyAt=Date.now();
  this.socket.send(JSON.stringify({type:'end_audio'}));
  this.receive({type:'voice_phase',status:'utterance_finalized'});
 }
 setMuted(value:boolean){this.muted=value;if(value)this.resetSpeech();this.stream?.getAudioTracks().forEach(t=>{t.enabled=!value;});if(value&&this.socket?.readyState===WebSocket.OPEN)this.socket.send(JSON.stringify({type:'end_audio'}));}
 private fail(message:string){if(this.closed)return;this.stop();this.receive({type:'error',message});}
 stop(){if(this.closed)return;this.closed=true;clearTimeout(this.timer);if(this.watchdog)clearInterval(this.watchdog);this.cancelTaskResult();this.clearAudio();
  if(this.socket){this.socket.onclose=null;this.socket.onerror=null;this.socket.onmessage=null;this.socket.close();}
  if(this.capture){this.capture.port.onmessage=null;this.capture.disconnect();}this.source?.disconnect();this.silent?.disconnect();
  this.stream?.getTracks().forEach(t=>t.stop());void this.input?.close().catch(()=>{});void this.output?.close().catch(()=>{});
 }
}

// The speech endpoint returns RIFF/WAV. Accept ancillary chunks and validate
// the same PCM format the live audio output already uses.
function taskSpeechPcm(wav:ArrayBuffer):Uint8Array{
 const view=new DataView(wav);
 if(view.byteLength<44||view.getUint32(0)!==0x52494646||view.getUint32(8)!==0x57415645)
  throw new Error('Invalid WAV header');
 let formatValid=false;
 for(let offset=12;offset+8<=view.byteLength;){
  const kind=view.getUint32(offset),size=view.getUint32(offset+4,true),start=offset+8;
  if(start+size>view.byteLength)break;
  if(kind===0x666d7420&&size>=16)
   formatValid=view.getUint16(start,true)===1&&view.getUint16(start+2,true)===1&&
    view.getUint32(start+4,true)===24000&&view.getUint16(start+14,true)===16;
  if(kind===0x64617461&&formatValid&&size>0&&size%2===0)
   return new Uint8Array(wav,start,size);
  offset=start+size+(size%2);
 }
 throw new Error('Unsupported task audio format');
}
