/** Real upstream streaming for the BARQ Studio. No timers, fake typing, or file writes. */
import {APIError} from './backend';
export type StudioRequest = {workspace:string;path:string;include_file:boolean;selection:string;prompt:string;model:string};
export type StudioEvent = {type:'token';content:string}|{type:'model';model:string}|{type:'routing';status:string}|{type:'done'};
export type GeneratedBlock = {language:string;filename:string;content:string;complete:boolean};

export function generatedBlocks(response:string):GeneratedBlock[]{
 const result:GeneratedBlock[]=[];
 // Stream-safe parser: an unfinished fenced block stays visible while tokens arrive.
 const expression=/```([^\n]*)\n/g;let match:RegExpExecArray|null;
 while((match=expression.exec(response))!==null){
  const spec=match[1].trim();const end=response.indexOf('```',expression.lastIndex);
  const value=end<0?response.slice(expression.lastIndex):response.slice(expression.lastIndex,end);
  const candidates=spec.split(/\s+/);const filename=candidates.find(item=>/[\\/]|\.(?:py|tsx?|jsx?|css|html|json|md|rs|go|java|sql|yaml|yml)$/.test(item))||'';
  result.push({language:candidates[0]||'text',filename,content:value,complete:end>=0});
  if(end>=0)expression.lastIndex=end+3;
 }
 return result.slice(0,20);
}

export async function* streamStudio(request:StudioRequest, signal:AbortSignal):AsyncGenerator<StudioEvent>{
 const result=await fetch('/v1/studio/assistant/stream',{
  method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json'},
  body:JSON.stringify(request),signal
 });
 if(!result.ok){let error='خطأ في الاتصال بمساعد المشروع';try{const data=await result.json() as {detail?:string};error=data.detail||error}catch{}throw new APIError(error,result.status)}
 if(!result.body)throw new APIError('لا يوجد بث مباشر من النموذج',503);
 const reader=result.body.getReader(),decoder=new TextDecoder();let buffer='',ended=false,completed=false;
 try{
  while(!ended){const part=await reader.read();if(part.done){buffer+=decoder.decode();ended=true}else buffer+=decoder.decode(part.value,{stream:true});
   const events=buffer.replace(/\r\n/g,'\n').split('\n\n');buffer=events.pop()||'';
   for(const event of events){const kind=event.split('\n').find(line=>line.startsWith('event:'))?.slice(6).trim();const body=event.split('\n').filter(line=>line.startsWith('data:')).map(line=>line.slice(5).trim()).join('\n');if(!kind||!body)continue;
    const data=JSON.parse(body) as Record<string,unknown>;
    if(kind==='error')throw new APIError(String(data.message||'حدث خطأ أثناء توليد الكود'),503);
    if(kind==='token')yield {type:'token',content:String(data.content||'')};
    if(kind==='routing')yield {type:'routing',status:String(data.status||'جاري اختيار الموديل')};
    if(kind==='model')yield {type:'model',model:String(data.model||'')};
    if(kind==='done'){completed=true;yield {type:'done'}}
   }
  }
  if(!completed && !signal.aborted)throw new APIError('انقطع البث قبل اكتمال الرد',503);
 }finally{if(!ended)await reader.cancel().catch(()=>{});reader.releaseLock()}
}
