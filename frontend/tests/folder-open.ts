import assert from 'node:assert/strict';
import {submitChat} from '../src/lib/chat';
import {useApp} from '../src/store';
const memory=new Map<string,string>();
Object.defineProperty(globalThis,'localStorage',{value:{getItem:(k:string)=>memory.get(k)??null,setItem:(k:string,v:string)=>memory.set(k,v),removeItem:(k:string)=>memory.delete(k)}});
const calls:string[]=[];let mode='exact';
globalThis.fetch=async(url:any,init:any={})=>{
 const path=String(url);calls.push(path);
 const body=JSON.parse(init.body||'{}');
 if(path==='/v1/launch/resolve'){
  assert.equal(body.text,'افتح فولدر IATA REPORT');
  return new Response(JSON.stringify({decision:mode==='exact'?'auto':mode==='missing'?'not_found':'choose',
   intent:{target_kind:'folder',target_text:'IATA REPORT'},text_ar:mode==='missing'?'الاسم غير موجود في نطاق البحث الحالي.':'اختار المكان الصحيح.',
   candidates:mode==='missing'?[]:[{id:'verified-folder-id',label:'IATA REPORT',kind:'folder',path_or_appid:'D:/Reports/IATA REPORT',score:1,risk:'low'}]}));
 }
 if(path==='/v1/launch/execute'){assert.equal(body.candidate_id,'verified-folder-id');return new Response(JSON.stringify({status:'opened'}));}
 throw Error('A simple folder command must not reach planning/model endpoints: '+path);
};
async function run(){
 for(const next of ['exact','missing','ambiguous']){
  mode=next;calls.length=0;useApp.getState().clearAll();useApp.getState().newChat();
  await submitChat('افتح فولدر IATA REPORT');
  assert.equal(calls.includes('/v1/brain/command'),false);
  assert.equal(calls.includes('/v1/computer/start'),false);
  assert.equal(calls.filter(p=>p==='/v1/launch/execute').length,next==='exact'?1:0);
  assert.equal(useApp.getState().streaming,false,'No endless local spinner after the folder result');
  const reply=useApp.getState().chats[0].messages.at(-1)?.content||'';
  assert.ok(next==='exact'?reply.includes('فتحتلك'):next==='missing'?reply.includes('غير موجود'):reply.includes('D:/Reports/IATA REPORT'));
 }
 console.log('PASS folder command: exact path opens once, missing/ambiguous never start a planner, spinner stops');
}
void run().catch(error=>{console.error(error);process.exitCode=1});
