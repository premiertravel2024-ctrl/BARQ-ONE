import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

export type Language = 'en'|'ar';
export type Theme = 'dark'|'light';
export type Role = 'user'|'assistant';
export type UploadedAttachment = {id:string;name:string;size:number;type:string;url?:string;progress:number};
export type ToolRequest = {integration:'rea';intent:'request'|'capability';status:'disabled'|'runner_missing'|'not_tested';enabled:boolean;runner_available:boolean;requires_approval:boolean;connected:boolean};
export type AgentStep={tool:string;args:Record<string,unknown>};
export type MissionProgress={interface_review?:{checked_files:number;visual_verified:boolean;issues:Array<{path:string;line:number;message:string}>;warnings:Array<{path:string;line:number;message:string}>};planning_required?:boolean;requirements?:Array<{id:string;title:string;acceptance:string;files:string[];tests:string[];status:string}>;checks?:Array<{name:string;status:string}>;mission_id:string;files:Array<{path:string;status:string;attempts:number;last_error?:string;model?:string;recovery?:{kind:string;action:string}|null}>;calls_used:number;call_budget:number};
export type AgentPlan={mission_progress?:MissionProgress;task_id?:string;task_status?:string;paused?:boolean;retry_id?:string;retry_reason?:string;plan_id:string;plan:{answer:string;reason:string;steps:AgentStep[]};expires_in_seconds:number};
export type AgentEdit={approval_id:string;path:string;diff:string;quality?:{valid:boolean;errors?:string[]}};
export type AgentTask={autopilot?:boolean;phase?:'executing'|'saving'|'planning_next';commandId?:string;taskId?:string;kind:'coding'|'computer';goal:string;status:'workspace_needed'|'plan_ready'|'running'|'paused'|'done'|'failed'|'cancelled';retryId?:string;savedEdit?:{approvalId:string;backupId:string;path:string};plan?:AgentPlan;pendingEdit?:AgentEdit;proposedCode?:{path:string;content:string};missionProgress?:MissionProgress;summary?:string;evidence?:string};
export type PendingCommand={id:string;status:'waiting_model';goal:string;diagnostic:{summary:string;attempts:Array<{model:string;code:string;message:string}>;actions?:string[]}};
export type ToolHandoff={integration:'rea'|'coding'|'computer';goal:string;tab:'tools'|'agent'|'computer'|'github'};
export type StudioCodeHandoff={chatId:string;messageId:string};
export type Message = {pendingCommand?:PendingCommand;agentTask?:AgentTask;toolRequest?:ToolRequest;metrics?:{latency_seconds:number;time_to_first_token_seconds:number;characters_per_second:number;output_characters:number};incomplete?:boolean;id:string;role:Role;content:string;createdAt:number;model?:string;provider?:string;dataUse?:string;attempts?:string[];offline?:boolean;cached?:boolean;attachments?:UploadedAttachment[];rating?:'like'|'dislike';isStreaming?:boolean;reasoning?:string};
export type Conversation = {id:string;title:string;createdAt:number;updatedAt:number;messages:Message[];pinned:boolean};
export type ChatOptions = {temperature:number;maxTokens:number;systemPrompt:string;localOnly:boolean};
export type Notice = {id:string;kind:'success'|'error'|'info';title:string;description?:string};
export type Model = {id:string;name:string;provider:string;speed:'Fast'|'Balanced'|'Deep';quality:'Strong'|'Good';local?:boolean;available?:boolean;unavailableReason?:string};
export const models:Model[] = [{id:'auto',name:'Auto (best free model)',provider:'Router',speed:'Balanced',quality:'Strong'}];
export const uid = () => globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
const safeStorage = {getItem:(key:string)=>{try{return localStorage.getItem(key)}catch{return null}},setItem:(key:string,value:string)=>{try{localStorage.setItem(key,value)}catch{console.warn('Storage quota unavailable')}},removeItem:(key:string)=>{try{localStorage.removeItem(key)}catch{/* storage unavailable */}}};
const initialOptions:ChatOptions={temperature:.7,maxTokens:4096,systemPrompt:'',localOnly:false};
type State={
  taskActions:Record<string,boolean>;setTaskAction:(chatId:string,busy:boolean)=>void;
  theme:Theme;language:Language;voiceId:string;setVoiceId:(id:string)=>void;sidebarCollapsed:boolean;sidebarOpen:boolean;rightOpen:boolean;
  activeId:string|null;selectedModel:string;chats:Conversation[];options:ChatOptions;notices:Notice[];availableModels:Model[];workspace:string;
  streaming:boolean;streamingId:string|null;toolHandoff:ToolHandoff|null;setToolHandoff:(handoff:ToolHandoff|null)=>void;studioCodeHandoff:StudioCodeHandoff|null;setStudioCodeHandoff:(ref:StudioCodeHandoff|null)=>void;
  setTheme:(theme:Theme)=>void;toggleTheme:()=>void;setLanguage:(l:Language)=>void;
  setSidebarCollapsed:(v:boolean)=>void;setSidebarOpen:(v:boolean)=>void;setRightOpen:(v:boolean)=>void;
  setModel:(id:string)=>void;setAvailableModels:(items:Model[])=>void;setWorkspace:(path:string)=>void;importChats:(items:Conversation[])=>void;setOptions:(patch:Partial<ChatOptions>)=>void;
  newChat:()=>string;selectChat:(id:string)=>void;renameChat:(id:string,title:string)=>void;pinChat:(id:string)=>void;deleteChat:(id:string)=>void;
  addMessage:(id:string,message:Message)=>void;updateMessage:(id:string,messageId:string,patch:Partial<Message>)=>void;
  editMessage:(id:string,messageId:string,text:string)=>void;trimAfter:(id:string,messageId:string)=>void;
  setStreaming:(v:boolean,id?:string|null)=>void;toast:(kind:Notice['kind'],title:string,description?:string)=>void;dismissToast:(id:string)=>void;
  clearAll:()=>void;
};
const updateChat=(chats:Conversation[],id:string,cb:(c:Conversation)=>Conversation)=>chats.map(c=>c.id===id?{...cb(c),updatedAt:Date.now()}:c);
export const useApp=create<State>()(persist((set,get)=>({
  taskActions:{},setTaskAction:(chatId,busy)=>set(s=>({taskActions:{...s.taskActions,[chatId]:busy}})),
  theme:'dark',language:'ar',voiceId:'Charon',setVoiceId:voiceId=>set({voiceId}),sidebarCollapsed:false,sidebarOpen:false,rightOpen:false,
  activeId:null,selectedModel:'auto',chats:[],options:initialOptions,notices:[],availableModels:[models[0]],workspace:'',streaming:false,streamingId:null,toolHandoff:null,setToolHandoff:toolHandoff=>set({toolHandoff}),studioCodeHandoff:null,setStudioCodeHandoff:studioCodeHandoff=>set({studioCodeHandoff}),
  setTheme:theme=>set({theme}),toggleTheme:()=>set(s=>({theme:s.theme==='dark'?'light':'dark'})),setLanguage:language=>set({language}),
  setSidebarCollapsed:sidebarCollapsed=>set({sidebarCollapsed}),setSidebarOpen:sidebarOpen=>set({sidebarOpen}),setRightOpen:rightOpen=>set({rightOpen}),
  setModel:selectedModel=>set({selectedModel}),setAvailableModels:items=>set({availableModels:[models[0],...items.filter(m=>m.id!=='auto')]}),setWorkspace:workspace=>set({workspace}),
  importChats:items=>set(s=>({chats:[...s.chats,...items.filter(c=>!s.chats.some(local=>local.id===c.id))].sort((a,b)=>b.updatedAt-a.updatedAt)})),setOptions:patch=>set(s=>({options:{...s.options,...patch}})),
  newChat:()=>{const active=get().chats.find(c=>c.id===get().activeId);if(active&&!active.messages.length){set({sidebarOpen:false});return active.id}const id=uid(),now=Date.now();set(s=>({chats:[{id,title:s.language==='ar'?'محادثة جديدة':'New chat',createdAt:now,updatedAt:now,messages:[],pinned:false},...s.chats],activeId:id,sidebarOpen:false}));return id},
  selectChat:activeId=>set({activeId,sidebarOpen:false}),
  renameChat:(id,title)=>set(s=>({chats:updateChat(s.chats,id,c=>({...c,title:title.trim().slice(0,100)||c.title}))})),
  pinChat:id=>set(s=>({chats:updateChat(s.chats,id,c=>({...c,pinned:!c.pinned}))})),
  deleteChat:id=>set(s=>({chats:s.chats.filter(c=>c.id!==id),activeId:s.activeId===id?null:s.activeId})),
  addMessage:(id,message)=>set(s=>({chats:updateChat(s.chats,id,c=>({...c,title:c.messages.length===0 && message.role==='user'?message.content.slice(0,42)||c.title:c.title,messages:[...c.messages,message]}))})),
  updateMessage:(id,messageId,patch)=>set(s=>({chats:updateChat(s.chats,id,c=>({...c,messages:c.messages.map(m=>m.id===messageId?{...m,...patch}:m)}))})),
  editMessage:(id,messageId,text)=>set(s=>({chats:updateChat(s.chats,id,c=>({...c,messages:c.messages.map(m=>m.id===messageId?{...m,content:text}:m)}))})),
  trimAfter:(id,messageId)=>set(s=>({chats:updateChat(s.chats,id,c=>({...c,messages:c.messages.slice(0,c.messages.findIndex(m=>m.id===messageId)+1)}))})),
  setStreaming:(streaming,streamingId=null)=>set({streaming,streamingId}),
  toast:(kind,title,description)=>{const id=uid();set(s=>({notices:[...s.notices.slice(-3),{id,kind,title,description}]}));},
  dismissToast:id=>set(s=>({notices:s.notices.filter(n=>n.id!==id)})),
  clearAll:()=>{if(get().streaming)return;set({chats:[],activeId:null})}
}),{name:'ai-router-premium-ui-v2',storage:createJSONStorage(()=>safeStorage),partialize:s=>({theme:s.theme,language:s.language,voiceId:s.voiceId,sidebarCollapsed:s.sidebarCollapsed,activeId:s.activeId,selectedModel:s.selectedModel,workspace:s.workspace,options:s.options,chats:s.chats.map(c=>({...c,messages:c.messages.map(m=>({...m,isStreaming:false,agentTask:m.agentTask?.phase?{...m.agentTask,phase:undefined,status:m.agentTask.retryId||m.agentTask.savedEdit?'paused':'failed'}:m.agentTask,attachments:m.attachments?.map(({url:_url,...rest})=>rest)}))}))})}));
