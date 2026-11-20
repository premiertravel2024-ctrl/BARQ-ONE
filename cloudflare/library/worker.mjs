/*
 * BARQ ONE independent public reading gateway.
 * Never route remote visitors to the desktop FastAPI service.
 * Google users authenticate with OIDC. ONLY the verified owner consents to
 * drive.readonly. The encrypted refresh token never reaches the browser.
 */
import { page } from './library_page.mjs';

const GOOGLE_AUTH = 'https://accounts.google.com/o/oauth2/v2/auth';
const GOOGLE_TOKEN = 'https://oauth2.googleapis.com/token';
const GOOGLE_FILES = 'https://www.googleapis.com/drive/v3/files';
const SESSION_COOKIE = '__Host-barq_reader';
const STATE_COOKIE = '__Host-barq_oauth';
const MAX_PDF = 64 * 1024 * 1024;
const MAX_COVER = 8 * 1024 * 1024;
const GOOGLE_FOLDER = 'application/vnd.google-apps.folder';
const ID_PATTERN = /^[a-zA-Z0-9_-]{10,160}$/;
const headers = {
  'Cache-Control': 'no-store',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'Cross-Origin-Resource-Policy': 'same-origin'
};
const encoder = new TextEncoder();
const decoder = new TextDecoder();

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {status, headers:{...headers,'Content-Type':'application/json; charset=utf-8'}});
}
function problem(status, message) { return json({error:message}, status); }
function redirect(url){return new Response(null,{status:302,headers:{...headers,Location:url}});}
function bytes(value) { return encoder.encode(value); }
function b64(data) {
  const raw = typeof data === 'string' ? bytes(data) : data;
  let value = '';
  for (const byte of raw) value += String.fromCharCode(byte);
  return btoa(value).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}
function unb64(value) {
  if (!/^[A-Za-z0-9_-]+$/.test(value)) throw new Error('Bad encoding');
  const raw = atob(value.replace(/-/g,'+').replace(/_/g,'/'));
  return Uint8Array.from(raw, c=>c.charCodeAt(0));
}
function cookie(request, name) {
  const match = request.headers.get('Cookie')?.match(new RegExp('(?:^|;\\s*)' + name + '=([^;]*)'));
  return match?.[1] || '';
}
function setCookie(response, name, value, maxAge) {
  response.headers.append('Set-Cookie', name + '=' + value +
    '; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=' + maxAge);
  return response;
}
function requireConfig(env) {
  for (const field of ['BASE_URL','GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET','OWNER_GOOGLE_EMAIL','SESSION_SECRET','TOKEN_KEY_B64']) {
    if (!env[field]) throw new Error('Missing library configuration: ' + field);
  }
  if (!env.DB) throw new Error('Missing D1 binding');
  const base = new URL(env.BASE_URL);
  if (base.protocol !== 'https:' || base.pathname !== '/' || base.search || base.hash)
    throw new Error('BASE_URL must be an HTTPS origin ending in /');
  if (unb64(env.TOKEN_KEY_B64).length !== 32) throw new Error('TOKEN_KEY_B64 must decode to 32 bytes');
  return base.origin;
}
async function hmacKey(env) {
  return crypto.subtle.importKey('raw',bytes(env.SESSION_SECRET),{name:'HMAC',hash:'SHA-256'},false,['sign','verify']);
}
async function seal(data, env) {
  const value=b64(JSON.stringify(data));
  const signed=await crypto.subtle.sign('HMAC',await hmacKey(env),bytes(value));
  return value + '.' + b64(new Uint8Array(signed));
}
async function openSealed(value, env) {
  if (!value || value.length > 4096) return null;
  const parts=value.split('.');
  if (parts.length !== 2) return null;
  try {
    if (!await crypto.subtle.verify('HMAC',await hmacKey(env),unb64(parts[1]),bytes(parts[0]))) return null;
    const data=JSON.parse(decoder.decode(unb64(parts[0])));
    if (!data || !Number.isInteger(data.exp) || data.exp < Date.now()) return null;
    return data;
  } catch { return null; }
}
async function session(request, env) {
  const data=await openSealed(cookie(request,SESSION_COOKIE),env);
  return data && typeof data.sub==='string' && typeof data.email==='string' ? data : null;
}
function owner(user, env) {
  return !!user && user.email.toLowerCase()===env.OWNER_GOOGLE_EMAIL.toLowerCase().trim() &&
   (!env.OWNER_GOOGLE_SUB || user.sub===env.OWNER_GOOGLE_SUB);
}
function requireUser(user) {
  if (!user) throw Object.assign(new Error('Sign in with Google first'),{status:401});
}
function requireOwner(user, env) {
  requireUser(user);
  if (!owner(user,env)) throw Object.assign(new Error('Only the library owner may change this'),{status:403});
}
async function encrypt(token, env) {
  const nonce=crypto.getRandomValues(new Uint8Array(12));
  const key=await crypto.subtle.importKey('raw',unb64(env.TOKEN_KEY_B64),'AES-GCM',false,['encrypt']);
  const ciphertext=await crypto.subtle.encrypt({name:'AES-GCM',iv:nonce},key,bytes(token));
  return b64(nonce)+'.'+b64(new Uint8Array(ciphertext));
}
async function decrypt(encoded,env) {
  const parts=encoded.split('.');
  if(parts.length!==2)throw new Error('Invalid owner credential');
  const key=await crypto.subtle.importKey('raw',unb64(env.TOKEN_KEY_B64),'AES-GCM',false,['decrypt']);
  const plain=await crypto.subtle.decrypt({name:'AES-GCM',iv:unb64(parts[0])},key,unb64(parts[1]));
  return decoder.decode(plain);
}
async function refreshOwner(env) {
  const row=await env.DB.prepare('SELECT owner_sub,refresh_cipher FROM owner_drive WHERE singleton=1').first();
  if (!row) throw Object.assign(new Error('Owner must connect Google Drive'),{status:503});
  if(env.OWNER_GOOGLE_SUB && row.owner_sub!==env.OWNER_GOOGLE_SUB)
    throw Object.assign(new Error('Owner identity changed'),{status:403});
  const refresh=await decrypt(row.refresh_cipher,env);
  const response=await fetch(GOOGLE_TOKEN,{
    method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
    body:new URLSearchParams({client_id:env.GOOGLE_CLIENT_ID,client_secret:env.GOOGLE_CLIENT_SECRET,
      refresh_token:refresh,grant_type:'refresh_token'})
  });
  if (!response.ok) throw Object.assign(new Error('Owner Drive consent expired'),{status:503});
  const data=await response.json();
  if (!data.access_token) throw new Error('Missing Drive access token');
  return data.access_token;
}
async function googleFetch(path, token, params, range) {
  const url=new URL(GOOGLE_FILES+path);
  for(const [key,value] of Object.entries(params || {})) url.searchParams.set(key,String(value));
  const extra={Authorization:'Bearer '+token};
  if(range)extra.Range=range;
  const response=await fetch(url,{headers:extra});
  if (!response.ok) throw Object.assign(new Error('Cannot fetch approved Drive file'),{status:502});
  return response;
}
function newNonce() {
  return b64(crypto.getRandomValues(new Uint8Array(24)));
}
async function oauthStart(request,env,base,flow,user) {
  if(flow==='drive')requireOwner(user,env);
  const state=newNonce();
  const response=redirect(GOOGLE_AUTH+'?'+new URLSearchParams({
    client_id:env.GOOGLE_CLIENT_ID,
    redirect_uri:base+'/auth/callback',
    response_type:'code',
    access_type:flow==='drive'?'offline':'online',
    prompt:flow==='drive'?'consent':'select_account',
    scope:'openid email profile'+(flow==='drive'?' https://www.googleapis.com/auth/drive.readonly':''),
    state
  }).toString(),302);
  return setCookie(response,STATE_COOKIE,
    await seal({state,flow,sub:user?.sub||'',exp:Date.now()+600000},env),600);
}
async function oauthCallback(request,env,base,user) {
  const url=new URL(request.url);
  const saved=await openSealed(cookie(request,STATE_COOKIE),env);
  if(!saved || saved.state!==url.searchParams.get('state') || !url.searchParams.get('code'))
    return problem(400,'Google authorization expired or invalid');
  const response=await fetch(GOOGLE_TOKEN,{
    method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
    body:new URLSearchParams({client_id:env.GOOGLE_CLIENT_ID,client_secret:env.GOOGLE_CLIENT_SECRET,
      code:url.searchParams.get('code'),grant_type:'authorization_code',redirect_uri:base+'/auth/callback'})
  });
  if (!response.ok) return problem(401,'Google sign-in failed');
  const token=await response.json();
  const profileResponse=await fetch('https://openidconnect.googleapis.com/v1/userinfo',{
    headers:{Authorization:'Bearer '+token.access_token}
  });
  if (!profileResponse.ok) return problem(401,'Google identity validation failed');
  const profile=await profileResponse.json();
  if(!profile.sub || !profile.email || profile.email_verified!==true)
    return problem(403,'A verified Google email is required');
  if(saved.flow==='drive') {
    requireOwner(user,env);
    if(saved.sub!==user.sub || profile.sub!==user.sub || !owner(profile,env) ||
       !token.scope?.split(' ').includes('https://www.googleapis.com/auth/drive.readonly') ||
       !token.refresh_token)
      return problem(403,'Owner Drive authorization is incomplete');
    const encrypted=await encrypt(token.refresh_token,env);
    await env.DB.prepare('INSERT INTO owner_drive (singleton,owner_sub,refresh_cipher) VALUES (1,?,?) '+
      'ON CONFLICT(singleton) DO UPDATE SET owner_sub=excluded.owner_sub,refresh_cipher=excluded.refresh_cipher,updated_at=CURRENT_TIMESTAMP')
      .bind(user.sub,encrypted).run();
  }
  const next=redirect(base+'/',302);
  setCookie(next,STATE_COOKIE,'',0);
  if(saved.flow!=='drive')setCookie(next,SESSION_COOKIE,
    await seal({sub:profile.sub,email:profile.email,exp:Date.now()+7*86400000},env),7*86400);
  return next;
}
async function currentBooks(env,user,all) {
  const full=all&&owner(user,env);
  const clause=full?'':'WHERE b.active=1 AND b.published=1';
  const rows=await env.DB.prepare('SELECT b.id,b.title,b.folder_name,b.cover_id,b.size_bytes,b.series_id,b.issue_number,b.position,b.published,b.active '+
    'FROM books b '+clause+' ORDER BY b.position,b.issue_number,b.title').all();
  const series=await env.DB.prepare('SELECT id,title,description,position FROM series ORDER BY position,title').all();
  const seriesUsed=new Set(rows.results.map(row=>row.series_id));
  return {books:rows.results,series:series.results.filter(item=>full||seriesUsed.has(item.id))};
}
async function media(request,env,user,id,cover) {
  requireUser(user);
  if (!ID_PATTERN.test(id))return problem(404,'Book not found');
  const row=await env.DB.prepare('SELECT * FROM books WHERE id=?').bind(id).first();
  if(!row || !row.active || (!row.published&&!owner(user,env)))return problem(404,'Book not found');
  const fileId=cover?row.cover_id:row.id;
  if (!fileId||!ID_PATTERN.test(fileId))return problem(404,'Cover not found');
  const token=await refreshOwner(env);
  const meta=await googleFetch('/'+encodeURIComponent(fileId),token,{fields:'mimeType,size,trashed'});
  const data=await meta.json();
  const size=Number(data.size);
  const expected=cover?['image/jpeg','image/png','image/webp']:['application/pdf'];
  if(data.trashed||!expected.includes(data.mimeType)||!Number.isInteger(size)||
     size<1||size>(cover?MAX_COVER:MAX_PDF))return problem(422,'File is not an approved readable format');
  const range=request.headers.get('Range');
  if(range&&!/^bytes=\d{1,8}-\d{0,8}$/.test(range))return problem(416,'Invalid byte range');
  const stream=await googleFetch('/'+encodeURIComponent(fileId),token,{alt:'media'},range);
  if(stream.status!==200&&stream.status!==206)return problem(502,'Unexpected Drive response');
  const h=new Headers({...headers,'Content-Type':data.mimeType,
    'Content-Disposition':(new URL(request.url).searchParams.get('download')==='1'?'attachment':'inline')+'; filename="barq-book"'}); 
  for(const name of ['Content-Length','Content-Range','Accept-Ranges']){
    if(stream.headers.has(name))h.set(name,stream.headers.get(name));
  }
  return new Response(stream.body,{status:stream.status,headers:h});
}
async function bodyJson(request) {
  const length=Number(request.headers.get('Content-Length')||'0');
  if(length>16384)throw Object.assign(new Error('Request too large'),{status:413});
  const text=await request.text();
  if(text.length>16384)throw Object.assign(new Error('Request too large'),{status:413});
  try {return JSON.parse(text);} catch {throw Object.assign(new Error('Invalid JSON'),{status:422});}
}
async function syncCatalogue(env) {
  const state=await env.DB.prepare('SELECT root_folder FROM owner_drive WHERE singleton=1').first();
  if(!state?.root_folder)throw Object.assign(new Error('Choose a Drive folder first'),{status:409});
  const token=await refreshOwner(env);
  const queue=[[state.root_folder,'']];
  const seen=new Set();
  const books=[];
  while(queue.length) {
    const [folder,group]=queue.shift();
    if(seen.has(folder))continue;
    seen.add(folder);
    if(seen.size>250||books.length>4000)throw Object.assign(new Error('Folder exceeds limits'),{status:413});
    let next='';
    const entries=[];
    do {
      const q="'"+folder+"' in parents and trashed = false";
      const data=await googleFetch('',token,{q,fields:'nextPageToken,files(id,name,mimeType,size)',pageSize:'500',pageToken:next||''});
      const parsed=await data.json();
      entries.push(...(parsed.files||[]));
      next=parsed.nextPageToken||'';
    }while(next);
    const images=new Map(entries.filter(f=>['image/jpeg','image/png','image/webp'].includes(f.mimeType)&&
      Number(f.size)>0&&Number(f.size)<=MAX_COVER).map(f=>[f.name.toLowerCase(),f]));
    const pdfs=entries.filter(f=>f.mimeType==='application/pdf'&&Number(f.size)>0&&Number(f.size)<=MAX_PDF&&ID_PATTERN.test(f.id));
    for(const folderItem of entries)if(folderItem.mimeType===GOOGLE_FOLDER&&ID_PATTERN.test(folderItem.id))
      queue.push([folderItem.id,[group,folderItem.name].filter(Boolean).join(' / ').slice(0,300)]);
    for(const file of pdfs) {
      const title=file.name.replace(/\.pdf$/i,'').slice(0,250);
      const options=[title+'.jpg',title+'.jpeg',title+'.png',title+'.webp'];
      if(pdfs.length===1)options.push('cover.jpg','cover.jpeg','cover.png','cover.webp');
      const cover=options.map(x=>images.get(x.toLowerCase())).find(Boolean);
      books.push({id:file.id,title,folder:group,cover:cover?.id||null,size:Number(file.size)});
    }
  }
  const statements=[env.DB.prepare('UPDATE books SET active=0')];
  for(const item of books)statements.push(env.DB.prepare(
    'INSERT INTO books(id,title,original_title,folder_name,cover_id,size_bytes,active) VALUES(?,?,?,?,?,?,1) '+
    'ON CONFLICT(id) DO UPDATE SET original_title=excluded.original_title,folder_name=excluded.folder_name, '+
    'cover_id=excluded.cover_id,size_bytes=excluded.size_bytes,active=1,updated_at=CURRENT_TIMESTAMP'
  ).bind(item.id,item.title,item.title,item.folder,item.cover,item.size));
  await env.DB.batch(statements);
  return {scanned:books.length,folders:seen.size,unpublished_default:true};
}
async function admin(request,env,user,path) {
  requireOwner(user,env);
  if(request.method==='GET'&&path==='/api/admin/status'){
    const row=await env.DB.prepare('SELECT root_folder FROM owner_drive WHERE singleton=1').first();
    return json({connected:!!row,folder:row?.root_folder||''});
  }
  if(request.method!=='POST')return problem(405,'Method not allowed');
  const data=await bodyJson(request);
  if(path==='/api/admin/folder'){
    const id=String(data.folder||'').trim().split('?')[0].split('/').pop();
    if(!ID_PATTERN.test(id))return problem(422,'Invalid Drive folder');
    const token=await refreshOwner(env);
    const response=await googleFetch('/'+encodeURIComponent(id),token,{fields:'id,mimeType,trashed'});
    const details=await response.json();
    if(details.trashed||details.mimeType!==GOOGLE_FOLDER)return problem(422,'Not a readable folder');
    await env.DB.prepare('UPDATE owner_drive SET root_folder=?,updated_at=CURRENT_TIMESTAMP WHERE singleton=1').bind(id).run();
    return json({folder:id});
  }
  if(path==='/api/admin/sync')return json(await syncCatalogue(env));
  if(path==='/api/admin/series'){
    const title=String(data.title||'').trim().slice(0,120);
    if(!title)return problem(422,'Series name required');
    const id=crypto.randomUUID();
    await env.DB.prepare('INSERT INTO series(id,title,description) VALUES(?,?,?)').bind(id,title,String(data.description||'').slice(0,500)).run();
    return json({id,title});
  }
  if(path==='/api/admin/book'){
    const id=String(data.id||'');
    if(!ID_PATTERN.test(id))return problem(422,'Invalid book');
    const current=await env.DB.prepare('SELECT id FROM books WHERE id=? AND active=1').bind(id).first();
    if(!current)return problem(404,'Book not found');
    const published=typeof data.published==='boolean'?Number(data.published):null;
    const seriesId=data.series_id===null||data.series_id===''?null:data.series_id;
    if(seriesId!==undefined&&seriesId!==null){
      if(typeof seriesId!=='string'||seriesId.length>60)return problem(422,'Invalid series');
      const found=await env.DB.prepare('SELECT id FROM series WHERE id=?').bind(seriesId).first();
      if(!found)return problem(422,'Unknown series');
    }
    const title=data.title===undefined?null:String(data.title).trim().slice(0,250);
    if(title!==null&&!title)return problem(422,'Empty book title');
    const order=data.position===undefined?null:data.position;
    const issue=data.issue_number===undefined?null:data.issue_number;
    if(order!==null&&(!Number.isInteger(order)||order<0||order>100000))return problem(422,'Invalid position');
    if(issue!==null&&(!Number.isInteger(issue)||issue<1||issue>100000))return problem(422,'Invalid issue number');
    await env.DB.prepare('UPDATE books SET title=COALESCE(?,title),published=COALESCE(?,published), '+
      'series_id=CASE WHEN ? THEN ? ELSE series_id END,position=COALESCE(?,position), '+
      'issue_number=CASE WHEN ? THEN ? ELSE issue_number END,updated_at=CURRENT_TIMESTAMP WHERE id=?')
      .bind(title,published,seriesId!==undefined?1:0,seriesId,order,data.issue_number!==undefined?1:0,issue,id).run();
    return json({updated:true});
  }
  return problem(404,'Unknown admin route');
}
async function progress(request,env,user){
  requireUser(user);
  if(request.method==='GET') {
    const rows=await env.DB.prepare('SELECT book_id,page,favourite FROM reader_progress WHERE reader_sub=?').bind(user.sub).all();
    return json({progress:rows.results});
  }
  if(request.method!=='POST')return problem(405,'Method not allowed');
  const data=await bodyJson(request);
  if(!ID_PATTERN.test(data.book_id||'')||!Number.isInteger(data.page)||data.page<1||data.page>100000||
     typeof data.favourite!=='boolean')return problem(422,'Invalid progress');
  const book=await env.DB.prepare('SELECT id FROM books WHERE id=? AND active=1 AND published=1').bind(data.book_id).first();
  if(!book)return problem(404,'Book not found');
  await env.DB.prepare('INSERT INTO reader_progress(reader_sub,book_id,page,favourite) VALUES(?,?,?,?) '+
    'ON CONFLICT(reader_sub,book_id) DO UPDATE SET page=excluded.page,favourite=excluded.favourite,updated_at=CURRENT_TIMESTAMP')
    .bind(user.sub,data.book_id,data.page,Number(data.favourite)).run();
  return json({saved:true});
}
export default {
  async fetch(request,env) {
    try {
      const base=requireConfig(env);
      const url=new URL(request.url);
      if(url.origin!==base)return problem(403,'Invalid host');
      const path=url.pathname;
      const user=await session(request,env);
      if(request.method==='POST'&&request.headers.get('Origin')!==base)return problem(403,'Invalid request origin');
      if(path==='/auth/login'&&request.method==='GET')return oauthStart(request,env,base,'login',user);
      if(path==='/auth/drive'&&request.method==='GET')return oauthStart(request,env,base,'drive',user);
      if(path==='/auth/callback'&&request.method==='GET')return oauthCallback(request,env,base,user);
      if(path==='/auth/logout'&&request.method==='GET'){
        const response=redirect(base+'/',302);
        return setCookie(response,SESSION_COOKIE,'',0);
      }
      if(path==='/healthz')return json({status:'ok'});
      if(path==='/api/me')return json({authenticated:!!user,owner:owner(user,env),email:user?.email||null});
      if(path==='/api/catalogue') {
        requireUser(user);
        return json(await currentBooks(env,user,url.searchParams.get('all')==='1'));
      }
      if(path==='/api/progress')return progress(request,env,user);
      if(path.startsWith('/api/admin/'))return admin(request,env,user,path);
      let match=path.match(/^\/api\/books\/([a-zA-Z0-9_-]{10,160})\/(file|cover)$/);
      if(match&&request.method==='GET')return media(request,env,user,match[1],match[2]==='cover');
      if(path==='/'&&request.method==='GET')return new Response(page,{headers:{...headers,
        'Content-Type':'text/html; charset=utf-8',
        'Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'" }});
      if(path==='/ui.js'&&request.method==='GET')return new Response((await import('./library_ui.mjs')).default,{headers:{...headers,'Content-Type':'text/javascript; charset=utf-8'}});
      if(path==='/ui.css'&&request.method==='GET')return new Response((await import('./library_style.mjs')).default,{headers:{...headers,'Content-Type':'text/css; charset=utf-8'}});
      return problem(404,'Not found');
    }catch(err) {
      const status=Number.isInteger(err?.status)?err.status:500;
      if(status>=500)console.error('BARQ reader:',err?.message||'unknown error');
      return problem(status,status===500?'Library service is unavailable':err.message);
    }
  }
};
