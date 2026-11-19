const {chromium}=require('playwright');require('fs').mkdirSync('test-results',{recursive:true});const assert=require('assert/strict');
(async()=>{const browser=await chromium.launch({...(process.env.BARQ_TEST_CHROMIUM?{executablePath:process.env.BARQ_TEST_CHROMIUM}:{}),headless:true,args:['--no-sandbox']});const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>{errors.push(e.message);console.error(e.message)});
const fs=require('node:fs');
const roomHtml=fs.readFileSync(require('node:path').resolve(__dirname,'../../cloudflare/room.html'),'utf8');
let musicRoom=null;
let appContextState;
function smallPdf(){
 const rows=['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Count 2 /Kids [3 0 R 4 0 R] >>',
  '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 240 300] /Contents 5 0 R >>',
  '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 240 300] /Rotate 90 /Contents 5 0 R >>','<< /Length 0 >>\nstream\nendstream'];
 let body='%PDF-1.4\n';const offsets=[0];
 for(const [index,row] of rows.entries()){offsets.push(body.length);body+=(index+1)+' 0 obj\n'+row+'\nendobj\n';}
 const xref=body.length;
 return Buffer.from(body+'xref\n0 '+offsets.length+'\n0000000000 65535 f \n'+
  offsets.slice(1).map(offset=>String(offset).padStart(10,'0')+' 00000 n \n').join('')+
  'trailer\n<< /Size '+offsets.length+' /Root 1 0 R >>\nstartxref\n'+xref+'\n%%EOF\n');
}
const title={id:1,kind:'movie',title:'QA catalogue title',date:'2026-01-01',rating:8,overview:'Catalogue fixture for automated UI checks only.',poster:null,backdrop:null,genres:[18]};
const pcm=Buffer.alloc(44+8000*2*20);pcm.write('RIFF');pcm.writeUInt32LE(pcm.length-8,4);pcm.write('WAVEfmt ',8);pcm.writeUInt32LE(16,16);pcm.writeUInt16LE(1,20);pcm.writeUInt16LE(1,22);pcm.writeUInt32LE(8000,24);pcm.writeUInt32LE(16000,28);pcm.writeUInt16LE(2,32);pcm.writeUInt16LE(16,34);pcm.write('data',36);pcm.writeUInt32LE(pcm.length-44,40);
await page.route('**/v1/**',route=>{if(route.request().url().includes('/v1/music/stream/')){
 const range=route.request().headers()['range'];
 const headers={'Content-Type':'audio/wav','Accept-Ranges':'bytes','Cache-Control':'no-store'};
 if(range){
  const match=/^bytes=(\d+)-(\d*)$/.exec(range);
  if(!match)return route.fulfill({status:416,headers:{...headers,'Content-Range':'bytes */'+pcm.length},body:''});
  const start=Number(match[1]),end=match[2]?Math.min(Number(match[2]),pcm.length-1):pcm.length-1;
  if(start>=pcm.length||start>end)return route.fulfill({status:416,headers:{...headers,'Content-Range':'bytes */'+pcm.length},body:''});
  return route.fulfill({status:206,headers:{...headers,'Content-Range':'bytes '+start+'-'+end+'/'+pcm.length,'Content-Length':String(end-start+1)},body:pcm.subarray(start,end+1)});
 }
 return route.fulfill({status:200,headers:{...headers,'Content-Length':String(pcm.length)},body:pcm});
}const u=new URL(route.request().url());
if(u.pathname==='/v1/reading/drive/status')return route.fulfill({json:{connected:false}});
if(u.pathname==='/v1/reading/books/egy-zenab')return route.fulfill({contentType:'application/pdf',body:smallPdf()});
let data;if(u.pathname==='/v1/cinema/status')data={configured:true};if(u.pathname==='/v1/cinema/genres')data={genres:[{id:18,name:'Drama'}]};if(u.pathname==='/v1/cinema/browse')data={results:[title],page:Number(u.searchParams.get('page')||1),total_pages:2,total_results:40};if(u.pathname.startsWith('/v1/cinema/details/'))data={...title,genre_names:['Drama'],cast:[],related:[],runtime:120};if(u.pathname==='/v1/music/discover')data={source:'index',items:[{kind:'song',id:'102704',title:'تملى معاك'}]};if(u.pathname==='/v1/music/library')data={tracks:[{id:'a'.repeat(24),title:'QA local track',artist:'Tagged artist',album:'Tagged album',duration:20,artwork:false}]};if(u.pathname==='/v1/watchrooms/active')data={room:musicRoom};
if(u.pathname==='/v1/app-context/state'&&route.request().method()==='PUT')appContextState=route.request().postDataJSON();
if(u.pathname==='/v1/app-context/command'&&u.searchParams.get('text')==='افتح أنغامي')data={action:{section:'music',mode:'anghami'}};
if(u.pathname==='/v1/router/providers')data={providers:[]};
if(u.pathname==='/v1/router/models'||u.pathname==='/v1/models')data={models:[]};
if(u.pathname==='/v1/conversations')data={conversations:[]};
if(u.pathname==='/v1/personal/notifications')data={items:[]};
route.fulfill(data===undefined?{status:503,json:{detail:"Fixture unavailable"}}:{json:data});});
await page.goto('http://127.0.0.1:5173/tests/rebuild/index.html');await page.getByRole('heading',{name:'الرائج دلوقتي'}).waitFor();await page.getByRole('button',{name:'QA catalogue title',exact:true}).first().click();await page.getByRole('dialog').waitFor();await page.keyboard.press('Escape');await page.getByRole('dialog').waitFor({state:'detached'});assert.equal(await page.getByRole('dialog').count(),0);await page.getByRole('button',{name:'المفضلة',exact:true}).nth(1).click();await page.getByRole('button',{name:'المفضلة',exact:true}).first().click();await page.getByRole('button',{name:'QA catalogue title',exact:true}).waitFor();await page.reload();await page.getByRole('button',{name:'المفضلة',exact:true}).first().click();await page.getByRole('button',{name:'QA catalogue title',exact:true}).waitFor();await page.getByRole('button',{name:'أفلام',exact:true}).click();await page.getByRole('button',{name:'التالي',exact:true}).click();await page.getByText('2 / 2',{exact:true}).waitFor();await page.screenshot({path:'test-results/cinema-desktop.png',fullPage:true});
await page.setViewportSize({width:390,height:844});await page.screenshot({path:'test-results/cinema-mobile.png',fullPage:true});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'cinema horizontal overflow');
await page.goto('http://127.0.0.1:5173/tests/rebuild/index.html?music');await page.getByText('QA local track',{exact:true}).first().waitFor();await page.getByRole('button',{name:'شغّل QA local track',exact:true}).click();await page.waitForFunction(()=>{const a=document.querySelector('audio');return a&&!a.paused&&a.duration===20});await page.getByRole('button',{name:'إيقاف مؤقت',exact:true}).click();assert.equal(await page.locator('audio').evaluate(a=>a.paused),true);await page.getByRole('slider',{name:'موضع التشغيل',exact:true}).press('End');try{await page.waitForFunction(()=>{const a=document.querySelector('audio');return a&&a.currentTime>18&&a.currentTime<20},null,{timeout:10000});}catch(error){const diagnostic=await page.locator('audio').evaluate(a=>({time:a.currentTime,duration:a.duration,paused:a.paused,readyState:a.readyState,networkState:a.networkState,seekable:a.seekable.length,seekStart:a.seekable.length?a.seekable.start(0):null,seekEnd:a.seekable.length?a.seekable.end(0):null}));throw new Error('Audio seek did not reach target '+JSON.stringify(diagnostic),{cause:error});}assert.ok(await page.locator('audio').evaluate(a=>a.paused),'seeking while paused must not restart the track');await page.getByRole('textbox' ,{name:'اسم قائمة جديدة'}).fill('QA playlist');await page.getByRole('button',{name:'إنشاء',exact:true}).click();await page.getByRole('button',{name:'أضف للقائمة المختارة'}).click();await page.getByRole('button',{name:'QA playlist',exact:true}).click();await page.getByText('QA local track',{exact:true}).first().waitFor();await page.getByRole('button',{name:'أضف للطابور'}).click();await page.getByRole('button',{name:/الطابور \(1\)/}).click();await page.getByRole('button',{name:'إزالة',exact:true}).click();await page.screenshot({path:'test-results/music-mobile.png',fullPage:true});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'music horizontal overflow');await page.setViewportSize({width:1600,height:1000});await page.screenshot({path:'test-results/music-desktop.png',fullPage:true});
await page.setViewportSize({width:390,height:844});
await page.route('https://widget.anghami.com/**',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><title>Anghami fixture</title><style>body{background:#282337;color:white;font:16px system-ui;padding:24px}</style><p>Anghami player fixture</p>'}));
await page.addInitScript(()=>{
 if(!location.pathname.startsWith('/room-test/'))return;
 window.__sentPackets=[];
 window.WebSocket=class {
  static OPEN=1;
  static CONNECTING=0;
  readyState=0;
  constructor(){
   setTimeout(()=>{this.readyState=1;this.onopen?.();this.onmessage?.({data:JSON.stringify({type:'ready'})});},0);
  }
  send(packet){window.__sentPackets.push(JSON.parse(packet));}
  close(){this.readyState=3;}
 };
});
await page.route('**/room-test/**',route=>route.fulfill({contentType:'text/html',body:roomHtml}));
musicRoom={room_id:'qa-share',mode:'music',host_url:'http://127.0.0.1:5173/room-test/qa?role=host&mode=music',guest_url:'',room_code:'123456',public:false,lan:false,guest_connected:false};
await page.reload();
await page.getByRole('button',{name:'غرفة الموسيقى',exact:true}).click();
await page.getByRole('button',{name:'اختار أغنية',exact:true}).click();
await page.getByRole('button',{name:'أنغامي',exact:true}).click();
await page.getByRole('searchbox',{name:'البحث في أنغامي'}).fill('تملي معاك');
await page.getByRole('button',{name:'ابحث',exact:true}).click();
await page.getByRole('button',{name:'تملى معاك أغنية',exact:true}).click();
await page.getByText('الأغنية ظهرت في الغرفة. كل مشارك يقدر يشغّلها عنده.').waitFor({state:'attached'});
const hostFrame=page.frames().find(frame=>frame.url().includes('/room-test/'));
assert.ok(await hostFrame.evaluate(()=>window.__sentPackets.some(packet=>packet.type==='track'&&packet.value.id==='102704')));
await page.goto('http://127.0.0.1:5173/tests/rebuild/index.html?books');
await page.getByRole('group',{name:'تصنيف الكتب'}).getByRole('button',{name:'سلاسل مصرية',exact:true}).click();
await page.getByRole('heading',{name:'ما وراء الطبيعة',exact:true}).waitFor();
await page.getByRole('heading',{name:'رجل المستحيل',exact:true}).waitFor();
await page.locator('article').filter({has:page.getByRole('heading',{name:'ما وراء الطبيعة',exact:true})})
 .getByRole('button',{name:'أعداد السلسلة'}).click();
const issues=page.getByRole('dialog',{name:'ما وراء الطبيعة'});
await issues.locator('li').first().waitFor();
assert.equal(await issues.locator('li').count(),81);
assert.equal(await issues.getByRole('link',{name:/Google Play/}).getAttribute('href'),'https://play.google.com/store/books/series?id=lW27GwAAABAvdM');
await issues.locator('.bs-series-scroll').evaluate(el=>{el.scrollTop=el.scrollHeight;});
assert.ok(await issues.locator('.bs-series-scroll').evaluate(el=>el.scrollTop>0));
await issues.getByRole('textbox',{name:'ابحث عن عدد'}).fill('٨١');
assert.equal(await issues.locator('li').count(),1);
await issues.getByText(/الجزء الثاني/).waitFor();
await page.keyboard.press('Escape');
await issues.waitFor({state:'detached'});
await page.getByRole('button',{name:'احفظ رجل المستحيل',exact:true}).click();
await page.getByRole('button',{name:'مكتبتي',exact:true}).click();
assert.equal(await page.getByRole('heading',{name:'رجل المستحيل',exact:true}).count(),1);
assert.equal(await page.getByRole('heading',{name:'ما وراء الطبيعة',exact:true}).count(),0);
await page.getByRole('button',{name:'رعب',exact:true}).click();
await page.getByRole('searchbox',{name:'ابحث في الكتب'}).fill('الفيل الازرق');
await page.getByRole('heading',{name:'الفيل الأزرق',exact:true}).waitFor();
assert.ok(await page.locator('.bs-published-card .bs-real-cover').evaluate(art=>art.getBoundingClientRect().height<170),'book cover should fit a compact card');
assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'reading library horizontal overflow');
await page.screenshot({path:'test-results/library-mobile.png',fullPage:true});
assert.equal(await page.getByRole('button',{name:'حكايات برق',exact:true}).count(),0);
await page.getByRole('button',{name:'الكل',exact:true}).click();
await page.getByRole('searchbox',{name:'ابحث في الكتب'}).fill('زينب');
await page.getByRole('button',{name:'اقرأ في برق',exact:true}).click();
await page.getByLabel('PDF 1',{exact:true}).waitFor();
await page.locator('.bs-pdf-scroll').focus();
await page.keyboard.press('End');
await page.waitForFunction(()=>{
 const canvas=document.querySelector('canvas[aria-label="PDF 2"]');
 if(!canvas)return false;
 const box=canvas.getBoundingClientRect();
 return box.width>0&&Math.abs(box.height/box.width-.8)<.02&&canvas.width>0&&canvas.height/canvas.width<.82;
});
await page.keyboard.press('Home');
const cMaps=await page.request.get('http://127.0.0.1:5173/assets/pdfjs/cmaps/Adobe-Japan1-UCS2.bcmap');
const font=await page.request.get('http://127.0.0.1:5173/assets/pdfjs/standard_fonts/LiberationSans-Regular.ttf');
assert.ok(cMaps.ok()&&(await cMaps.body()).length>100,'PDF character maps must be reachable');
assert.equal((await font.body()).readUInt32BE(0),0x00010000,'PDF standard fonts must be served as font files');
const readerCanvas=page.getByLabel('PDF 1',{exact:true});
await readerCanvas.waitFor();
const oldWidth=await readerCanvas.evaluate(canvas=>canvas.getBoundingClientRect().width);
await page.locator('.bs-pdf-scroll').dispatchEvent('wheel',{ctrlKey:true,deltaY:-100,cancelable:true,bubbles:true});
await page.waitForFunction(width=>document.querySelector('canvas[aria-label="PDF 1"]')?.getBoundingClientRect().width>width,oldWidth);
await page.getByRole('combobox',{name:'ألوان القراءة'}).selectOption('warm');
assert.equal(await page.locator('.bs-document').getAttribute('data-paper'),'warm');
const pageNumber=page.getByRole('spinbutton',{name:'انتقل إلى صفحة'});
await pageNumber.fill('2');
await pageNumber.press('Enter');
await page.waitForFunction(()=>document.querySelector('.bs-page-jump input')?.value==='2');
await page.getByRole('button',{name:'علّم الصفحة',exact:true}).click();
assert.equal(await page.getByRole('button',{name:'علّم الصفحة'}).getAttribute('aria-pressed'),'true');
await page.getByRole('button',{name:'رجوع للمكتبة'}).click();
await page.getByRole('button',{name:'اقرأ في برق',exact:true}).click();
await page.waitForFunction(()=>document.querySelector('.bs-page-jump input')?.value==='2');

await page.addInitScript(()=>{
 window.pywebview={api:{
  check_update:async()=>({status:'available',current:'2.41.1',version:'2.41.2',notes:'تحسين اختباري',size:2000000}),
  download_update:async version=>{window.installerRequested=version;return {status:'installing'};},
 }};
});
await page.goto('http://127.0.0.1:5173/');
await page.getByRole('button',{name:'تحديث متاح',exact:true}).click();
const updateDialog=page.getByRole('dialog',{name:'تحديثات BARQ ONE'});
await updateDialog.getByText('تحسين اختباري').waitFor();
await updateDialog.getByRole('button',{name:'حدّث الآن',exact:true}).click();
assert.equal(await page.evaluate(()=>window.installerRequested),'2.41.2');
await page.keyboard.press('Escape');
assert.equal(await page.getByRole('button',{name:'اسأل برق',exact:true}).count(),0);
const chatNav=page.locator('.ops-header nav').getByRole('button',{name:'المحادثة',exact:true});
await chatNav.click();
const composer=page.locator('#chatComposer');
await composer.fill('افتح أنغامي');
await composer.press('Enter');
await page.getByRole('searchbox',{name:'البحث في أنغامي'}).waitFor();
const requestedPicker=page.getByRole('dialog',{name:'اختار أغنية',exact:true});
await requestedPicker.getByRole('button',{name:/تملى معاك عمرو دياب.*أغنية/}).click();

const preservedView=page.locator('.ops-media-page iframe[title="مشغّل الغرفة"]');
await preservedView.waitFor();
const stage=page.locator('.ops-media-page > .one-page');
await stage.evaluate(el=>{el.scrollTop=el.scrollHeight;});
assert.ok(await stage.evaluate(el=>el.scrollTop>0),'room should scroll in the outer app stage');
const roomBottom=await preservedView.boundingBox();
const stageBox=await stage.boundingBox();
assert.ok(roomBottom.y+roomBottom.height<=stageBox.y+stageBox.height+1,'room footer must be reachable in a short window');
const contextUpdate=page.waitForRequest(request=>request.method()==='PUT'&&
 request.url().endsWith('/v1/app-context/state')&&request.postDataJSON()?.section==='chat');
await chatNav.click();
await contextUpdate;
assert.equal(await preservedView.count(),1,'asking BARQ should preserve a playing media view');
await composer.fill('أنا كنت فاتح إيه');
await composer.press('Enter');
await page.getByText('آخر قسم فتحته هو الموسيقى · تملى معاك.',{exact:true}).waitFor();
assert.equal(appContextState?.previous,'music');
assert.equal(appContextState?.previous_view?.item,'تملى معاك');
assert.deepEqual(errors,[]);console.log('PASS: catalogue details, keyboard dismissal, favorites persistence, pagination, playlists, queue, provider name search, one-click room sharing, in-app PDF and bookmarks, room scrolling, app awareness, mobile overflow, no runtime errors');await browser.close();})().catch(e=>{console.error(e);process.exit(1)});
