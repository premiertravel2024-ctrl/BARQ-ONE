// Node.js tests run without a live Cloudflare account or touching real media.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source = await readFile(new URL('./worker.mjs',import.meta.url),'utf8');
const transformed = source.replace('import roomPage from "./room.html";','const roomPage = "<html>BARQ ROOM TEST</html>";');
const moduleUrl = 'data:text/javascript;base64,' + Buffer.from(transformed).toString('base64');
const {default:worker,RoomSession,RateLimit} = await import(moduleUrl);

function namespace(Clazz){
  const instances = new Map();
  return {
    idFromName(name){return name;},
    get(id){
      if(!instances.has(id)){
        const data = new Map();
        const context = {sockets:[],
          storage:{
            async get(key){return data.get(key);},
            async put(key,value){data.set(key,value);},
            async setAlarm(_timestamp){},
            async deleteAll(){data.clear();}
          },
          getWebSockets(){return context.sockets;},
          getTags(socket){return [socket.role];},
          acceptWebSocket(){},
        };
        const actor = new Clazz(context);
        instances.set(id,{actor,context,fetch(request,init){return actor.fetch(typeof request==="string"?new Request(request,init):request);}});
      }
      return instances.get(id);
    }
  };
}
function env(){return {ROOMS:namespace(RoomSession),RATE_LIMIT:namespace(RateLimit)};}
test('health actually probes room storage, not only the worker process',async()=>{
  const e=env();
  const ok=await worker.fetch(new Request('https://barq.example/health/rooms'),e);
  assert.equal(ok.status,200);
  assert.equal((await ok.json()).rooms_ready,true);
  const broken=await worker.fetch(new Request('https://barq.example/health/rooms'),{});
  assert.equal(broken.status,503);
  assert.equal((await broken.json()).code,'BINDING_MISSING');
});
test('create browser room, verify guest token, close room',async()=>{
  const e=env();
  const res=await worker.fetch(new Request('https://barq.example/api/rooms',{
    method:'POST',headers:{'Content-Type':'application/json','CF-Connecting-IP':'192.0.2.1'},body:JSON.stringify({mode:'music'})
  }),e);
  assert.equal(res.status,201);
  const room=await res.json();
  assert.match(room.room_id,/^[A-Za-z0-9_-]{16}$/);
  assert.match(room.host_token,/^[A-Za-z0-9_-]{43}$/);
  assert.match(room.guest_token,/^[A-Za-z0-9_-]{43}$/);
  const page=new URL('/r/'+room.room_id,'https://barq.example');
  page.searchParams.set('role','guest');page.searchParams.set('token',room.guest_token);
  const guest=await worker.fetch(new Request(page),e);
  assert.equal(guest.status,200);
  assert.match(await guest.text(),/BARQ ROOM TEST/);
  page.searchParams.set('token','wrong');
  const denied=await worker.fetch(new Request(page),e);
  assert.equal(denied.status,403);
  const end=await worker.fetch(new Request('https://barq.example/api/rooms/'+room.room_id,{
    method:'DELETE',headers:{Authorization:'Bearer '+room.host_token}
  }),e);
  assert.equal(end.status,200);
  assert.equal((await end.json()).closed,true);
});
test('limit errors distinguish actual rate limits from broken storage',async()=>{
  const e=env(),ip='192.0.2.2';
  async function create(){return worker.fetch(new Request('https://barq.example/api/rooms',{
    method:'POST',headers:{'Content-Type':'application/json','CF-Connecting-IP':ip},body:'{"mode":"video"}'
  }),e);}
  for(let i=0;i<24;i++) assert.equal((await create()).status,201);
  const max=await create();assert.equal(max.status,429);
  assert.equal((await max.json()).code,'ROOM_RATE_LIMIT');
  const noBindings=await worker.fetch(new Request('https://barq.example/api/rooms',{
    method:'POST',headers:{'Content-Type':'application/json'},body:'{"mode":"video"}'
  }),{});
  assert.equal(noBindings.status,503);
  assert.equal((await noBindings.json()).code,'BINDING_MISSING');
});

test('guest chat and legacy value both reach host with text',async()=>{
 const e=env();
 const created=await worker.fetch(new Request('https://barq.example/api/rooms',{
  method:'POST',headers:{'Content-Type':'application/json','CF-Connecting-IP':'192.0.2.41'},
  body:JSON.stringify({mode:'music'})
 }),e);
 assert.equal(created.status,201);
 const id=(await created.json()).room_id;
 const session=e.ROOMS.get(id);
 const received=[];
 const host={role:'host',send(text){received.push(JSON.parse(text))}};
 const guest={role:'guest',send(){}};
 session.context.sockets.push(host,guest);
 await session.actor.webSocketMessage(guest,JSON.stringify({type:'chat',text:'أهلًا يا مضيف'}));
 await session.actor.webSocketMessage(guest,JSON.stringify({type:'chat',value:'رسالة قديمة'}));
 await session.actor.webSocketMessage(guest,JSON.stringify({type:'reaction',text:'👏'}));
 assert.deepEqual(received,[
  {type:'chat',role:'guest',text:'أهلًا يا مضيف'},
  {type:'chat',role:'guest',text:'رسالة قديمة'},
  {type:'reaction',text:'👏'},
 ]);
});
