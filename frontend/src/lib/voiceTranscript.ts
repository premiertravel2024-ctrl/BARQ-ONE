/** Merge Live transcription chunks. The SDK may emit either cumulative text or deltas. */
export function mergeLiveTranscript(previous:string,chunk:string):string{
 if(!chunk)return previous;
 if(!previous)return chunk;
 if(chunk===previous||previous.endsWith(chunk))return previous;
 if(chunk.startsWith(previous))return chunk;
 const limit=Math.min(previous.length,chunk.length);
 for(let n=limit;n>1;n--)if(previous.endsWith(chunk.slice(0,n)))return previous+chunk.slice(n);
 // Streaming speech chunks often omit the space preceding a new word.
 const spacer=/\s$/.test(previous)||/^\s|^[،,.!?؟:;]/.test(chunk)?'':' ';
 return previous+spacer+chunk;
}
