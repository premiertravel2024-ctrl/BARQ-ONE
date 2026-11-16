// Tests the browser PCM capture -> WebSocket -> Gemini events -> audible output.
// No fake success claims: this runs a deterministic fake browser, not a microphone.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=(()=>{
 const paths=[process.env.TYPESCRIPT_MODULE,path.join(__dirname,'../frontend/node_modules/typescript'),process.env.NODE_PATH && path.join(process.env.NODE_PATH,'typescript'),'/opt/nvm/versions/node/v22.16.0/lib/node_modules/typescript'];
 for(const modulePath of paths){if(!modulePath)continue;try{return require(modulePath)}catch{}}
 try{return require('typescript')}catch{throw new Error('TypeScript not installed: run npm ci in BARQ/frontend first')}
})();
const source=fs.readFileSync(path.join(__dirname,'../frontend/src/lib/liveVoice.ts'),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const messages=[],events=[],sent=[],contexts=[];
let lastSocket,lastInput,lastOutput;let inputCreated=false;let echoCancellation=true;
class FakeContext {
 constructor(opts){if(process.env.BARQ_FAKE_48K==='1'&&opts?.sampleRate===16000)throw new Error('NotSupportedError: 16000 unavailable');this.sampleRate=opts?.sampleRate||(inputCreated&&process.env.BARQ_FAKE_48K==='1'?48000:24000);this.state='running';this.currentTime=0;this.destination={};this.audioWorklet={addModule:async(file)=>{assert.equal(file,'/audio/live-capture.js')}};if(!inputCreated){lastInput=this;inputCreated=true;}else lastOutput=this;}
 async resume(){this.state='running'} async close(){this.state='closed'}
 createMediaStreamSource(){return {connect(){},disconnect(){}}}
 createGain(){return {gain:{value:1},connect(){},disconnect(){}}}
 createBuffer(ch,n,sr){assert.equal(sr,24000);return {duration:n/sr,getChannelData(){return new Float32Array(n)}}}
 createBufferSource(){const out={buffer:null,connect(){},disconnect(){},start(){out.started=true; if(out.onended)setTimeout(()=>out.onended?.(),Math.max(50,(out.buffer?.duration||0)*1000))},stop(){out.stopped=true}};contexts.push(out);return out}
}
class FakeSocket {
 static OPEN=1;
 constructor(url){assert.match(url,/\/v1\/voice\/live\?/);this.url=url;this.readyState=1;this.bufferedAmount=0;lastSocket=this;}
 send(data){sent.push(data)}
 close(){this.readyState=3;this.onclose?.()}
 emit(data){this.onmessage?.({data:JSON.stringify(data)})}
}
class FakeCapture {constructor(){this.port={onmessage:null};} connect(){} disconnect(){} sendPcm(rms){const pcm=new Int16Array(1024);pcm.fill(Math.round(rms*32767));this.port.onmessage?.({data:pcm.buffer});}}
const ctx={exports:{},console,Int16Array,Float32Array,ArrayBuffer,Date,performance,Math,Promise,DataView,Uint8Array,AbortController,setTimeout,clearTimeout,setInterval,clearInterval,
 AudioContext:FakeContext,AudioWorkletNode:FakeCapture,WebSocket:FakeSocket,
 navigator:{mediaDevices:{getUserMedia:async()=>({getAudioTracks:()=>[{enabled:true,getSettings:()=>({echoCancellation})}],getTracks:()=>[{stop(){}}]})}},
 location:{protocol:'http:',host:'127.0.0.1:8765'},fetch:async(url)=>{
  if(url!=='/v1/voice/speak')return {ok:true};
  const wav=Buffer.alloc(44+48000);
  wav.write('RIFF',0);wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);
  wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(24000,24);wav.writeUInt16LE(16,34);
  wav.write('data',36);wav.writeUInt32LE(48000,40);
  return {ok:true,arrayBuffer:async()=>Uint8Array.from(wav).buffer};
 },atob:globalThis.atob};
const glowSource=fs.readFileSync(path.join(__dirname,'../frontend/src/lib/speechGlow.ts'),'utf8');
const glowContext={exports:{},fetch:ctx.fetch,setInterval,clearInterval};
vm.runInNewContext(ts.transpileModule(glowSource,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,glowContext);
ctx.require=name=>{assert.equal(name,'./speechGlow');return glowContext.exports;};
vm.runInNewContext(compiled,ctx,{filename:'liveVoice.js'});
const LiveVoice=ctx.exports.LiveVoice;
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function main(){
 const client=new LiveVoice(e=>events.push(e));
 await client.start('Charon',[],false,'testchat');
 assert(lastSocket);assert.equal(lastInput.sampleRate,process.env.BARQ_FAKE_48K==='1'?24000:16000);assert(lastOutput);
 lastSocket.emit({type:'ready'});
 assert(sent.some(e=>typeof e==='string'&&JSON.parse(e).type==='context'));
 for(let i=0;i<6;i++)client.capture.port.onmessage({data:new Int16Array(1024).fill(6500).buffer});
 for(let i=0;i<20;i++)client.capture.port.onmessage({data:new Int16Array(1024).buffer});
 assert(sent.some(e=>typeof e==='string'&&JSON.parse(e).type==='end_audio'),'No end-of-utterance frame after silence');
 lastSocket.emit({type:'audio_relay'});
 lastSocket.emit({type:'voice_phase',status:'execution_started'});
 const chunk=Buffer.alloc(480);lastSocket.emit({type:'audio',data:chunk.toString('base64')});
 await delay(820);
 assert(contexts.some(c=>c.started),'Audio reply did not enter speaker playback');
 assert(events.some(e=>e.type==='voice_phase'&&e.status==='mic_streaming'));
 assert(events.some(e=>e.type==='playback_done'));
 assert(events.some(e=>e.type==='voice_metric'&&e.status==='first_audio'&&e.elapsedMs>=0));
 assert(events.some(e=>e.type==='voice_metric'&&e.status==='execution_start'&&e.elapsedMs>=0));
 client.interruptPlayback();
 assert(sent.some(e=>typeof e==='string'&&JSON.parse(e).type==='interrupt_output'));
 const chunks=contexts.length;
 lastSocket.emit({type:'audio',data:chunk.toString('base64')});
 assert.equal(contexts.length,chunks,'late audio resumed an interrupted reply');
 await delay(180);
 // Repeat a second utterance without reopening call; verifies natural back-and-forth.
 const before=sent.filter(e=>typeof e==='string'&&JSON.parse(e).type==='end_audio').length;
 for(let i=0;i<6;i++)client.capture.port.onmessage({data:new Int16Array(1024).fill(6500).buffer});
 for(let i=0;i<20;i++)client.capture.port.onmessage({data:new Int16Array(1024).buffer});
 assert.equal(sent.filter(e=>typeof e==='string'&&JSON.parse(e).type==='end_audio').length,before+1);
 lastSocket.emit({type:'turn_complete'});
 assert.equal(client.announceTaskResult('خلصت المهمة واتأكدت من النتيجة.','Charon'),true);
 await delay(15);
 const taskSpeaker=contexts.at(-1);
 assert(taskSpeaker.started&&taskSpeaker!==contexts[chunks-1],'verified task completion produced no audio');
 const sentBefore=sent.length;
 for(let i=0;i<4;i++)client.capture.sendPcm(.003);
 assert.equal(sent.length,sentBefore,'speaker echo leaked to the server');
 echoCancellation=false;
 for(let i=0;i<3;i++)client.capture.sendPcm(.12);
 assert.equal(sent.length,sentBefore,'acoustic interrupt ran without device echo cancellation');
 echoCancellation=true;
 client.capture.sendPcm(.12);
 assert.equal(sent.length,sentBefore,'a single residual noise frame caused an interrupt');
 client.capture.sendPcm(.12);
 assert.equal(JSON.parse(sent[sentBefore]).type,'interrupt_output');
 assert(taskSpeaker.stopped,'spoken interrupt left the completion audio running');
 assert(events.some(e=>e.type==='voice_phase'&&e.status==='spoken_interrupt'));
 assert(sent.slice(sentBefore+1).filter(e=>e instanceof ArrayBuffer).length>=2,'interruption clipped the first input frame');
 const beforeCancelled=contexts.length;
 assert(client.announceTaskResult('خلصت المهمة.','Charon'));
 client.cancelTaskResult();
 await delay(15);
 assert.equal(contexts.length,beforeCancelled,'a cancelled result played after fetch');
 // A missing turn_complete or no audio reply must not block later task results.
 client.awaitingReplyAt=Date.now()-16000;
 client.lastResponseAt=Date.now()-16000;
 client.turnActive=true;
 client.interruptedTurnPending=true;
 assert(client.announceTaskResult('المهمة وقفت.','Charon'));
 await delay(15);
 assert.equal(contexts.length,beforeCancelled);
 client.recoverIdleTurn();
 assert.equal(client.awaitingReplyAt,0);
 assert(events.some(e=>e.status==='reply_timed_out'));
 client.resetSpeech();
 client.playTaskResult();
 assert.equal(contexts.length,beforeCancelled+1,'stalled live turn prevented task result audio');
 assert.equal(client.announceTaskResult('نتيجة تانية','Charon'),false,'busy audio must apply backpressure');
 client.stop();assert.equal(lastSocket.readyState,3);
 console.log('PASS: 2 audio utterances + 2 end markers + playable 24kHz PCM + clean shutdown');
}
main().catch(err=>{console.error(err);process.exitCode=1});

async function localVoiceRegression(){
 const filename=path.join(__dirname,'../frontend/src/lib/localVoice.ts');
 const localSource=ts.transpileModule(fs.readFileSync(filename,'utf8'),{
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}
 }).outputText;
 const localEvents=[];
 let pendingSpeech;
 let listening=0;
 const localContext={
  exports:{},AbortController,URLSearchParams,crypto:require('node:crypto').webcrypto,
  performance,setTimeout,clearTimeout,
  require:name=>{assert.equal(name,'./speechGlow');return glowContext.exports;},
  fetch:async(url,options)=>{
   if(url.startsWith('/v1/voice/local/command?')){
    return {ok:true,json:async()=>({transcript:'افتح الآلة الحاسبة',status:'started',spoken_ar:'بدأت المهمة',task_id:'task-a'})};
   }
   return await new Promise((resolve,reject)=>{
    pendingSpeech={resolve,signal:options.signal};
    options.signal.addEventListener('abort',()=>reject(new Error('Speech interrupted')),{once:true});
   });
  }
 };
 vm.runInNewContext(localSource,localContext,{filename});
 const voice=new localContext.exports.LocalVoice(event=>localEvents.push(event));
 voice.active=true;
 voice.resumeListening=()=>{listening++;};
 const processing=voice.process(new Blob(['local']),0);
 await delay(0);
 assert(pendingSpeech);
 voice.interruptPlayback();
 await processing;
 assert(pendingSpeech.signal.aborted,'interrupt must cancel synthesis before playback starts');
 assert.equal(localEvents.filter(e=>e.type==='turn_complete').length,1);
 assert.equal(listening,1);
 assert.equal(localEvents.filter(e=>e.type==='voice_warning').length,0);
 const failing=voice.process(new Blob(['local']),0);
 await delay(0);
 pendingSpeech.resolve({ok:false});
 await failing;
 assert.equal(localEvents.filter(e=>e.type==='turn_complete').length,2,'failed synthesis must finalize and keep the transcript');
 assert.equal(listening,2,'microphone must resume after synthesis fails');
 assert.equal(localEvents.filter(e=>e.type==='voice_warning').length,1);
 voice.stop();
}
localVoiceRegression().catch(error=>{console.error(error);process.exitCode=1;});
