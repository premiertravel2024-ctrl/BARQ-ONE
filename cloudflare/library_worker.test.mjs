import test from 'node:test';
import assert from 'node:assert/strict';
import library from './library/worker.mjs';

const env={
 BASE_URL:'https://library.example.com',
 GOOGLE_CLIENT_ID:'test.apps.googleusercontent.com',
 GOOGLE_CLIENT_SECRET:'unit-test-secret',
 OWNER_GOOGLE_EMAIL:'owner@example.com',
 SESSION_SECRET:'long-secret-for-unit-tests',
 TOKEN_KEY_B64:Buffer.alloc(32,17).toString('base64url'),
 DB:{prepare(){throw new Error('Anonymous user must not reach the database')}}
};
const make=(path,options)=>new Request(env.BASE_URL+path,options);

test('The gateway is available without forwarding BARQ desktop endpoints',async()=>{
 const health=await library.fetch(make('/healthz'),env);
 assert.equal(health.status,200);
 assert.equal((await health.json()).status,'ok');
 assert.equal((await library.fetch(make('/v1/chat/completions'),env)).status,404);
});
test('Anonymous and forged Google sessions cannot browse Drive catalogue',async()=>{
 const paths=['/api/catalogue','/api/catalogue?all=1','/api/progress',
  '/api/books/1234567890abcdef/file','/api/books/1234567890abcdef/cover','/api/admin/status'];
 for(const path of paths) {
  const response=await library.fetch(make(path),env);
  assert.equal(response.status,401,path);
 }
 const forged=await library.fetch(make('/api/catalogue',{headers:{Cookie:'__Host-barq_reader=owner'}}),env);
 assert.equal(forged.status,401);
});
test('Owner Google Drive consent cannot start anonymously',async()=>{
 const response=await library.fetch(make('/auth/drive'),env);
 assert.equal(response.status,401);
});
test('Mutations require an exact same-origin request',async()=>{
 const response=await library.fetch(make('/api/admin/sync',{
  method:'POST',headers:{Origin:'https://attacker.example','Content-Type':'application/json'},body:'{}'
 }),env);
 assert.equal(response.status,403);
});
test('Home page has anti-framing policy and no Drive credentials',async()=>{
 const response=await library.fetch(make('/'),env);
 assert.equal(response.status,200);
 assert.match(response.headers.get('content-security-policy'),/frame-ancestors 'none'/);
 const page=await response.text();
 assert.match(page,/BARQ ONE/);
 assert.doesNotMatch(page,/unit-test-secret|refresh_token|owner_drive/);
});
test('Browser assets only come from the dedicated gateway',async()=>{
 for(const path of ['/ui.js','/ui.css']) {
  const response=await library.fetch(make(path),env);
  assert.equal(response.status,200,path);
  assert.ok((await response.text()).length>100);
 }
});
