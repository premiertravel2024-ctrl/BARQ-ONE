/** Isolated state owners reduce accidental rerenders and make future unit tests practical. */
import {useState} from 'react';

export type Layout={side:number;ai:number;bottom:number;showBottom:boolean;showAI:boolean;zen:boolean};
export const DEFAULT_LAYOUT:Layout={side:238,ai:314,bottom:165,showBottom:false,showAI:false,zen:false};
export function useWorkspaceLayout(){return useState<Layout>(DEFAULT_LAYOUT)}

export function useWorkspaceFiles<T extends {path:string}>(){
  const [files,setFiles]=useState<T[]>([]);
  const [activeFile,setActiveFile]=useState('');
  return {files,setFiles,activeFile,setActiveFile};
}
export function useWorkspaceAI(){
  const [ask,setAsk]=useState('');const [reply,setReply]=useState('');const [replyModel,setReplyModel]=useState('');
  const [streamStatus,setStreamStatus]=useState('');
  const [includeFile,setIncludeFile]=useState(false);const [aiLoading,setAiLoading]=useState(false);
  return {ask,setAsk,reply,setReply,replyModel,setReplyModel,streamStatus,setStreamStatus,includeFile,setIncludeFile,aiLoading,setAiLoading};
}
export function useWorkspaceMonitor<T>(){
  const [monitorDraft,setMonitorDraft]=useState<T|null>(null);
  const [monitorProject,setMonitorProject]=useState<T|null>(null);
  const [previewSafety,setPreviewSafety]=useState<T|null>(null);
  const [monitorSource,setMonitorSource]=useState<'draft'|'project'>('draft');
  const [monitorBusy,setMonitorBusy]=useState(false);
  const [projectScanBusy,setProjectScanBusy]=useState(false);
  return {monitorDraft,setMonitorDraft,monitorProject,setMonitorProject,previewSafety,setPreviewSafety,monitorSource,setMonitorSource,monitorBusy,setMonitorBusy,projectScanBusy,setProjectScanBusy};
}
