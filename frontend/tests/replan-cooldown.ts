/** Temporary model cooldowns can retry planning, but never replay approved tools. */
import assert from 'node:assert/strict';
import {useApp,type AgentTask} from '../src/store';
import {retryTaskPlan} from '../src/lib/taskActions';
import {pendingApproval} from '../src/lib/approvals';
const saved=new Map<string,string>();
Object.defineProperty(globalThis,'localStorage',{value:{getItem:(key:string)=>saved.get(key)??null,setItem:(key:string,value:string)=>saved.set(key,value),removeItem:(key:string)=>saved.delete(key)}});
const paths:string[]=[];
let attempts=0;
globalThis.fetch=async (url:any)=>{
 const path=String(url);paths.push(path);
 assert.equal(path,'/v1/agent/retry-plan','Automatic retries must only request a fresh plan');
 attempts++;
 const result=attempts===1
  ?{answer:'Provider cooldown',paused:true,retry_id:'r-cooldown',retry_after_seconds:0.1}
  :{answer:'Next action ready',next_plan:{plan_id:'p-cooldown',expires_in_seconds:600,plan:{steps:[{tool:'workspace_edit',args:{path:'app/main.py',content:'print(1)'}}],answer:'Ready',reason:'Continue'}}};
 return new Response(JSON.stringify(result),{status:200});
};
async function main(){
 useApp.getState().clearAll();
 const chatId=useApp.getState().newChat();
 const task:AgentTask={kind:'coding',goal:'Continue the saved project',status:'paused',retryId:'r-cooldown',summary:'Temporary model cooldown'};
 useApp.getState().addMessage(chatId,{id:'mission',role:'assistant',content:'Paused',createdAt:1,agentTask:task});
 await retryTaskPlan(chatId,'mission');
 const updated=useApp.getState().chats[0].messages.at(-1)!.agentTask!;
 assert.equal(updated.status,'plan_ready');
 assert.equal(updated.phase,undefined);
 assert.equal(updated.plan?.plan_id,'p-cooldown');
 assert.equal(pendingApproval(useApp.getState().chats[0].messages)?.token,'p-cooldown');
 assert.equal(attempts,2,'Retry the planning request only once after a cooldown');
 assert.ok(paths.every(path=>path==='/v1/agent/retry-plan'));
 assert.equal(useApp.getState().taskActions[chatId],false,'The task lock must be released');
 console.log('PASS: explicit cooldown automatically retries planning, without executing tools or leaving a busy spinner');
}
void main().catch(error=>{console.error(error);process.exitCode=1});
