/** Blobs stay in memory, not in localStorage or the conversation database. */
const files=new Map<string,File>();
export function registerAttachment(id:string,file:File){files.set(id,file)}
export function getAttachment(id:string){return files.get(id)}
export function releaseAttachment(id:string){files.delete(id)}
