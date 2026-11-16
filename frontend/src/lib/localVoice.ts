import {bindSpeechGlow} from './speechGlow';
import type {VoiceEvent,VoiceHistory} from './liveVoice';

// Windows SAPI emits PCM WAV. Read only the waveform amplitude for the avatar.
async function wavPlaybackMeter(wave:Blob,audio:HTMLAudioElement){
 const view=new DataView(await wave.arrayBuffer());
 if(view.byteLength<44||view.getUint32(0)!==0x52494646||view.getUint32(8)!==0x57415645)return;
 let sampleRate=0,channels=0;
 for(let offset=12;offset+8<=view.byteLength;){
  const kind=view.getUint32(offset),size=view.getUint32(offset+4,true),start=offset+8;
  if(start+size>view.byteLength)return;
  if(kind===0x666d7420&&size>=16){
   if(view.getUint16(start,true)!==1||view.getUint16(start+14,true)!==16)return;
   channels=view.getUint16(start+2,true);sampleRate=view.getUint32(start+4,true);
  }
  if(kind===0x64617461&&sampleRate&&channels)return ()=>{
   const first=start+Math.floor(audio.currentTime*sampleRate)*channels*2;
   const last=Math.min(start+size-1,first+Math.ceil(sampleRate*.02)*channels*2);
   let energy=0,count=0;
   for(let i=first;i<last;i+=channels*2){energy+=(view.getInt16(i,true)/32768)**2;count++;}
   return count?Math.min(1,Math.sqrt(energy/count)*4):0;
  };
  offset=start+size+(size%2);
 }
}

/** Optional local STT -> BARQ ask_barq -> Windows SAPI path.
 * It does not create a second assistant brain and never calls Google.
 * Microphone is stopped before each synthetic reply to avoid feedback.
 */
export class LocalVoice {
 private active=false;
 private stopped=false;
 private request=new AbortController();
 private chatId='';
 private sessionId=crypto.randomUUID();
 private computerEnabled=false;
 private recorder:MediaRecorder|null=null;
 private stream:MediaStream|null=null;
 private monitor:AudioContext|null=null;
 private tick:ReturnType<typeof setInterval>|null=null;
 private playback:HTMLAudioElement|null=null;
 private lastBlobUrl='';
 private finishPlayback?:()=>void;
 private taskResult?:{text:string;abort:AbortController};
 private taskPlayback=false;
 private replySpeech?:AbortController;
 constructor(private readonly receive:(event:VoiceEvent)=>void){}
 async start(_voice:string,_history:VoiceHistory,computerEnabled:boolean,chatId:string,
             _wakeGreeting=false,_openConversation=true):Promise<void>{
  const status=await fetch('/v1/voice/readiness',{cache:'no-store',signal:this.request.signal}).then(r=>r.json()) as {local_stt_ready?:boolean};
  if(this.stopped)return;
  if(!status.local_stt_ready)throw new Error('نموذج Whisper المحلي مش جاهز؛ حدّد مجلده في إعدادات الصوت.');
  if(!navigator.mediaDevices?.getUserMedia||typeof MediaRecorder==='undefined')throw new Error('الوصول للميكروفون المحلي غير متاح.');
  this.active=true;
  this.chatId=chatId;this.computerEnabled=computerEnabled;
  await this.listen();
  if(this.active)this.receive({type:'ready',computer_enabled:computerEnabled});
 }
 sendChatContext(_messages:VoiceHistory,chatId:string):void{this.chatId=chatId;}
 sendWorkState(_state:{task_id:string;goal:string;status:string;phase?:string;summary?:string;progress?:string}|null):void{}
 async unlockSpeaker(){return true;}
 stop(){
  this.stopped=true;
  this.active=false;
  this.request.abort();
  this.cancelTaskResult();
  if(this.tick){clearInterval(this.tick);this.tick=null;}
  if(this.recorder&&this.recorder.state!=='inactive')this.recorder.stop();
  this.recorder=null;
  this.stream?.getTracks().forEach(t=>t.stop());this.stream=null;
  if(this.monitor){void this.monitor.close();this.monitor=null;}
  this.interruptPlayback();
  if(this.lastBlobUrl){URL.revokeObjectURL(this.lastBlobUrl);this.lastBlobUrl='';}
 }
 announceTaskResult(text:string){
  if(!this.active||this.taskResult)return false;
  this.taskResult={text,abort:new AbortController()};
  return true;
 }
 cancelTaskResult(){
  this.taskResult?.abort.abort();
  this.taskResult=undefined;
  if(this.taskPlayback){
   this.playback?.pause();
   this.finishPlayback?.();
  }
 }
 interruptPlayback(){
  this.replySpeech?.abort();
  this.cancelTaskResult();
  this.playback?.pause();
  this.finishPlayback?.();
 }
 private async listen(){
  if(!this.active)return;
  const stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});
  if(!this.active){stream.getTracks().forEach(t=>t.stop());return;}
  this.stream=stream;
  const mime=MediaRecorder.isTypeSupported('audio/webm;codecs=opus')?'audio/webm;codecs=opus':'';
  const recorder=new MediaRecorder(stream,mime?{mimeType:mime}:undefined);
  this.recorder=recorder;
  const chunks:BlobPart[]=[];
  recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};
  recorder.onstop=()=>{
   stream.getTracks().forEach(t=>t.stop());
   if(this.stream===stream)this.stream=null;
   if(!this.active)return;
   const clip=new Blob(chunks,{type:recorder.mimeType||'audio/webm'});
   if(spoke&&clip.size>300)void this.process(clip,lastSpeech);
   else void this.deliverTaskResult();
  };
  let spoke=false,spokenMs=0,quietMs=0,elapsed=0,lastSpeech=0;
  const monitor=new AudioContext();this.monitor=monitor;
  const source=monitor.createMediaStreamSource(stream);
  const analyzer=monitor.createAnalyser();analyzer.fftSize=1024;
  source.connect(analyzer);
  const samples=new Float32Array(analyzer.fftSize);
  recorder.start(250);
  this.receive({type:'voice_phase',status:'local_listening'});
  this.tick=setInterval(()=>{
   if(!this.active||recorder.state==='inactive')return;
   analyzer.getFloatTimeDomainData(samples);
   let sum=0;for(let i=0;i<samples.length;i++)sum+=samples[i]*samples[i];
   const rms=Math.sqrt(sum/samples.length);
   elapsed+=60;
   if(elapsed%240===0)this.receive({type:'mic_level',level:Math.min(100,Math.round(rms*500))});
   if(rms>0.012){
    lastSpeech=performance.now();spokenMs+=60;quietMs=0;
    if(spokenMs>160&&!spoke){
     spoke=true;this.receive({type:'voice_phase',status:'user_speaking'});
    }
   }
   else if(spoke)quietMs+=60;
   if((spoke&&quietMs>=950)||elapsed>20000||(!spoke&&(elapsed>=7000||(this.taskResult&&spokenMs===0&&elapsed>=600)))){
    if(this.tick){clearInterval(this.tick);this.tick=null;}
    void monitor.close();if(this.monitor===monitor)this.monitor=null;
    recorder.stop();
   }
  },60);
 }
 private resumeListening(){
  void this.listen().catch(error=>{
   if(!this.active)return;
   this.stop();
   this.receive({type:'error',message:error instanceof Error?error.message:'تعذّر تشغيل الميكروفون'});
  });
 }
 private async process(blob:Blob,lastSpeech:number){
  if(!this.active)return;
  this.receive({type:'voice_phase',status:'utterance_finalized'});
  try{
   const sentAt=performance.now();
   const query=new URLSearchParams({conversation_id:this.chatId,voice_session:this.sessionId,computer:this.computerEnabled?'1':'0'});
   const result=await fetch('/v1/voice/local/command?'+query,{method:'POST',headers:{'Content-Type':blob.type},body:blob,signal:this.request.signal});
   if(!result.ok)throw new Error('فشل تحويل التسجيل لأمر محلي');
   const answer=await result.json() as {transcript?:string;dispatch_ms?:number;status:string;spoken_ar:string;cards?:VoiceEvent['cards'];_ui?:VoiceEvent;needs_approval?:boolean;task_id?:string};
   if(!this.active)return;
   if(answer.dispatch_ms!==undefined)this.receive({type:'voice_metric',status:'execution_start',elapsedMs:Math.round(sentAt-lastSpeech+answer.dispatch_ms)});
   if(answer.transcript)this.receive({type:'input_text',text:answer.transcript});
   if(answer.cards?.length)this.receive({type:'barq_cards',cards:answer.cards});
   this.receive({type:'barq_task',status:answer.status,spoken_ar:answer.spoken_ar,needs_approval:answer.needs_approval,task_id:answer.task_id});
   if(answer._ui)this.receive(answer._ui);
   this.receive({type:'output_text',text:answer.spoken_ar});
   try{
    if(answer.spoken_ar){
     const speech=this.replySpeech=new AbortController();
     const timeout=setTimeout(()=>speech.abort('timeout'),12000);
     try{await this.speak(answer.spoken_ar,speech.signal,lastSpeech);}
     catch(error){if(!speech.signal.aborted||speech.signal.reason==='timeout')throw error;}
     finally{clearTimeout(timeout);this.replySpeech=undefined;}
    }
   }finally{
    if(this.active)this.receive({type:'turn_complete'});
   }
  }catch(e){if(this.active)this.receive({type:'voice_warning',message:e instanceof Error?e.message:'تعذر تنفيذ أمر محلي'})}
  if(this.active)await this.deliverTaskResult();
 }
 private async deliverTaskResult(){
  const result=this.taskResult;
  if(result){
   this.taskPlayback=true;
   const timeout=setTimeout(()=>result.abort.abort(),10000);
   try{await this.speak(result.text,result.abort.signal);}
   catch(e){
    if(this.active&&this.taskResult===result)
     this.receive({type:'voice_warning',message:e instanceof Error?e.message:'تعذّر تشغيل نتيجة المهمة.'});
   }finally{
    clearTimeout(timeout);
    this.taskPlayback=false;
    if(this.taskResult===result)this.taskResult=undefined;
   }
  }
  if(this.active)this.resumeListening();
 }
 private async speak(text:string,signal:AbortSignal,lastSpeech?:number){
  const voice=await fetch('/v1/voice/local/speak',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text}),signal});
  if(!voice.ok)throw new Error('صوت Windows SAPI مش متاح؛ النص موجود في الشات.');
  const wave=await voice.blob();
  if(!this.active||signal.aborted)return;
  const url=URL.createObjectURL(wave);this.lastBlobUrl=url;
  const audio=new Audio(url);
  try{
   const meter=await wavPlaybackMeter(wave,audio).catch(()=>undefined);
   if(!this.active||signal.aborted)return;
   this.playback=audio;
   const detachGlow=bindSpeechGlow(audio,meter);
   const abortPlayback=()=>{audio.pause();this.finishPlayback?.();};
   try{
    await new Promise<void>((resolve,reject)=>{
     this.finishPlayback=resolve;
     signal.addEventListener('abort',abortPlayback,{once:true});
     if(lastSpeech!==undefined)audio.addEventListener('playing',()=>{
      this.receive({type:'voice_metric',status:'first_audio',elapsedMs:Math.round(performance.now()-lastSpeech)});
     },{once:true});
     audio.onended=()=>resolve();
     audio.onerror=()=>reject(new Error('تعذر تشغيل الصوت المحلي.'));
     void audio.play().catch(reject);
    });
   }finally{signal.removeEventListener('abort',abortPlayback);this.finishPlayback=undefined;detachGlow();}
  }finally{
   if(this.playback===audio)this.playback=null;
   URL.revokeObjectURL(url);if(this.lastBlobUrl===url)this.lastBlobUrl='';
  }
 }
}
