import assert from 'node:assert/strict';
import {submitChat,retrySavedCommand} from '../src/lib/chat';
import {useApp} from '../src/store';
import {taskMessages} from '../src/lib/backend';
import {outcomeStatus,preparationStatus} from '../src/lib/agentOutcome';
const memory=new Map<string,string>();
Object.defineProperty(globalThis,'localStorage',{value:{getItem:(key:string)=>memory.get(key)??null,setItem:(key:string,value:string)=>memory.set(key,value),removeItem:(key:string)=>memory.delete(key)}});
const calls:Array<{path:string;body:any}>=[];
const longBuildRequest=('برق، عاوزك تبنيلي برنامج Windows كامل اسمه TOFU Desktop Buddy.\n'+
 'لا تكتفي بكتابة شرح أو خطوات أعملها أنا. خلي الأوامر في الشات الأساسي. '+
 'تابع المهمة حتى تنتهي أو يظهر عائق حقيقي. اختبر البرنامج بعد ما تشغله. '.repeat(8)).trim();
const semanticRequest='محتاج الزرار ده يبقى أحمر في المشروع';
let preparePaused=false,resumePaused=false,resumeFail=false,prepareFail=false,chooseLaunch=false;
let unified=false,understandingDown=false;
globalThis.fetch=async (url:any,init:any={})=>{
 const path=String(url),body=JSON.parse(init.body||'{}');calls.push({path,body});
 let response:any;
 if(path==='/v1/brain/command'||path==='/v1/brain/command/retry'){
   if(!unified)return new Response(JSON.stringify({detail:'Older backend fixture'}),{status:404});
   if(understandingDown)return new Response(JSON.stringify({intent:null,command_id:'saved-command',pending_command:{id:'saved-command',status:'waiting_model',goal:longBuildRequest,diagnostic:{summary:'Saved',attempts:[{model:'test/free',code:'auth',message:'راجع مفتاح المزود'}]}}}),{status:200});
   return new Response(JSON.stringify({intent:{kind:'coding',goal:'Resume the saved project request',requires_approval:true},command_id:'saved-command'}),{status:200});
 }
 if(path==='/v1/launch/resolve'&&body.text.length>240)return new Response(JSON.stringify({detail:[{loc:['body','text'],msg:'String should have at most 240 characters',type:'string_too_long'}]}),{status:422});
 if(path==='/v1/agent/prepare'&&prepareFail)return new Response(JSON.stringify({detail:'HTTP 503'}),{status:503,headers:{'Content-Type':'application/json'}});
 if(path==='/v1/agent/prepare'&&preparePaused)response={plan_id:'',plan:{steps:[],answer:'خدمة النموذج متوقفة',reason:''},paused:true,retry_id:'retry-prepare',task_status:'paused'};
 else if(path==='/v1/agent/retry-plan')response={answer:'خطة جديدة فقط',next_plan:{plan_id:'next-plan',plan:{steps:[{tool:'workspace_list',args:{}}],answer:'جاهز',reason:''}},task_status:'awaiting_approval'};
 else if(path==='/v1/agent/resume'&&resumeFail)throw new Error('resume network interrupted');
 else if(path==='/v1/agent/resume'&&resumePaused)response={answer:'الملف محفوظ والنموذج متوقف',paused:true,retry_id:'retry-save',task_status:'paused'};
 else if(path==='/v1/launch/resolve'&&chooseLaunch)response={decision:'choose',text_ar:'اختار التطبيق',candidates:[{id:'a',label:'A'},{id:'b',label:'B'}]};
 else if(path==='/v1/launch/resolve')response=body.text==='افتح يوتيوب'?{decision:'auto',text_ar:'هفتح يوتيوب.',candidates:[{id:'site-youtube',kind:'site',label:'يوتيوب',path_or_appid:'https://www.youtube.com',score:1,risk:'low'}]}:{decision:'not_command',text_ar:'',candidates:[]};
 else if(path==='/v1/launch/execute')response={status:'opened',candidate:{label:'يوتيوب'},audit_id:'mock-audit-1'};
 else if(path==='/v1/brain/route'){const text=body.messages.at(-1)?.content;response=text===semanticRequest?{intent:{kind:'coding',goal:'Change save button to red',requires_approval:true}}:text==='حلله'?{intent:{kind:'rea',goal:'Analyze previous program',requires_approval:true}}:text==='كمل'?{intent:null,clarification:'تقصد أكمل أي مهمة؟ حدّد البرنامج أو المشروع.'}:text.includes('الهندسه')?{intent:null,reply:'اختار البرنامج لتحليله بأداة REA.',tool_request:{integration:'rea',intent:'capability',enabled:true,runner_available:true,connected:false,status:'not_tested'}}:{intent:null};}
 else if(path==='/v1/router/chat/stream'){const reply=body.messages.at(-1)?.content==='انقطع'?'رد جزئي':'أنا برق، عامل إيه؟';const events=[{name:'model',value:{model:'mock/free',provider:'mock',attempts:[]}},{name:'token',value:{content:reply}}];if(body.messages.at(-1)?.content!=='انقطع')events.push({name:'done',value:{}} as any);return new Response(events.map(e=>`event: ${e.name}\ndata: ${JSON.stringify(e.value)}\n\n`).join(''),{headers:{'Content-Type':'text/event-stream'}});}
 else if(path==='/v1/agent/task-intent')response=body.text==='حلله'
  ?{intent:{kind:'rea',goal:'Analyze previous program',requires_approval:true}}
  :(body.text==='اعمل برنامج'||body.text===longBuildRequest||(body.text==='حاول'&&body.previous_user_texts.at(-1)===longBuildRequest))
    ?{intent:{kind:'coding',goal:'Build a real app',requires_approval:true}}
    :body.text==='كمل'?{intent:null,clarification:'تقصد أكمل أي مهمة؟ حدّد البرنامج أو المشروع.'}:{intent:null};
 else if(path==='/v1/integrations/intent')response={tool_request:{integration:'rea',intent:'capability',message_ar:'اختار البرنامج لتحليله بأداة REA.',enabled:true,runner_available:true,connected:false,status:'not_tested'}};
 else if(path==='/v1/agent/prepare')response={plan_id:'p',plan:{steps:[{tool:'rea_analyze',args:{name:'real_tool'}}],answer:'Ready',reason:'Analysis'},preparation_results:[{tool:'workspace_read',success:true,result:'Actual code evidence'}]};
 else if(path==='/v1/agent/execute')response={answer:'Tool completed',results:[{tool:'rea_analyze',success:true,result:'Verified analysis'}],pending_edit:{approval_id:'edit1',path:'app.py',diff:'proposed change'}};
 else if(path==='/v1/workspace/edit/apply')response={backup_id:'b1',path:'app.py'};
 else if(path==='/v1/agent/resume')response={answer:'Saved and checked',next_plan:null};
 else throw new Error('Unexpected external/chat call: '+path);
 return new Response(JSON.stringify(response),{status:200,headers:{'Content-Type':'application/json'}});
};
async function main(){
 useApp.getState().clearAll();
 await submitChat('تقدر تحللي برنامج بالهندسه العكسية ؟');
 let chat=useApp.getState().chats[0];
 assert.equal(chat.messages.at(-1)?.toolRequest?.integration,'rea');
 assert.equal(useApp.getState().streaming,false);
 useApp.getState().setWorkspace('/test/project');
 await submitChat('حلله');
 chat=useApp.getState().chats[0];
 const task=chat.messages.at(-1)?.agentTask;
 assert.equal(task?.status,'plan_ready');assert.ok(task?.evidence?.includes('Actual code evidence'));
 assert.notEqual(task?.summary,'window is not defined','Planning must work without a browser window');
 // Explicit contextual actions use the local classifier (faster than a
 // second cloud routing request), but must retain the prior user context.
 const classifier=calls.filter(c=>c.path==='/v1/agent/task-intent').at(-1)!;
 assert.equal(classifier.body.text,'حلله');
 assert.equal(classifier.body.previous_user_texts.at(-1),'تقدر تحللي برنامج بالهندسه العكسية ؟');
 assert.equal(calls.filter(c=>c.path==='/v1/brain/route').length,1,
   'The initial ambiguous capability question may use the brain; the explicit REA action must not route twice');
 assert.ok(taskMessages(chat.messages).at(-1)?.content.includes('Actual code evidence'));
 assert.equal(calls.some(c=>c.path==='/v1/agent/execute'),false);
 await submitChat('نفذ');
 let latest=useApp.getState().chats[0].messages.at(-1)!;
 assert.equal(latest.agentTask?.pendingEdit?.approval_id,'edit1');
 assert.equal(calls.filter(c=>c.path==='/v1/agent/execute').length,1);
 await submitChat('احفظ');
 latest=useApp.getState().chats[0].messages.at(-1)!;
 assert.equal(latest.agentTask?.status,'done');assert.ok(latest.agentTask?.evidence?.includes('Saved: app.py'));
 assert.equal(calls.filter(c=>c.path==='/v1/workspace/edit/apply').length,1);
 useApp.getState().newChat();await submitChat('كمل');
 assert.ok(useApp.getState().chats[0].messages.at(-1)?.content.includes('أي مهمة'));
 useApp.getState().newChat();
 const originalNow=Date.now;Date.now=()=>12345;
 try{await submitChat('ازيك')}finally{Date.now=originalNow}
 latest=useApp.getState().chats[0].messages.at(-1)!;
 assert.equal(latest.content,'أنا برق، عامل إيه؟','Fast final chunks must never be appended twice');
 assert.equal(latest.isStreaming,false);
 assert.equal(calls.filter(c=>c.path==='/v1/router/chat/stream').at(-1)?.body.conversation_id,useApp.getState().activeId);
 await submitChat('انقطع');
 latest=useApp.getState().chats[0].messages.at(-1)!;
 assert.equal(latest.content,'رد جزئي');assert.equal(latest.incomplete,true);
 const brainCallCount=calls.filter(c=>c.path==='/v1/brain/route').length;
 useApp.getState().newChat();await submitChat('افتح يوتيوب');
 latest=useApp.getState().chats[0].messages.at(-1)!;
 assert.equal(latest.content,'تمام، فتحتلك يوتيوب.');
 // Keep the launch resolver AND the executor in this runtime regression test:
 // resolving a known local command must not call a cloud brain first.
 const resolvedLaunches=calls.filter(c=>c.path==='/v1/launch/resolve');
 assert.ok(resolvedLaunches.length>0,'launch resolver must be called for explicit desktop commands');
 assert.equal(resolvedLaunches.at(-1)?.body.text,'افتح يوتيوب','launch resolver must receive the original user command');
 assert.equal(calls.filter(c=>c.path==='/v1/brain/route').length,brainCallCount,'Local launcher must not call the cloud brain');
 assert.equal(calls.filter(c=>c.path==='/v1/launch/execute').at(-1)?.body.candidate_id,'site-youtube');
 // A buggy browser panel listener must never corrupt an approved agent plan.
 const originalWindow=Object.getOwnPropertyDescriptor(globalThis,'window');
 const originalWarn=console.warn;
 const workspaceEvents:string[]=[];
 try{
   Object.defineProperty(globalThis,'window',{configurable:true,value:{dispatchEvent:(event:Event)=>{
     workspaceEvents.push(event.type);throw new Error('mock workspace panel failure');
   }}});
   console.warn=()=>{};
   useApp.getState().newChat();
   await submitChat('اعمل برنامج');
   latest=useApp.getState().chats[0].messages.at(-1)!;
   assert.equal(latest.agentTask?.status,'plan_ready','UI navigation errors must not mark an agent plan as failed');
   assert.equal(latest.agentTask?.plan?.plan_id,'p');
   assert.deepEqual(workspaceEvents,['barq-open-workspace']);
 }finally{
   console.warn=originalWarn;
   if(originalWindow)Object.defineProperty(globalThis,'window',originalWindow);
   else Reflect.deleteProperty(globalThis,'window');
 }
 assert.equal(outcomeStatus({answer:'needs input',task_status:'needs_input'}),'paused');
 assert.equal(outcomeStatus({answer:'failed',blocked:true,next_plan:{plan:{steps:[{}]}} as any}),'failed');
 const planned={plan_id:'p',plan:{steps:[],reason:'',answer:''},expires_in_seconds:0};
 assert.equal(preparationStatus({...planned,paused:true,retry_id:'r'}),'paused');
 useApp.getState().newChat();
 const beforeSSE=calls.filter(c=>c.path==='/v1/router/chat/stream').length;
 const beforeExecute=calls.filter(c=>c.path==='/v1/agent/execute').length;
 preparePaused=true;await submitChat('اعمل برنامج');preparePaused=false;
 latest=useApp.getState().chats[0].messages.at(-1)!;
 assert.equal(latest.agentTask?.status,'paused');assert.equal(latest.agentTask?.retryId,'retry-prepare');
 await submitChat('حاول تاني');
 latest=useApp.getState().chats[0].messages.at(-1)!;
 assert.equal(latest.agentTask?.status,'plan_ready');
 assert.equal(calls.filter(c=>c.path==='/v1/agent/execute').length,beforeExecute,'Retry must not execute tools');
 assert.equal(calls.filter(c=>c.path==='/v1/router/chat/stream').length,beforeSSE,'Execution outages must not become tutorials');
 await submitChat('نفذ');
 resumePaused=true;await submitChat('احفظ');resumePaused=false;
 latest=useApp.getState().chats[0].messages.at(-1)!;
 assert.equal(latest.agentTask?.status,'paused');assert.equal(latest.agentTask?.retryId,'retry-save');
 const saves=calls.filter(c=>c.path==='/v1/workspace/edit/apply').length;
 await submitChat('كمل');
 assert.equal(calls.filter(c=>c.path==='/v1/workspace/edit/apply').length,saves);
 useApp.getState().newChat();await submitChat('اعمل برنامج');await submitChat('نفذ');
 resumeFail=true;await submitChat('احفظ');resumeFail=false;
 latest=useApp.getState().chats[0].messages.at(-1)!;
 assert.equal(latest.agentTask?.status,'paused');assert.equal(latest.agentTask?.pendingEdit,undefined);
 assert.equal(latest.agentTask?.savedEdit?.backupId,'b1');
 const afterInterruptedSave=calls.filter(c=>c.path==='/v1/workspace/edit/apply').length;
 await submitChat('كمل');
 assert.equal(calls.filter(c=>c.path==='/v1/workspace/edit/apply').length,afterInterruptedSave,'A saved receipt must never write again');
 assert.equal(useApp.getState().chats[0].messages.at(-1)?.agentTask?.status,'done');
 useApp.getState().newChat();prepareFail=true;await submitChat('اعمل برنامج');prepareFail=false;
 assert.equal(useApp.getState().chats[0].messages.at(-1)?.agentTask?.status,'failed');
 useApp.getState().newChat();chooseLaunch=true;await submitChat('افتح برنامج');chooseLaunch=false;
 assert.ok(useApp.getState().chats[0].messages.at(-1)?.content.includes('1. A'),'Ambiguous launch must work without window');
 useApp.getState().newChat();
 const launchCount=calls.filter(c=>c.path==='/v1/launch/resolve').length;
 const executionCount=calls.filter(c=>c.path==='/v1/launch/execute'||c.path==='/v1/agent/execute').length;
 await submitChat(longBuildRequest);
 latest=useApp.getState().chats[0].messages.at(-1)!;
 assert.equal(latest.agentTask?.status,'plan_ready','Long project requests must reach planning, not fail in the 240-character launcher');
 assert.equal(calls.filter(c=>c.path==='/v1/launch/resolve').length,launchCount);
 assert.equal(calls.filter(c=>c.path==='/v1/agent/prepare').at(-1)?.body.messages.at(-1).content,longBuildRequest,'Planning must receive the entire request');
 assert.equal(calls.filter(c=>c.path==='/v1/launch/execute'||c.path==='/v1/agent/execute').length,executionCount,'Routing a project request must not execute tools');
 const streamCount=calls.filter(c=>c.path==='/v1/router/chat/stream').length;
 await submitChat('حاول');
 assert.equal(useApp.getState().chats[0].messages.at(-1)?.agentTask?.status,'plan_ready','A retry must prepare the previous task instead of returning a model disclaimer');
 assert.equal(calls.filter(c=>c.path==='/v1/agent/task-intent').at(-1)?.body.previous_user_texts.at(-1),longBuildRequest);
 useApp.getState().newChat();
 await submitChat(semanticRequest);
 assert.equal(useApp.getState().chats[0].messages.at(-1)?.agentTask?.status,'plan_ready','A request without a known action keyword must reach semantic planning');
 assert.equal(calls.filter(c=>c.path==='/v1/brain/route').at(-1)?.body.messages.at(-1)?.content,semanticRequest);
 assert.equal(calls.filter(c=>c.path==='/v1/router/chat/stream').length,streamCount,'An understood action must not fall through to explanatory chat');
 useApp.getState().newChat();
 await submitChat('البرنامج شغال دلوقتي');
 assert.equal(calls.filter(c=>c.path==='/v1/launch/resolve').length,launchCount,'A word inside ordinary chat is not a launch command');
 unified=true;understandingDown=true;
 useApp.getState().newChat();
 const beforeUnifiedStream=calls.filter(c=>c.path==='/v1/router/chat/stream').length;
 await submitChat(longBuildRequest);
 let savedChat=useApp.getState().chats[0];latest=savedChat.messages.at(-1)!;
 assert.equal(latest.pendingCommand?.id,'saved-command','An outage must expose a resumable saved command');
 assert.equal(calls.filter(c=>c.path==='/v1/router/chat/stream').length,beforeUnifiedStream,'Do not substitute explanatory chat for a waiting command');
 const beforeUnifiedExecution=calls.filter(c=>c.path==='/v1/agent/execute').length;
 understandingDown=false;
 await retrySavedCommand(savedChat.id,latest.id);
 latest=useApp.getState().chats[0].messages.at(-1)!;
 assert.equal(latest.agentTask?.status,'plan_ready');
 assert.equal(calls.filter(c=>c.path==='/v1/brain/command/retry').at(-1)?.body.command_id,'saved-command');
 assert.equal(calls.filter(c=>c.path==='/v1/agent/prepare').at(-1)?.body.command_id,'saved-command','Prepared steps must bind to the saved command, not re-interpret an assistant error');
 assert.equal(calls.filter(c=>c.path==='/v1/agent/execute').length,beforeUnifiedExecution);
 console.log('PASS: local launch, contextual agent planning, UI notification resilience, approvals, saving, SSE streaming, paused preparation, saved-file recovery, retry without tool replay');
}
void main().catch(e=>{console.error(e);process.exitCode=1});
