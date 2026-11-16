import type {AgentPlan,AgentTask,AgentEdit} from '../store';

export type AgentOutcome={
  workspace?:string;mission_progress?:import('../store').MissionProgress;
  answer:string;task_status?:string;paused?:boolean;blocked?:boolean;failed?:boolean;deferred?:boolean;
  retry_id?:string;retry_reason?:string;retry_after_seconds?:number;next_plan?:AgentPlan|null;pending_edit?:AgentEdit;
  results?:Array<{success:boolean;tool:string;result?:string;error?:string}>;
};

/** One state mapping for the chat composer and its approval cards, without DOM. */
export function outcomeStatus(data:AgentOutcome):AgentTask['status']{
  if(data.task_status==='cancelled')return 'cancelled';
  if(data.paused||data.task_status==='paused')return 'paused';
  if(data.blocked||data.failed||data.task_status==='blocked')return 'failed';
  if(data.deferred||data.task_status==='planning_next')return 'running';
  if(data.results?.some(r=>!r.success))return 'failed';
  if(data.pending_edit||data.next_plan?.plan.steps.length)return 'plan_ready';
  if(data.task_status&&data.task_status!=='completed')return 'paused';
  return 'done';
}

export function applyOutcome(current:AgentTask,data:AgentOutcome):AgentTask{
  const nextSource=data.next_plan?.plan?.steps.find(step=>step.tool==='workspace_edit');
  const proposed=typeof nextSource?.args?.path==='string'&&typeof nextSource.args.content==='string'
    ?{path:nextSource.args.path,content:nextSource.args.content}:data.pending_edit?current.proposedCode:undefined;
  return {...current,phase:data.deferred&&!data.paused&&!data.blocked&&!data.failed?'planning_next':undefined,plan:data.next_plan||undefined,pendingEdit:data.pending_edit,proposedCode:proposed,missionProgress:data.next_plan?.mission_progress||data.mission_progress||current.missionProgress,
    savedEdit:undefined,retryId:data.retry_id,status:outcomeStatus(data),
    summary:data.retry_reason||data.answer,
    evidence:[current.evidence,data.results?.length?JSON.stringify(data.results):''].filter(Boolean).join('\n').slice(-32000)};
}

export function preparationStatus(data:AgentPlan&{failed?:boolean}):AgentTask['status']{
  return outcomeStatus({answer:data.plan.answer,task_status:data.task_status,paused:data.paused,
    failed:data.failed,next_plan:data.plan.steps.length?data:null});
}
