/** Leased native glow follows audible playback across all speech sources. */
const audioPlayers=new Set<HTMLAudioElement>();
const leases=new Map<symbol,(()=>number)|undefined>();let timer:ReturnType<typeof setInterval>|undefined;
export function isSpeechPlaying(){return leases.size>0;}
function notifyPlayback(){if(typeof window!=='undefined')window.dispatchEvent(new Event('barq-speech-playback'));}
function send(active:boolean){void fetch('/v1/voice/wake/speaking',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({active})}).catch(()=>{});}
export function speechPlaybackLevel():number|null{
 let level:number|null=null;
 for(const read of leases.values())if(read)level=Math.max(level??0,read());
 return level;
}
export function acquireSpeechGlow(level?:()=>number):()=>void{
 const id=Symbol();leases.set(id,level);
 if(leases.size===1){notifyPlayback();send(true);timer=setInterval(()=>send(true),1500);}
 return ()=>{if(!leases.delete(id)||leases.size)return;if(timer){clearInterval(timer);timer=undefined;}notifyPlayback();send(false);};
}
function bindPlaybackGlow(target:EventTarget,startEvent:string,stopEvents:string[],level?:()=>number):()=>void{
 let release:(()=>void)|undefined;
 const stop=()=>{release?.();release=undefined;};
 const start=()=>{release??=acquireSpeechGlow(level);};
 target.addEventListener(startEvent,start);
 for(const event of stopEvents)target.addEventListener(event,stop);
 return ()=>{stop();target.removeEventListener(startEvent,start);for(const event of stopEvents)target.removeEventListener(event,stop);};
}
export function bindSpeechGlow(audio:HTMLAudioElement,level?:()=>number):()=>void{audioPlayers.add(audio);const detach=bindPlaybackGlow(audio,'playing',['pause','ended','error','waiting','stalled'],level);return()=>{detach();audioPlayers.delete(audio)};}
export function stopSpeechPlayback(){for(const audio of audioPlayers)audio.pause();if(typeof window!=='undefined')window.speechSynthesis?.cancel();}
export function bindUtteranceGlow(utterance:SpeechSynthesisUtterance):()=>void{return bindPlaybackGlow(utterance,'start',['end','error','pause']);}
