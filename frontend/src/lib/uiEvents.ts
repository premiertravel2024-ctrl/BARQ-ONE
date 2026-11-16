/** Navigation must never alter the outcome of an already completed API action. */
export function notifyUI(name:string,detail?:unknown):void{
  if(typeof window==='undefined'||typeof window.dispatchEvent!=='function')return;
  try{window.dispatchEvent(detail===undefined?new Event(name):new CustomEvent(name,{detail}))}
  catch(error){console.warn('BARQ navigation notification failed',error)}
}
