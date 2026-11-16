import assert from 'node:assert/strict';
import {submitChat} from '../src/lib/chat';
import {useApp} from '../src/store';
import {bindSpeechGlow,acquireSpeechGlow} from '../src/lib/speechGlow';
const memory=new Map<string,string>();
Object.defineProperty(globalThis,'localStorage',{value:{getItem:(k:string)=>memory.get(k)??null,setItem:(k:string,v:string)=>memory.set(k,v),removeItem:(k:string)=>memory.delete(k)}});
const calls:string[]=[];const glow:boolean[]=[];
globalThis.fetch=async(url:any,init:any={})=>{
 const path=String(url);
 if(path==='/v1/voice/wake/speaking'){glow.push(JSON.parse(init.body).active);return new Response('{}');}
 calls.push(path);
 if(path!=='/v1/computer/companion-command')throw Error('Companion command should not reach planner/model: '+path);
 const text=JSON.parse(init.body).text;
 return new Response(JSON.stringify({matched:true,status:text.includes('فريم')?'ok':'opened',message:'نتيجة فعلية للأمر'}));
};
async function run(){
 for(const text of ['شغلي اغنية على اليوتيوب','قيسلي الفريمات','اديني نصايح في اللعب']){
  calls.length=0;useApp.getState().clearAll();useApp.getState().newChat();
  await submitChat(text);
  assert.deepEqual(calls,['/v1/computer/companion-command']);
  assert.equal(useApp.getState().streaming,false);
  assert.ok(useApp.getState().chats[0].messages.at(-1)?.content.includes('نتيجة فعلية'));
 }
 const audio=new EventTarget() as HTMLAudioElement;
 const detach=bindSpeechGlow(audio);
 assert.deepEqual(glow,[],'No glow during synthesis/network wait');
 audio.dispatchEvent(new Event('playing'));audio.dispatchEvent(new Event('playing'));
 assert.deepEqual(glow,[true],'Playing is idempotent');
 audio.dispatchEvent(new Event('waiting'));
 audio.dispatchEvent(new Event('playing'));
 detach();audio.dispatchEvent(new Event('playing'));
 assert.deepEqual(glow,[true,false,true,false],'Buffering, completion and cleanup stop the glow');
 const releaseA=acquireSpeechGlow(),releaseB=acquireSpeechGlow();
 const count=glow.length;releaseA();assert.equal(glow.length,count,'Another speaker still owns glow');releaseB();assert.equal(glow.at(-1),false);
 console.log('PASS companion fast paths and native glow actual-playback lifecycle');
}
void run().catch(error=>{console.error(error);process.exitCode=1});
