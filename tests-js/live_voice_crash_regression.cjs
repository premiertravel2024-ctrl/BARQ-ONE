'use strict';
/* Regression: audio congestion or bad PCM must not terminate a Live call. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=(()=>{try{return require('../frontend/node_modules/typescript')}catch{return require('typescript')}})();
const filename=path.join(__dirname,'../frontend/src/lib/liveVoice.ts');
const compiled=ts.transpileModule(fs.readFileSync(filename,'utf8'),{
  fileName:filename,reportDiagnostics:true,
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}
});
const errors=(compiled.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error);
assert.equal(errors.length,0, 'LiveVoice TypeScript must transpile');
const mod={exports:{}};
const getFetch=()=>Promise.resolve({ok:true});
const glowMod={exports:{}};
const glowSource=fs.readFileSync(path.join(__dirname,'../frontend/src/lib/speechGlow.ts'),'utf8');
new Function('exports','fetch',ts.transpileModule(glowSource,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(glowMod.exports,getFetch);
const localRequire=name=>name==='./speechGlow'?glowMod.exports:require(name);
new Function('module','exports','require','fetch','atob',compiled.outputText)(
  mod,mod.exports,localRequire,getFetch,globalThis.atob
);
const LiveVoice=mod.exports.LiveVoice;
assert.equal(typeof LiveVoice,'function');
function speaker(state='running') {
  const nodes=[];
  return {nodes,state,currentTime:0,destination:{},
    createBuffer(_channels,length,rate){return {duration:length/rate,getChannelData(){return new Float32Array(length)}}},
    createBufferSource(){const node={connect(){},disconnect(){},start(){},stop(){},onended:null};nodes.push(node);return node;}
  };
}
const pcm=Buffer.from([0,0,255,127]).toString('base64');
const events=[];const voice=new LiveVoice(e=>events.push(e));
voice.output=speaker();voice.next=17;
voice.play(pcm);
assert.equal(voice.closed,false);
assert.ok(events.some(e=>e.type==='voice_warning'), 'Should warn and keep call alive after excessive queued output');
assert.equal(voice.playing.size,1);
voice.play('%%%invalid-base64');
assert.equal(voice.closed,false);
assert.ok(events.some(e=>e.type==='voice_warning'&&String(e.message).includes('غير صالحة')));
voice.output=speaker('suspended'); voice.speakerUnlockRequired=false;
voice.play(pcm);
assert.equal(voice.closed,false);
assert.ok(events.some(e=>e.type==='speaker_blocked'));
voice.clearAudio();
console.log('PASS live voice crash regression: backpressure, invalid PCM and suspended output');
