// Device-rate PCM regression: Windows 44.1k/48k microphones must be converted
// to 16k PCM, not merely relabeled. This executes the real AudioWorklet source.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const script=fs.readFileSync(path.join(root,'frontend/public/audio/live-capture.js'),'utf8');
assert.equal(script,fs.readFileSync(path.join(root,'web/react/audio/live-capture.js'),'utf8'));
function capture(rate,channels=1){
 const out=[];let Processor;
 class Worklet {
   constructor(){this.port={postMessage(buffer){out.push(new Int16Array(buffer).slice())}};}
 }
 vm.runInNewContext(script,{AudioWorkletProcessor:Worklet,sampleRate:rate,Math,Int16Array,
  registerProcessor(name,value){assert.equal(name,'barq-capture');Processor=value}});
 const p=new Processor();
 const total=Math.round(rate/10); // 100 ms of audio
 for(let at=0;at<total;at+=128){
  const count=Math.min(128,total-at);
  const sine=Float32Array.from({length:count},(_,i)=>Math.sin(2*Math.PI*440*(at+i)/rate)*.4);
  const inputs=[[sine,...(channels===2?[sine]:[])]];
  assert.equal(p.process(inputs),true);
 }
 const merged=Int16Array.from(out.flatMap(frame=>Array.from(frame)));
 assert.equal(merged.length,1600,`${rate}Hz audio must become 1600 16kHz samples`);
 assert.ok(merged.every(n=>n<=32767&&n>=-32768));
 const rms=Math.sqrt(merged.reduce((n,v)=>n+(v/32768)**2,0)/merged.length);
 assert.ok(rms>.20&&rms<.35,`${rate}Hz amplitude should be preserved: ${rms}`);
 let crossings=0;
 for(let i=1;i<merged.length;i++)if(merged[i-1]<=0&&merged[i]>0)crossings++;
 assert.ok(crossings>=43&&crossings<=45,`${rate}Hz 440Hz pitch distortion: ${crossings}`);
 console.log(`PASS: ${rate}Hz -> 16000Hz, ${out.length} x 20ms packets, pitch+amplitude intact`);
}
for(const rate of [16000,32000,44100,48000])capture(rate);
capture(48000,2);
