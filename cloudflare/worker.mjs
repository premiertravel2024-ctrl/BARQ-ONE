// BARQ ONE - Cloudflare Workers room signaling. No media is uploaded here.
// HTTPS on Workers, WebSockets + hibernatable SQLite Durable Objects on the Free tier.
import roomPage from "./room.html";

const TTL_MS = 2 * 60 * 60 * 1000;
const RE_ROOM = /^[A-Za-z0-9_-]{16}$/;
const MIME_JSON = {"content-type":"application/json; charset=utf-8","cache-control":"no-store","referrer-policy":"no-referrer"};
const PAGE_HEADERS = {"content-type":"text/html; charset=utf-8","cache-control":"no-store","referrer-policy":"no-referrer",
  "x-content-type-options":"nosniff","content-security-policy":"default-src 'self'; img-src 'self' data: blob:; media-src blob: https:; frame-src https://open.spotify.com https://play.anghami.com; connect-src 'self' ws: wss:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; frame-ancestors 'self' http://127.0.0.1:*"};
function reply(data,status=200){return new Response(JSON.stringify(data),{status,headers:MIME_JSON});}
function randomToken(bytes=32){return btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(bytes)))).replaceAll("+","-").replaceAll("/","_").replace(/=+$/,"");}
async function digest(v){const raw=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(v));return Array.from(new Uint8Array(raw)).map(x=>x.toString(16).padStart(2,"0")).join("");}
const roomStub=(env,id)=>env.ROOMS.get(env.ROOMS.idFromName(id));
function safeRoom(path){const parts=path.split("/").filter(Boolean);const id=parts.at(-1);return RE_ROOM.test(id||"")?id:null;}
const wsUpgrade=(request)=>request.headers.get("Upgrade")?.toLowerCase()==="websocket";
export default {
  async fetch(request,env){
    const url=new URL(request.url),p=url.pathname;
    if(request.method==="GET"&&(p==="/"||p==="/health"))return reply({status:"ok",service:"BARQ ONE Rooms",type:"signaling",media:"peer-to-peer",turn_configured:false});
    if(p==="/api/rooms"&&request.method==="POST"){
      // A free public API is rate-limited per connecting IP; no shared secret is put inside the installer.
      const ip=request.headers.get("CF-Connecting-IP")||"unknown";
      const limiter=env.RATE_LIMIT.get(env.RATE_LIMIT.idFromName(ip));
      const allowed=await limiter.fetch("https://limit.local/check",{method:"POST"});
      if(allowed.status!==200)return reply({error:"Room limit reached; retry later"},429);
      let payload;
      try{payload=await request.json();}catch{return reply({error:"Invalid JSON"},400);}
      const mode=payload?.mode;
      if(mode!=="video"&&mode!=="music")return reply({error:"Unknown room mode"},400);
      const room_id=randomToken(12),host_token=randomToken(),guest_token=randomToken();
      const code=String(100000+crypto.getRandomValues(new Uint32Array(1))[0]%900000);
      const init=await roomStub(env,room_id).fetch("https://room.local/create",{
        method:"POST",body:JSON.stringify({id:room_id,mode,code,hostHash:await digest(host_token),guestHash:await digest(guest_token),created:Date.now()})
      });
      if(!init.ok)return reply({error:"Unable to create room"},503);
      return reply({room_id,host_token,guest_token,code},201);
    }
    if(p.startsWith("/api/rooms/")&&request.method==="DELETE"){
      const id=safeRoom(p);if(!id)return reply({error:"Invalid room"},404);
      const token=(request.headers.get("Authorization")||"").replace(/^Bearer /,"");
      if(!token)return reply({error:"Host token required"},401);
      return roomStub(env,id).fetch("https://room.local/delete",{method:"DELETE",headers:{"x-token":token}});
    }
    if(p.startsWith("/r/")&&request.method==="GET"){
      const id=safeRoom(p);
      if(!id||url.searchParams.get("role")!=="guest")return reply({error:"Guest-only room page"},404);
      const token=url.searchParams.get("token")||"";
      const auth=await roomStub(env,id).fetch("https://room.local/check",{headers:{"x-token":token,"x-role":"guest"}});
      if(!auth.ok)return reply({error:"Room unavailable or invalid invite"},auth.status===403?403:404);
      return new Response(roomPage,{headers:PAGE_HEADERS});
    }
    if(p.startsWith("/signal/")&&request.method==="GET"){
      const id=safeRoom(p);if(!id)return reply({error:"Room not found"},404);
      if(!wsUpgrade(request))return reply({error:"WebSocket required"},426);
      return roomStub(env,id).fetch(new Request("https://room.local/ws"+url.search,{headers:request.headers}));
    }
    return reply({error:"Not found",hint:"Use /health or create a BARQ invitation."},404);
  }
};
export class RateLimit {
  constructor(ctx){this.ctx=ctx;}
  async fetch(req){
    if(req.method!=="POST")return reply({error:"Method"},405);
    const bucket=Math.floor(Date.now()/3600000);
    const row=await this.ctx.storage.get("rate");
    const count=row?.bucket===bucket?row.count:0;
    if(count>=8)return reply({error:"Too many new rooms this hour"},429);
    await this.ctx.storage.put("rate",{bucket,count:count+1});
    await this.ctx.storage.setAlarm((bucket+2)*3600000);
    return reply({allowed:true});
  }
  async alarm(){await this.ctx.storage.deleteAll();}
}
export class RoomSession {
  constructor(ctx){this.ctx=ctx;}
  async fetch(request){
    const url=new URL(request.url),p=url.pathname;
    if(p==="/create"&&request.method==="POST"){
      if(await this.ctx.storage.get("room"))return reply({error:"Already exists"},409);
      const room=await request.json();
      if(!RE_ROOM.test(room.id)||!["video","music"].includes(room.mode)||!room.hostHash||!room.guestHash)return reply({error:"Invalid room"},400);
      await this.ctx.storage.put("room",room);
      await this.ctx.storage.setAlarm(room.created+TTL_MS);
      return reply({created:true},201);
    }
    const room=await this.ctx.storage.get("room");
    if(!room||Date.now()-room.created>TTL_MS)return reply({error:"Room expired"},404);
    if(p==="/check"){
      const role=request.headers.get("x-role")||"";
      const token=request.headers.get("x-token")||"";
      const expected=role==="guest"?room.guestHash:role==="host"?room.hostHash:null;
      if(!expected||await digest(token)!==expected)return reply({error:"Invalid invitation"},403);
      return reply({mode:room.mode});
    }
    if(p==="/delete"&&request.method==="DELETE"){
      if(await digest(request.headers.get("x-token")||"")!==room.hostHash)return reply({error:"Host token required"},403);
      for(const socket of this.ctx.getWebSockets())try{socket.close(1000,"Room closed");}catch{}
      await this.ctx.storage.deleteAll();return reply({closed:true});
    }
    if(p==="/ws"){
      const role=url.searchParams.get("role"),token=url.searchParams.get("token")||"",code=url.searchParams.get("code")||"";
      if(role!=="guest"&&role!=="host")return reply({error:"Unknown role"},403);
      if(await digest(token)!==(role==="host"?room.hostHash:room.guestHash)||(role==="guest"&&code!==room.code))
        return reply({error:"Invalid room credentials"},403);
      const live=this.ctx.getWebSockets().filter(s=>this.ctx.getTags(s).includes(role));
      if(live.length)return reply({error:"That seat is occupied"},409);
      const pair=new WebSocketPair(),client=pair[0],server=pair[1];
      this.ctx.acceptWebSocket(server,[role]);
      const track=await this.ctx.storage.get("track");
      server.send(JSON.stringify({type:"ready",mode:room.mode,ice_servers:[{urls:"stun:stun.l.google.com:19302"}],track:track||null}));
      for(const other of this.ctx.getWebSockets()){
        if(other!==server)try{
          other.send(JSON.stringify({type:"peer-joined",connection:"internet"}));
          server.send(JSON.stringify({type:"peer-joined",connection:"internet"}));
        }catch{}
      }
      return new Response(null,{status:101,webSocket:client});
    }
    return reply({error:"Unknown action"},404);
  }
  async webSocketMessage(socket,message){
    if(typeof message!=="string"||message.length>65536){socket.close(1009,"Message too large");return;}
    let data;try{data=JSON.parse(message);}catch{return;}
    const role=this.ctx.getTags(socket)[0]||"",type=data?.type;
    const allowed=["offer","answer","ice","chat","typing","reaction","track","sync","subtitle","request-pause","request-seek"];
    if(!allowed.includes(type))return;
    if(["offer","sync","track","subtitle"].includes(type)&&role!=="host")return;
    if(type==="answer"&&role!=="guest")return;
    if(type==="track"){
      if(data.value!==null&&(!data.value||typeof data.value!=="object"||!["spotify","anghami"].includes(data.value.provider)))return;
      await this.ctx.storage.put("track",data.value);
    }
    let output;
    if(type==="chat")output={type,role,text:String(data.value||"").slice(0,500)};
    else if(type==="reaction"||type==="typing")output={type,text:String(data.value||"").slice(0,40)};
    else if(type==="subtitle")output={type,value:String(data.value||"").slice(0,400)};
    else output={type,value:data.value};
    const payload=JSON.stringify(output);
    if(payload.length>65536)return;
    for(const other of this.ctx.getWebSockets())if(other!==socket)try{other.send(payload);}catch{}
  }
  async webSocketClose(socket){
    const role=this.ctx.getTags(socket)[0]||"";
    for(const other of this.ctx.getWebSockets())if(other!==socket)try{other.send(JSON.stringify({type:"peer-left",role}));}catch{}
  }
  async webSocketError(socket){await this.webSocketClose(socket);}
  async alarm(){
    for(const socket of this.ctx.getWebSockets())try{socket.close(1000,"Room expired");}catch{}
    await this.ctx.storage.deleteAll();
  }
}