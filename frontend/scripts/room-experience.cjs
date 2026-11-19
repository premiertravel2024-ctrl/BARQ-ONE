const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({...(process.env.BARQ_TEST_CHROMIUM?{executablePath:process.env.BARQ_TEST_CHROMIUM}:{}),headless:true,args:['--no-sandbox']});
 const pictures=path.resolve('test-results');fs.mkdirSync(pictures,{recursive:true});
 try{
  const page=await browser.newPage({viewport:{width:1280,height:850}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  const starts=[];let active=null;
  page.on('dialog',dialog=>dialog.accept());
  await page.addInitScript(()=>{
   class Socket {static OPEN=1;readyState=0;constructor(){setTimeout(()=>{this.readyState=1;this.onopen?.();this.onmessage?.({data:JSON.stringify({type:'ready',ice_servers:[]})});},10);}send(){}close(){this.readyState=3;}}
   window.WebSocket=Socket;
  });
  await page.route('**/room-fixture/**',route=>route.fulfill({contentType:'text/html',path:path.resolve('../cloudflare/room.html')}));
  await page.route('**/v1/**',route=>{
   const request=route.request(),url=new URL(request.url());let data={};
   if(url.pathname==='/v1/watchrooms/start'){
    const body=request.postDataJSON();starts.push(body);
    active={room_id:'qa',mode:body.mode,lan:body.lan,public:false,room_code:'123456',guest_connected:false,
     host_url:'http://127.0.0.1:5173/room-fixture/qa?role=host&paired=1&mode='+body.mode,
     guest_url:'http://127.0.0.1:5173/room-fixture/qa?paired=1&mode='+body.mode};data=active;
   }else if(url.pathname==='/v1/watchrooms/publish'){active={...active,public:true};data=active;}
   else if(url.pathname==='/v1/watchrooms/close'){active=null;}
   else if(url.pathname==='/v1/watchrooms/active')data={room:active};
   else if(url.pathname==='/v1/cinema/status')data={configured:true};
   else if(url.pathname==='/v1/cinema/genres')data={genres:[]};
   else if(url.pathname==='/v1/cinema/browse')data={results:[],page:1,total_pages:1,total_results:0};
   else if(url.pathname==='/v1/music/library')data={tracks:[]};
   route.fulfill({json:data});
  });
  for(const mode of ['video','music'])for(const local of [false,true]){
   await page.goto('http://127.0.0.1:5173/tests/rebuild/index.html?'+(mode==='music'?'music':'rooms'));
   if(mode==='music')await page.getByRole('button',{name:'غرفة الموسيقى',exact:true}).click();
   assert.equal(await page.getByRole('button',{name:'الشبكة المحلية',exact:true}).count(),0);
   await page.getByRole('button',{name:mode==='music'?'افتح غرفة':'افتح غرفة مشاهدة',exact:true}).click();
   const dialog=page.getByRole('dialog',{name:'غرفة جديدة'});
   await dialog.getByRole('button',{name:local?'الشبكة المحلية':'عبر الإنترنت',exact:true}).click();
   const frame=page.frameLocator('iframe[title="مشغّل الغرفة"]');
   await frame.locator('#uploadMedia').waitFor();
   assert.deepEqual(starts.at(-1),{mode,lan:local});
   await dialog.waitFor({state:'detached'});
   assert.equal(await frame.locator('#sources').getAttribute('open'),null);
   const before=await frame.locator('#videoStage').boundingBox();
   await frame.locator('#openMediaLink').click();
   await frame.locator('#linkMedia').fill('https://example.com/sample.mp4');
   const after=await frame.locator('#videoStage').boundingBox();
   assert.ok(Math.abs(after.y-before.y)<1,'source controls must not push the player down');
   await frame.locator('#linkMedia').press('Escape');
   assert.equal(await frame.locator('#sources').getAttribute('open'),null);
   if(mode==='music'){
    const art=await frame.locator('.music-now-art').boundingBox(),title=await frame.locator('#musicNowTitle').boundingBox();
    assert.ok(art.y+art.height<=title.y,'music artwork and title overlap');
    assert.equal(await frame.locator('#musicTransport').isVisible(),true);
   }
   await page.screenshot({path:path.join(pictures,'focused-'+mode+'-desktop.png'),fullPage:true});
   await page.setViewportSize({width:390,height:844});
   await frame.locator('#openMediaLink').click();
   const panel=await frame.locator('.source-panel').boundingBox();
   await page.screenshot({path:path.join(pictures,'focused-'+mode+'-mobile.png'),fullPage:true});
   assert.ok(panel.x>=0&&panel.x+panel.width<=390,'source popover fits a phone: '+JSON.stringify(panel));
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   await page.screenshot({path:path.join(pictures,'focused-'+mode+'-mobile.png'),fullPage:true});
   await page.getByRole('button',{name:'إنهاء الغرفة',exact:true}).click();
   await page.setViewportSize({width:1280,height:850});
  }
  await page.goto('http://127.0.0.1:5173/tests/rebuild/index.html?music');
  await page.getByRole('button',{name:'غرفة الموسيقى',exact:true}).click();
  await page.getByRole('searchbox',{name:'البحث في Spotify'}).waitFor();
  await page.screenshot({path:path.join(pictures,'music-lobby-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:path.join(pictures,'music-lobby-mobile.png'),fullPage:true});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.emulateMedia({reducedMotion:'reduce'});
  assert.equal(await page.locator('.bm-header button').first().evaluate(el=>parseFloat(getComputedStyle(el).transitionDuration)||0),0);
  assert.deepEqual(errors,[]);
  console.log('PASS compact rooms: launch transport, icon popovers, stable media, audio geometry, mobile and reduced motion');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1});
