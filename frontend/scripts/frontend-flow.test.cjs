/** Behavioral contract tests for the real TS backend adapter. No paid keys/network. */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');
const content=fs.readFileSync(path.join(__dirname,'../src/lib/backend.ts'),'utf8');
const transpiled=ts.transpileModule(content,{fileName:'backend.ts',compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}});
assert.equal((transpiled.diagnostics||[]).length,0);
function backend(fetch){
 const exports={};
 vm.runInNewContext(transpiled.outputText,{
   exports,require(){throw new Error('Unexpected runtime dependency')},fetch,Headers,FormData,
   TextDecoder,AbortController,JSON,Promise,console,Uint8Array,Response
 });
 return exports;
}
test('dynamic models must come from backend, not a hardcoded brand',async()=>{
 const app=backend(async(path)=>{
  assert.equal(path,'/v1/router/models');
  return new Response(JSON.stringify({models:[{id:'ollama/qwen3',provider:'ollama',kind:'local',strengths:['coding'],configured:true,enabled:true,available:true,priority:50,remaining_today:null}]}),{status:200,headers:{'Content-Type':'application/json'}});
 });
 const entries=await app.loadModels();
 assert.equal(entries.length,1);assert.equal(entries[0].id,'ollama/qwen3');assert.equal(entries[0].local,true);assert.equal(entries[0].quality,'Strong');
});
test('provider UI loads disabled reason from backend response',async()=>{
 const app=backend(async()=>new Response(JSON.stringify({providers:[{name:'x',enabled:false,disabled_reason_ar:'حصة غير مؤكدة'}]}),{status:200}));
 const providers=await app.loadProviders();assert.equal(providers[0].disabled_reason_ar,'حصة غير مؤكدة');
});
test('API JSON errors preserve server status',async()=>{
 const app=backend(async()=>new Response(JSON.stringify({detail:'rate limited'}),{status:429}));
 await assert.rejects(app.requestJSON('/v1/chat/completions'),e=>e.status===429&&e.message==='rate limited');
});
test('validation errors retain the field and cause without echoing rejected input',async()=>{
 const app=backend(async()=>new Response(JSON.stringify({detail:[{loc:['body','text'],msg:'String should have at most 240 characters',input:'private project requirements'}]}),{status:422}));
 await assert.rejects(app.requestJSON('/v1/launch/resolve'),e=>e.status===422&&e.message.includes('body.text')&&e.message.includes('240')&&!e.message.includes('private project'));
});
test('SSE streaming reconstructs UTF-8 split chunks and verifies done',async()=>{
 const text='event: model\ndata: {"model":"ollama/a","provider":"ollama","attempts":[],"offline":true,"cached":false}\n\n'+
 'event: token\ndata: {"content":"تمام"}\n\nevent: done\ndata: {}\n\n';
 const encoded=new TextEncoder().encode(text);
 const stream=new ReadableStream({start(controller){const n=Math.floor(encoded.length/2);controller.enqueue(encoded.slice(0,n));controller.enqueue(encoded.slice(n));controller.close()}});
 const uiContext='BARQ application context: Music';
 const app=backend(async(_path,init)=>{
  const body=JSON.parse(init.body);
  assert.deepEqual(body.messages[0],{role:'system',content:uiContext});
  assert.equal(body.messages[1].role,'user');
  return new Response(stream,{status:200,headers:{'Content-Type':'text/event-stream'}});
 });
 const msgs=[{id:'one',role:'user',content:'مرحبا',createdAt:1}];
 const opts={systemPrompt:'',localOnly:true,temperature:.7,maxTokens:128};
 const events=[];for await(const e of app.streamChat(msgs,'auto',opts,new AbortController().signal,[],'chat-test',uiContext))events.push(e);
 assert.deepEqual(Array.from(events,e=>e.type),['model','token','done']);assert.equal(events[1].value,'تمام');
});

test('store actions preserve chat identity and update only targeted messages',()=>{
 const src=fs.readFileSync(path.join(__dirname,'../src/store/index.ts'),'utf8');
 const js=ts.transpileModule(src,{fileName:'index.ts',compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 const exports={};
 let state;
 function create(){return initializer=>{
   const get=()=>state;
   const set=next=>{state={...state,...(typeof next==='function'?next(state):next)}};
   state=initializer(set,get);
   const useApp=select=>select(state);
   useApp.getState=get;
   useApp.subscribe=()=>()=>{};
   return useApp;
 }}
 const safeStore={getItem(){return null},setItem(){},removeItem(){}};
 vm.runInNewContext(js,{
   exports,require(name){if(name==='zustand')return {create};if(name==='zustand/middleware')return {persist:fn=>fn,createJSONStorage:()=>safeStore};throw Error(name)},
   crypto:globalThis.crypto,Math,Date,JSON,globalThis,localStorage:safeStore,console
 });
 const app=exports.useApp; const id=app.getState().newChat();
 app.getState().addMessage(id,{id:'u1',role:'user',content:'مرحبا',createdAt:1});
 app.getState().addMessage(id,{id:'a1',role:'assistant',content:'أهلا',createdAt:2});
 app.getState().updateMessage(id,'a1',{content:'اتفضل'});
 assert.equal(app.getState().chats[0].messages[1].content,'اتفضل');
 assert.equal(app.getState().chats[0].messages[0].content,'مرحبا');
 app.getState().deleteChat(id);
 assert.equal(app.getState().chats.length,0);
});
