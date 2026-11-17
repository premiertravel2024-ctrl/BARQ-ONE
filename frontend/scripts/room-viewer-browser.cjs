// BARQ guest-room regression: actual browser geometry and chat, not CSS text matching.
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const room=path.resolve(__dirname,'../../cloudflare/room.html');
const pictures=path.resolve(process.cwd(),'test-results');
fs.mkdirSync(pictures,{recursive:true});

(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  for(const [label,width,height] of [['desktop',1440,900],['mobile',390,844],['small-phone',360,800]]){
   const page=await browser.newPage({viewport:{width,height}});
   const pageErrors=[];
   page.on('pageerror',e=>pageErrors.push(e.message));
   await page.addInitScript(()=>{
    window.__roomSent=[];
    class FakeSocket{
     static OPEN=1;
     static CONNECTING=0;
     readyState=0;
     constructor(url){this.url=url;setTimeout(()=>{
       this.readyState=FakeSocket.OPEN;
       this.onopen?.();
       this.onmessage?.({data:JSON.stringify({type:'ready',ice_servers:[]})});
     },0);}
     send(packet){window.__roomSent.push(JSON.parse(packet));}
     close(){this.readyState=3;}
    }
    window.WebSocket=FakeSocket;
   });
   const url=pathToFileURL(room).href+'?role=guest&mode=video&paired=1';
   await page.goto(url);
   await page.locator('#waitingOverlay').waitFor({state:'visible'});
   await page.waitForFunction(()=>document.getElementById('status')?.textContent.includes('مستني'));
   const sizes=await page.evaluate(()=>{
    const stage=document.getElementById('videoStage').getBoundingClientRect();
    const video=document.getElementById('video').getBoundingClientRect();
    return {stageWidth:stage.width,videoWidth:video.width,stageHeight:stage.height,videoHeight:video.height,
     overflow:document.documentElement.scrollWidth-window.innerWidth};
   });
   assert.ok(sizes.stageWidth>=width*.55,'stage should get the available screen width '+JSON.stringify(sizes));
   assert.ok(Math.abs(sizes.stageWidth-sizes.videoWidth)<3,'video must fill the entire stage width '+JSON.stringify(sizes));
   assert.ok(Math.abs(sizes.stageHeight-sizes.videoHeight)<3,'video must fill the entire stage height '+JSON.stringify(sizes));
   assert.ok(sizes.overflow<=2,'unexpected horizontal scroll on '+label+' '+JSON.stringify(sizes));
   assert.equal(await page.locator('#guestWrap').isVisible(),true);
   await page.locator('#chatText').fill('رسالة تجربة من الضيف');
   await page.locator('#send').click();
   const packets=await page.evaluate(()=>window.__roomSent);
   assert.ok(packets.some(p=>p.type==='chat'&&p.text==='رسالة تجربة من الضيف'),
      'connected guest must be able to send chat without peer-joined');
   assert.equal(await page.locator('#chatText').inputValue(),'');
   assert.equal(await page.getByText('رسالة تجربة من الضيف').count(),1);
   assert.deepEqual(pageErrors,[],'room page errors');
   await page.screenshot({path:path.join(pictures,'room-guest-'+label+'.png'),fullPage:true});
   await page.close();
  }
  console.log('PASS BARQ guest rooms: real browser stage fill, mobile overflow, status and guest chat');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
