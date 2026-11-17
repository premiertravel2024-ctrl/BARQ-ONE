// Execute the actual headless controller with fake audio/React surfaces.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const ts=require('../frontend/node_modules/typescript');
const source=fs.readFileSync(path.join(__dirname,'../frontend/src/components/chat/HandsFreeVoice.tsx'),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText;
let receiver,refresh,statusSnapshot,speakerBusy=false,statusError;const saveSnapshots=[];const announcements=[];const sent=[],warnings=[],cleanups=[],lookups=[],sessions=[],appActions=[];
const state={activeId:'chat-1',streaming:false,chats:[{id:'chat-1',messages:[]}],
 selectChat:id=>{state.activeId=id},toast:(...v)=>warnings.push(v),newChat:()=>state.activeId,
 addMessage:(id,m)=>state.chats.find(c=>c.id===id).messages.push(m),
 updateMessage:(id,mid,patch)=>Object.assign(state.chats.find(c=>c.id===id).messages.find(m=>m.id===mid),patch),voiceId:'male'};
const store=Object.assign(selector=>selector(state),{getState:()=>state,subscribe:()=>()=>{}});
class FakeVoice{constructor(callback){receiver=callback;sessions.push(callback)}async start(){}stop(){}sendWorkState(){}sendChatContext(){} announceTaskResult(text){if(speakerBusy)return false;announcements.push(text);return true} cancelTaskResult(){}}
const win=new EventTarget();
win.setInterval=f=>{refresh=async()=>{f();await new Promise(r=>setImmediate(r))};return 1};win.clearInterval=()=>{};
const hooks={useRef:v=>({current:v}),useState:v=>[typeof v==='function'?v():v,()=>{}],useCallback:f=>f,
 useEffect:f=>{const cleanup=f();if(cleanup)cleanups.push(cleanup)}};
class APIError extends Error{constructor(status){super(String(status));this.status=status;}}
const mods={react:hooks,'react/jsx-runtime':{jsx:()=>null,jsxs:()=>null,Fragment:'fragment'},
 '../../lib/appContext':{openAppSection:action=>appActions.push(action)},
 '../../lib/liveVoice':{LiveVoice:FakeVoice},'../../lib/localVoice':{LocalVoice:FakeVoice},
 '../../lib/backend':{APIError,requestJSON:async(path,{signal}={})=>{
  if(path==='/v1/voice/speaker')return new Promise(resolve=>lookups.push(resolve));
  assert(signal instanceof AbortSignal,'desktop lookups must have a bounded request');
  if(statusError)throw new Error('network unavailable');
  if(path==='/v1/computer/status')return statusSnapshot;
  const task=statusSnapshot.checkpoints[path.split('/').at(-1)];
  if(!task)throw new APIError(404);
  return task;
 },saveConversation:async chat=>saveSnapshots.push(chat.messages.map(m=>m.agentTask?.status))},
 '../../store':{useApp:store},'../../lib/voiceTranscript':{mergeLiveTranscript:(a,b)=>a+b},
 '../../lib/chat':{submitChat:async text=>sent.push([state.activeId,text])},
 '../ui/Modal':{},'../ui/Button':{}};
const context={exports:{},require:name=>{assert.ok(name in mods,`unexpected import ${name}`);return mods[name]},
 window:win,Event,CustomEvent,AbortSignal,crypto:require('node:crypto').webcrypto,Date,console,
 setInterval,clearInterval,setTimeout,clearTimeout};
vm.runInNewContext(compiled,context);
(async()=>{
 context.exports.HandsFreeVoice();
 const start=()=>win.dispatchEvent(new CustomEvent('barq-handsfree-start',{detail:{computerEnabled:true}}));
 start();start();
 assert.equal(lookups.length,1,'repeated starts during speaker lookup must use one session');
 win.dispatchEvent(new Event('barq-handsfree-stop'));start();
 assert.equal(lookups.length,2);
 for(const resolve of lookups)resolve({speaker:'gemini'});
 await new Promise(r=>setImmediate(r));assert.ok(receiver);
 assert.equal(sessions.length,1,'the stopped session must not reopen the microphone');
 const previous=receiver;
 win.dispatchEvent(new Event('barq-handsfree-stop'));start();
 lookups.at(-1)({speaker:'gemini'});
 await new Promise(r=>setImmediate(r));
 assert.equal(sessions.length,2);
 previous({type:'closed'});
 assert.equal(context.exports.isHandsFreeActive(),true,'a stale close cannot stop a newer session');
 const appAction={type:'barq_app_action',app_action:{section:'music',mode:'anghami'}};
 previous(appAction);
 assert.equal(appActions.length,0,'stopped voice sessions must not navigate the current app');
 receiver(appAction);
 assert.deepEqual(appActions,[appAction.app_action]);
 const event={type:'chat_task_requested',text:'ابنيلي برنامج حسابات واديني exe',request_id:'request-1',conversation_id:'chat-1'};
 receiver(event);receiver(event);
 assert.deepEqual(sent,[['chat-1',event.text]],'duplicate handoff must not execute twice');
 receiver({...event,request_id:'request-2',conversation_id:'another-chat'});
 assert.equal(sent.length,1,'wrong conversation must not execute');
 state.streaming=true;receiver({...event,request_id:'request-3'});
 assert.equal(sent.length,1,'busy chat must not discard an in-flight task');
 assert.equal(warnings.length,2);
 const runTask=(id,goal)=>{
  receiver({type:'input_text',text:goal});
  receiver({type:'barq_task',status:'started',task_id:id,spoken_ar:'بدأت المهمة'});
  receiver({type:'turn_complete'});
 };
 runTask('first-task','افتح المجلد');
 statusSnapshot={task:{id:'second-task',status:'running'},settings:{enabled:true},
   checkpoints:{'first-task':{id:'first-task',goal:'افتح المجلد',status:'completed',goal_proof:{status:'verified'},message:'تم فتح المجلد'}}};
 speakerBusy=true;
 statusError=true;await refresh();
 statusError=false;await refresh();
 assert.equal(announcements.length,0,'a second result must wait while the speaker is busy');
 speakerBusy=false;
 await refresh();await refresh();
 assert.equal(announcements.length,1,'completed task should be read once despite repeated polling');
 assert.match(announcements[0],/اتأكدت/);
 let assistant=state.chats[0].messages.filter(m=>m.agentTask?.taskId==='first-task');
 assert.equal(assistant.length,1,'task result must update the original receipt');
 assert.equal(assistant[0].agentTask.status,'done');
 runTask('missing-task','افتح ملف');
 await refresh();
 const missing=state.chats[0].messages.find(m=>m.agentTask?.taskId==='missing-task');
 assert.equal(missing.agentTask.status,'failed','a missing checkpoint must replace the indefinite running state');
 assert.match(missing.content,/مقدرتش أتحقق/);
 assert(saveSnapshots.some(snapshot=>snapshot.includes('done')),'terminal state should be persisted');
 runTask('second-task','افتح التطبيق');
 win.dispatchEvent(new Event('barq-handsfree-stop'));
 statusSnapshot.task={id:'second-task',status:'needs_review',goal:'افتح التطبيق',message:'النافذة لم تظهر'};
 await refresh();
 assistant=state.chats[0].messages.filter(m=>m.agentTask?.taskId==='second-task');
 assert.equal(assistant.length,1);
 assert.equal(assistant[0].agentTask.status,'failed','unverified execution should never appear as success');
 assert.equal(announcements.length,2,'stopped voice sessions must not read pending results');
 for(const cleanup of cleanups)cleanup();
 console.log('PASS actual voice controller: chat command dispatch, duplicate protection, chat binding and busy handling');
})().catch(e=>{for(const cleanup of cleanups)cleanup();console.error(e);process.exitCode=1});
