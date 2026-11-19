// BARQ guest-room regression: actual browser geometry and chat, not CSS text matching.
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const room=path.resolve(__dirname,'../../cloudflare/room.html');
const pictures=path.resolve(process.cwd(),'test-results');
fs.mkdirSync(pictures,{recursive:true});

async function verifyPlayback(browser,mode){
 const context=await browser.newContext({viewport:{width:1180,height:720}});
 const sockets=new Map(), history=[];
 try{
  await context.route('http://localhost:44331/**',route=>route.fulfill({contentType:'text/html',path:room}));
  await context.route('https://widget.anghami.com/**',route=>route.fulfill({contentType:'text/html',body:'<button>Play Anghami</button>'}));
  await context.route('https://open.spotify.com/**',route=>route.fulfill({contentType:'text/html',body:'<button>Play Spotify</button>'}));
  await context.routeWebSocket('ws://localhost:44331/join-signal/*',socket=>{
   const role=sockets.has('host')?'guest':'host';
   sockets.set(role,socket);
   const other=role==='host'?'guest':'host';
   socket.onMessage(message=>{
    const packet=JSON.parse(message);
    history.push({role,type:packet.type});
    sockets.get(other)?.send(message);
    if(packet.type==='track')sockets.get(other)?.send(message);
   });
   socket.send(JSON.stringify({type:'ready',ice_servers:[]}));
   if(sockets.has(other))for(const client of sockets.values())client.send(JSON.stringify({type:'peer-joined',connection:'lan'}));
  });
  await context.addInitScript(()=>{
   window.__peers=[];
   const RTC=RTCPeerConnection;
   window.RTCPeerConnection=class extends RTC{
    constructor(...options){super(...options);window.__peers.push(this);}
   };
  });
  const host=await context.newPage();
  await host.addInitScript(()=>{
   const capture=HTMLMediaElement.prototype.captureStream;
   HTMLMediaElement.prototype.captureStream=function(){
    const native=capture.call(this);
    const delayed=new MediaStream();
    window.setTimeout(()=>{
     native.getTracks().forEach(track=>delayed.addTrack(track));
     delayed.dispatchEvent(new Event('addtrack'));
    },300);
    return delayed;
   };
  });
  await host.goto('http://localhost:44331/r/test?role=host&paired=1&mode='+mode);
  await host.locator('#sources summary').click();
  await host.locator('#linkMedia').click();
  const field=await host.locator('#linkMedia').evaluate(input=>({
   height:input.getBoundingClientRect().height,
   outline:getComputedStyle(input).outlineStyle,
   style:getComputedStyle(input).fontStyle,
  }));
  assert.ok(field.height<=40,'source input should be compact');
  assert.equal(field.outline,'none');
  assert.equal(field.style,'normal');
  await host.locator('#sources summary').click();
  await host.locator('#sources summary').click();
  const fixture=await host.evaluate(async audioOnly=>{
   const audio=new AudioContext();
   const destination=audio.createMediaStreamDestination();
   const oscillator=audio.createOscillator();
   oscillator.connect(destination);oscillator.start();
   window.keepAudioContext=audio;
   const canvas=document.createElement('canvas');
   canvas.width=160;canvas.height=90;
   const drawing=canvas.getContext('2d');
   let frame=0;
   const interval=window.setInterval(()=>{
    drawing.fillStyle=frame++%2?'#623388':'#206549';drawing.fillRect(0,0,160,90);
   },40);
   const stream=new MediaStream([...destination.stream.getAudioTracks(),...(!audioOnly?canvas.captureStream(25).getVideoTracks():[])]);
   const recorder=new MediaRecorder(stream,{mimeType:audioOnly?'audio/webm':'video/webm'});
   const bytes=await new Promise(resolve=>{
    recorder.ondataavailable=event=>resolve(event.data.arrayBuffer());
    recorder.start();
    window.setTimeout(()=>recorder.stop(),3500);
   });
   window.clearInterval(interval);
   stream.getTracks().forEach(track=>track.stop());
   oscillator.stop();await audio.close();
   return Array.from(new Uint8Array(bytes));
  },mode==='music');
  await host.locator('#video').evaluate(media=>{media.loop=true;});
  await host.locator('#file').setInputFiles({name:'sample.webm',mimeType:mode==='music'?'audio/webm':'video/webm',buffer:Buffer.from(fixture)});
  try{
   await host.waitForFunction(()=>{const media=document.querySelector('#video');return media.readyState>=2&&!media.paused&&!document.querySelector('#sources').open;},null,{timeout:10000});
  }catch(error){
   const state=await host.locator('#video').evaluate(media=>({error:media.error?.message,time:media.currentTime,paused:media.paused,ready:media.readyState,secure:isSecureContext,status:document.querySelector('#status').textContent}));
   throw new Error(mode+' host did not share media: '+JSON.stringify(state),{cause:error});
  }
  assert.equal(await host.locator('#sources').getAttribute('open'),null);
  const guest=await context.newPage();
  await guest.goto('http://localhost:44331/r/test?role=guest&paired=1&mode='+mode);
  try{await guest.waitForFunction(audioOnly=>{
   const media=document.querySelector('#video');
   return media.srcObject?.getAudioTracks().length>0&&(audioOnly||media.videoWidth===160)&&media.currentTime>0&&!media.paused;
  },mode==='music',{timeout:10000});}catch(error){
   const inspect=page=>page.evaluate(()=>({
    status:document.querySelector('#status').textContent,
    peers:window.__peers.map(pc=>[pc.connectionState,pc.iceConnectionState,pc.signalingState]),
    tracks:document.querySelector('#video').srcObject?.getTracks().map(track=>[track.kind,track.muted]),
    size:document.querySelector('#video').videoWidth,
    time:document.querySelector('#video').currentTime,
   }));
   throw new Error(mode+' guest did not receive media: '+JSON.stringify({history,host:await inspect(host),guest:await inspect(guest)}),{cause:error});
  }
  assert.ok(history.some(packet=>packet.type==='answer'&&packet.role==='guest'));
  await guest.evaluate(()=>{
   const peer=window.__peers.at(-1);
   Object.defineProperty(peer,'connectionState',{value:'failed'});
   peer.dispatchEvent(new Event('connectionstatechange'));
  });
  await guest.waitForFunction(()=>window.__peers.length>1&&window.__peers.at(-1).connectionState==='connected');
  assert.ok(history.some(packet=>packet.type==='request-media'&&packet.role==='guest'));
  await guest.waitForFunction(()=>{
   const media=document.querySelector('#video');
   return media.srcObject&&media.readyState>=2&&media.currentTime>0&&!media.paused;
  });
  await guest.locator('#waitingOverlay').waitFor({state:'hidden'});
  await guest.locator('#resumePlayback').click();
  assert.equal(await guest.locator('#video').evaluate(media=>media.muted),false);
  const guestComposer=guest.locator('#chatText');
  await guestComposer.fill('أهلاً');
  await guestComposer.press('Space');
  await guestComposer.press('Space');
  await guestComposer.pressSequentially('برق');
  await guestComposer.press('Shift+Enter');
  await guestComposer.pressSequentially('سطر تاني');
  assert.equal(await guestComposer.inputValue(),'أهلاً  برق\nسطر تاني');
  await guestComposer.press('Enter');
  await host.waitForFunction(()=>document.querySelector('#messages .msg span')?.textContent==='أهلاً  برق\nسطر تاني');
  await host.locator('#chatText').fill('رد المضيف');
  assert.equal(await host.locator('#chatText').evaluate(field=>getComputedStyle(field).outlineStyle),'none');
  const toolbar=await host.locator('.room-viewer-actions').boundingBox();
  const player=await host.locator('#videoStage').boundingBox();
  assert.ok(toolbar.y+toolbar.height<=player.y+1,'room controls must stay above the media');
  await host.locator('#send').click();
  await guest.locator('#messages .msg[data-mine="false"]').getByText('رد المضيف').waitFor();
  if(mode==='music'){
   for(const [name,link,selector] of [
    ['Anghami','https://play.anghami.com/song/102704','iframe[title="أنغامي"]'],
    ['Spotify','https://open.spotify.com/track/4ZXnE6NdKAQMaMzsDuFurd','iframe[title="Spotify"]'],
   ]){
    await host.locator('#sources summary').click();
    await host.locator('#musicServiceUrl').fill(link);
    await host.locator('#musicService button').click();
    await guest.frameLocator(selector).getByRole('button',{name:'Play '+name}).waitFor();
    assert.equal(await guest.locator(selector).count(),1);
    assert.equal(await guest.locator('#videoStage').isVisible(),false);
    await host.locator('#sources summary').click();
   }
  }
 }finally{await context.close();}
}

(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-features=WebRtcHideLocalIpsWithMdns','--allow-loopback-in-peer-connection']});
 try{
  for(const [label,width,height] of [['desktop',1440,900],['mobile',390,844],['small-phone',360,800]]){
   const page=await browser.newPage({viewport:{width,height}});
   const pageErrors=[];
   page.on('pageerror',e=>pageErrors.push(e.message));
   await page.addInitScript(()=>{
    window.__roomSent=[];
    window.__roomOpenCount=0;
    class FakeSocket{
     static OPEN=1;
     static CONNECTING=0;
     readyState=0;
     constructor(url){this.url=url;window.__roomSocket=this;setTimeout(()=>{
       window.__roomOpenCount++;
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
   assert.equal(await page.locator('#screenActions button').count(),1);
   assert.equal(await page.locator('#video').evaluate(video=>getComputedStyle(video).objectFit),'cover');
   assert.equal(await page.getByRole('button',{name:'إرسال الرسالة'}).isDisabled(),true);
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
   await page.locator('#chatToggle').click();
   assert.equal(await page.locator('#roomChat').isVisible(),false);
   assert.equal(await page.locator('#chatToggle').getAttribute('aria-expanded'),'false');
   const focusWidth=await page.locator('#videoStage').evaluate(stage=>stage.getBoundingClientRect().width);
   assert.ok(focusWidth+2>=sizes.stageWidth,'hiding chat must preserve or expand the stage');
   await page.locator('#chatToggle').click();
   assert.equal(await page.locator('#roomChat').isVisible(),true);

   await page.locator('#chatText').fill('رسالة');
   await page.locator('#chatText').press('Space');
   await page.locator('#chatText').pressSequentially('تجربة من الضيف');
   assert.equal(await page.locator('#chatText').inputValue(),'رسالة تجربة من الضيف');
   await page.locator('#send').click();
   const packets=await page.evaluate(()=>window.__roomSent);
   assert.ok(packets.some(p=>p.type==='chat'&&p.text==='رسالة تجربة من الضيف'),
      'connected guest must be able to send chat without peer-joined');
   assert.equal(await page.locator('#chatText').inputValue(),'');
   assert.equal(await page.getByText('رسالة تجربة من الضيف').count(),1);
   await page.evaluate(()=>{
    window.__roomSocket.readyState=3;
    window.__roomSocket.onclose({code:1006});
   });
   await page.waitForFunction(()=>window.__roomOpenCount===2);
   await page.waitForFunction(()=>document.getElementById('status')?.textContent.includes('مستني'));
   assert.deepEqual(pageErrors,[],'room page errors');
   await page.screenshot({path:path.join(pictures,'room-guest-'+label+'.png'),fullPage:true});
   await page.close();
  }
  console.log('PASS BARQ guest rooms: responsive layout, chat and reconnection');
  let interfaces;
  try{interfaces=require('node:os').networkInterfaces();}
  catch(error){if(error.info?.errno!==1)throw error;}
  if(process.env.CI||interfaces&&Object.values(interfaces).flat().some(address=>!address.internal)){
   await verifyPlayback(browser,'video');
   await verifyPlayback(browser,'music');
   console.log('PASS BARQ guest playback: WebRTC video and audio, and provider players');
  }else console.log('WebRTC integration runs in CI because this workspace has no usable network interface.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
