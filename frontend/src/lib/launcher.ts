import {requestJSON} from './backend';
export type LaunchCandidate={id:string;kind:'app'|'file'|'folder'|'site';label:string;path_or_appid:string;score:number;risk:string};
export type LaunchResponse={decision:'auto'|'choose'|'ask_approval'|'not_found'|'blocked'|'not_command'|'selected';candidates:LaunchCandidate[];text_ar:string;intent?:{target_text?:string;target_kind?:string}|null;transcript?:string;execution?:LaunchExecution};
export type LaunchExecution={status:'opened'|'approval'|'blocked';approval_id?:string;reason?:string;candidate?:{label:string};audit_id?:string};
/** A short, directly typed opening command may use the desktop launcher.
 * Words embedded in a project specification must not hijack the whole task.
 * Keep the raw length within the launch API contract; never truncate a goal.
 */
export function isLaunchCommand(text:string):boolean{
 if(!text.trim()||text.length>240)return false;
 const value=text.normalize('NFKC').replace(/[\u064B-\u065F\u0670\u0640]/g,'').replace(/[إأآ]/g,'ا').trim();
 if(/(?:شيت|اكس[يل]+|excel|workbook|spreadsheet|وورد|word|باوربوينت|powerpoint)/i.test(value)&&/^(?:(?:يا برق|لو سمحت|ممكن)\s+)*(?:اعمل(?:لي|ي)?|انشئ|جهز(?:لي)?|create|make)\s+/i.test(value))return true;
 return /^(?:(?:يا\s+(?:برق|barq)|لو\s+سمحت|من\s+فضلك|ممكن|بالله\s+عليك|please|hey\s+barq)\s+)*(?:افتح(?:لي|ي|هالي|هولي|ه)?|تفتح(?:لي)?|فتحلي|شغل(?:لي|هالي|ه)?|تشغل(?:لي)?|وريني|هاتلي|(?:عايز|عاوز)(?:ك)?\s+(?:افتح|تفتح|تشغل)|نفسي\s+افتح|روح\s+ل|روح\s+علي|ارجع\s+ل|open|launch|start|run|show\s+me|3ayez\s+aft[aeh]7|efta7|efta7li|eshaghal|shaghal)(?:\s+|$)/i.test(value);
}
export async function resolveLaunch(text:string,source:'text'|'voice'|'palette'='text',query_only=false){
 return requestJSON<LaunchResponse>('/v1/launch/resolve',{method:'POST',body:JSON.stringify({text,source,query_only})});
}
export async function executeLaunch(candidate_id:string,approval_token?:string){
 return requestJSON<LaunchExecution>('/v1/launch/execute',{method:'POST',body:JSON.stringify({candidate_id,approval_token})});
}
export async function confirmLaunch(id:string):Promise<LaunchExecution>{
 let result=await executeLaunch(id);
 if(result.status==='approval'){
  if(!window.confirm(`برق محتاج موافقتك قبل التشغيل.\n${result.reason||''}\nموافق تفتح العنصر المحدد؟`)){
    await requestJSON('/v1/launch/deny',{method:'POST',body:JSON.stringify({candidate_id:id})}).catch(()=>{});return {status:'blocked',reason:'ألغيت التنفيذ.'};
  }
  result=await executeLaunch(id,result.approval_id);
 }
 return result;
}
