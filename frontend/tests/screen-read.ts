import assert from 'node:assert/strict';
import {submitChat} from '../src/lib/chat';
import {useApp} from '../src/store';
const memory=new Map<string,string>();
Object.defineProperty(globalThis,'localStorage',{value:{getItem:(k:string)=>memory.get(k)??null,setItem:(k:string,v:string)=>memory.set(k,v),removeItem:(k:string)=>memory.delete(k)}});
const calls:string[]=[];let status='ok';
globalThis.fetch=async(url:any)=>{
 const path=String(url);calls.push(path);
 if(path!=='/v1/computer/read-screen')throw Error('Explicit screen reading unexpectedly reached: '+path);
 return new Response(JSON.stringify({status,window:'Local document',text:'نص من النافذة الحالية',error:status==='ok'?'':'OCR unavailable'}));
};
async function run(){
 for(const next of ['ok','unavailable']){
  status=next;calls.length=0;useApp.getState().clearAll();useApp.getState().newChat();
  await submitChat('شوف اللي على الشاشة');
  assert.deepEqual(calls,['/v1/computer/read-screen']);
  assert.equal(useApp.getState().streaming,false);
  const reply=useApp.getState().chats[0].messages.at(-1)?.content||'';
  assert.ok(next==='ok'?reply.includes('نص من النافذة الحالية'):reply.includes('لم أقدر'));
 }
 console.log('PASS explicit screen read stays local, reports unavailable honestly, and clears progress');
}
void run().catch(error=>{console.error(error);process.exitCode=1});
