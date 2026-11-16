import assert from 'node:assert/strict';
import {submitChat} from '../src/lib/chat';
import {useApp} from '../src/store';
const memory=new Map<string,string>();
Object.defineProperty(globalThis,'localStorage',{value:{getItem:(k:string)=>memory.get(k)??null,setItem:(k:string,v:string)=>memory.set(k,v),removeItem:(k:string)=>memory.delete(k)}});
const calls:string[]=[];
globalThis.fetch=async(url:any,init:any={})=>{calls.push(String(url));assert.equal(String(url),'/v1/personal/command');assert.ok(JSON.parse(init.body).text);return new Response(JSON.stringify({matched:true,status:'ok',message:'النتيجة المؤكدة'}));};
async function run(){
 for(const text of ['جهزني للشغل','وقف الأغنية','رجع آخر تغيير','بلغني لما التنزيل يخلص','فكرني بالتقرير لما أفتح Outlook','ترجم المحدد','راقب اداء اللعبة','راقب أداء اللعبة']){
  calls.length=0;useApp.getState().clearAll();useApp.getState().newChat();await submitChat(text);
  assert.deepEqual(calls,['/v1/personal/command']);assert.equal(useApp.getState().streaming,false);
  assert.equal(useApp.getState().chats[0].messages.at(-1)?.content,'النتيجة المؤكدة');
 }
 console.log('PASS personal routines, media, reminders, selection, gaming and undo route locally');
}
void run().catch(error=>{console.error(error);process.exitCode=1});
