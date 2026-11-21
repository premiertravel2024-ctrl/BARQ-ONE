const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');
const {TextEncoder}=require('node:util');

const source=fs.readFileSync(path.join(__dirname,'..','src','lib','readingLocalState.ts'),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{
 module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,
}}).outputText;

function harness(){
 const records=new Map();
 const cache=new Map();
 let online=false;
 let writes=0;
 const localStorage={
  get length(){return cache.size;},
  key:(i)=>Array.from(cache.keys())[i]??null,
  getItem:(k)=>cache.get(k)??null,
  setItem:(k,v)=>cache.set(k,String(v)),
  removeItem:(k)=>cache.delete(k),
 };
 const requestJSON=async (url,options={})=>{
  if(!online)throw new Error('Backend offline');
  const body=options.body?JSON.parse(options.body):{};
  if(url.endsWith('/flush')){
   for(const [key,value] of Object.entries(body.records))records.set(key,value);
   return {saved:Object.keys(body.records).length};
  }
  if(url.endsWith('/sync')){
   for(const [key,value] of Object.entries(body.records))
    if(!records.has(key))records.set(key,value);
   return {records:Object.fromEntries(records)};
  }
  const key=decodeURIComponent(url.slice(url.lastIndexOf('/')+1));
  if(options.method==='PUT'){
   writes++;
   records.set(key,body.value);
   return {saved:true};
  }
  return {value:records.get(key)??null};
 };
 function mount(){
  const m={exports:{}};
  const context={
   module:m,exports:m.exports,TextEncoder,localStorage,
   CustomEvent:class CustomEvent{constructor(name,options){this.type=name;this.detail=options?.detail;}},
   Event:class Event{constructor(name){this.type=name;}},
   window:{dispatchEvent:()=>{}},
   require:(name)=>{
    assert.equal(name,'./backend');
    return {requestJSON};
   },
  };
  vm.runInNewContext(compiled,context,{filename:'readingLocalState.js'});
  return m.exports;
 }
 return {records,cache,mount,setOnline(v){online=v;},get writes(){return writes;}};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));

test('unconfirmed offline progress remains in outbox after restart and replays over stale SQLite',async()=>{
 const backend=harness();
 const key='barq-reader:google:fiction';
 backend.records.set(key,'{"page":4,"marks":[]}');
 const first=backend.mount();
 first.saveReadingLocalState(key,'{"page":91,"marks":[91]}');
 await tick();
 assert.equal(first.getReadingStorageStatus().pending,1);
 assert.ok(backend.cache.has('barq-reading-pending-v2'));
 // Recreate the entire JS module to emulate WebView/app restart.
 const restarted=backend.mount();
 backend.setOnline(true);
 await restarted.hydrateReadingLocalState();
 assert.equal(backend.records.get(key),'{"page":91,"marks":[91]}');
 assert.equal(backend.cache.get(key),'{"page":91,"marks":[91]}');
 assert.equal(restarted.getReadingStorageStatus().pending,0);
 assert.equal(backend.cache.has('barq-reading-pending-v2'),false);
});
test('two rapid edits use the latest page, never an old network response',async()=>{
 const backend=harness();
 backend.setOnline(true);
 const reader=backend.mount();
 const key='barq-reader:google:fast';
 reader.saveReadingLocalState(key,'{"page":6}');
 reader.saveReadingLocalState(key,'{"page":7}');
 await tick();
 await tick();
 assert.equal(backend.records.get(key),'{"page":7}');
 assert.equal(reader.getReadingStorageStatus().pending,0);
 assert.equal(backend.writes,1);
});
test('hydrate while offline keeps changes pending and never shows a false saved state',async()=>{
 const backend=harness();
 const reader=backend.mount();
 reader.saveReadingLocalState('barq-stories-v1','{"favorites":["story-1"]}');
 await tick();
 assert.equal(reader.getReadingStorageStatus().pending,1);
 assert.ok(reader.getReadingStorageStatus().error);
 backend.setOnline(true);
 assert.equal(await reader.retryReadingLocalState(),true);
 assert.equal(reader.getReadingStorageStatus().pending,0);
 assert.equal(backend.records.get('barq-stories-v1'),'{"favorites":["story-1"]}');
});
