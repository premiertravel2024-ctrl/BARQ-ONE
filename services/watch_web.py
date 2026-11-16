"""Ephemeral player for shared video and music rooms.

Files stay with the host and only captured tracks travel to the guest.
The browser must support captureStream and the selected media codec.
"""
PAGE = r"""<!doctype html>
<html lang="ar" dir="rtl">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BARQ Watch Together</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#0f0d13;color:#f7eef3;font-family:system-ui,Arial,sans-serif}
main{max-width:1200px;margin:auto;padding:24px}header{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
h1{font-size:1.45rem}h1 b{color:#ff6888}.sub{color:#c7b1c3;font-size:.9rem;line-height:1.7}
.grid{display:grid;grid-template-columns:minmax(0,1.9fr) minmax(270px,.8fr);gap:16px;margin-top:15px}
.panel{border:1px solid #473342;background:#19151f;border-radius:16px;padding:15px;min-width:0}
video,audio{width:100%;background:#070509;border-radius:12px;max-height:65vh}
button,input,select{border-radius:9px;border:1px solid #5c3848;background:#32212b;color:#fff;padding:8px;font:inherit}
button{cursor:pointer}button:hover{border-color:#ff6888}button:disabled{opacity:.45;cursor:default}
.row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:9px 0}.status{color:#ffd2dc}
#messages{height:46vh;overflow:auto;border:1px solid #453443;border-radius:10px;padding:12px;background:#100e15}
.msg{padding:6px 0;border-bottom:1px solid #302433;overflow-wrap:anywhere}
.msg small{color:#c4abb9;margin-inline-end:6px}#chatText{flex:1;min-width:0}
#emoji{display:flex;gap:8px}.emoji{border-radius:50%}input[type=file]{max-width:100%}
[hidden]{display:none!important}
#linkMedia{min-width:min(340px,100%);direction:ltr}.source-options{display:grid;gap:10px;margin-bottom:14px}.source-options label{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.player{position:relative;min-width:0}.captions{position:absolute;inset-inline:4%;bottom:9%;text-align:center;pointer-events:none;white-space:pre-line;overflow-wrap:anywhere;unicode-bidi:plaintext;font-size:clamp(1rem,2.4vw,1.65rem);font-weight:750;line-height:1.55;color:#fff;text-shadow:0 2px 6px #000,0 0 4px #000;max-height:32%;overflow:hidden}
@media(max-width:820px){.grid{grid-template-columns:1fr}#messages{height:260px}}
</style></head>
<body><main><header><div><h1 id="roomTitle">غرفة المشاهدة</h1></div><div id="status" class="status">جاري الاتصال...</div></header>
<div id="joinPanel" class="panel" hidden><p>ادخل كود الغرفة اللي بعتهولك صاحبها</p><div class="row"><input id="code" maxlength="6" inputmode="numeric" placeholder="Room code"><button id="join">دخول</button></div></div>
<div class="grid">
<section class="panel">
 <div id="localWrap" hidden>
  <div class="source-options">
   <label><span id="fileLabel">فيديو من جهازك</span><input id="file" type="file" accept="video/*,.mp4,.webm,.mov"></label>
   <form class="row" id="linkForm"><input id="linkMedia" type="url" placeholder="https://…" aria-label="رابط ملف الوسائط" required><button>تشغيل من رابط</button></form>
  </div>
  <form class="row" id="musicService" hidden><input id="musicServiceUrl" type="url" required placeholder="رابط أغنية أو ألبوم" aria-label="رابط Spotify أو أنغامي"><button>مشاركة من Spotify أو أنغامي</button></form>
  <div class="row"><label id="videoQuality">الجودة <select id="quality"><option value="auto">تلقائي</option><option value="high">عالية</option><option value="medium">متوسطة</option><option value="low">منخفضة</option></select></label><label id="subtitlePicker">ترجمة SRT/VTT <input id="subFile" type="file" accept=".srt,.vtt,text/vtt"></label><label><input id="guestControls" type="checkbox"> السماح للضيف بالتحكم في التشغيل</label></div>
 </div>
 <div class="player"><video id="video" controls playsinline></video><div id="captions" class="captions" dir="auto" aria-live="off"></div></div>
 <div class="row" id="guestWrap" hidden><button id="resumePlayback">تشغيل الوسائط</button><button id="pauseRequest">اطلب إيقاف مؤقت</button><button id="seekRequest">اطلب تقديم 30 ثانية</button></div>
 <section id="officialMusic" hidden class="row"></section>
 <p class="sub" id="mediaNote" role="status"></p>
</section>
<aside class="panel"><h2>الدردشة</h2><div id="messages" aria-live="polite"></div><div class="row"><input id="chatText" maxlength="500" placeholder="اكتب رسالة..." aria-label="Chat message"><button id="send">إرسال</button></div><p class="sub" id="typing"></p><div id="emoji"><button class="emoji" data-emoji="❤️">❤️</button><button class="emoji" data-emoji="🔥">🔥</button><button class="emoji" data-emoji="😂">😂</button><button class="emoji" data-emoji="👏">👏</button></div><p class="sub">الدردشة مؤقتة ومش بتتسجل على الهارد.</p></aside>
</div></main>
<script>
(function(){
'use strict';
var params=new URLSearchParams(location.search);
var role=params.get('role')==='host'?'host':'guest';
var token=params.get('token')||'';
var roomId=location.pathname.split('/').pop();
var socket=null,peer=null,localStream=null,connected=false,pendingIce=[];
var video=document.getElementById('video');
var music=params.get('mode')==='music';
var blobUrl=null,guestPresent=false,loadVersion=0,rtcQueue=Promise.resolve();
if(music){
 var audio=document.createElement('audio');audio.id='video';audio.controls=true;video.replaceWith(audio);video=audio;
 document.getElementById('roomTitle').textContent='غرفة الموسيقى';
 document.getElementById('fileLabel').textContent='أغنية من جهازك';
 document.getElementById('file').accept='audio/*,.mp3,.m4a,.wav,.ogg,.opus,.flac';
 document.getElementById('videoQuality').hidden=true;
 document.getElementById('subtitlePicker').hidden=true;
}
var captionEl=document.getElementById('captions'),cues=[],lastCaption='';
var status=document.getElementById('status');
var host=role==='host';
var paired=params.get('paired')==='1';
var turnServers=[],officialTrack=null;
var nearby=params.get('lan')==='1'||/^http:\/\/(?:10\.|172\.|192\.168\.|100\.)/.test(location.origin);
document.getElementById('localWrap').hidden=!host;
document.getElementById('musicService').hidden=!host||!music;
document.getElementById('guestWrap').hidden=host;
document.getElementById('joinPanel').hidden=host||paired;
if(!host){video.controls=false;status.textContent='ادخل كود الغرفة';}
function note(text){status.textContent=text;}
function send(type,value){if(socket&&socket.readyState===WebSocket.OPEN){socket.send(JSON.stringify({type:type,value:value}));}}
function addMessage(who,text){var box=document.getElementById('messages');var row=document.createElement('div');row.className='msg';var meta=document.createElement('small');meta.textContent=who+' · '+new Date().toLocaleTimeString();var span=document.createElement('span');span.textContent=text;row.append(meta,span);box.appendChild(row);if(box.childElementCount>150)box.firstElementChild.remove();box.scrollTop=box.scrollHeight;}
function connect(code){
 var proto=location.protocol==='https:'?'wss:':'ws:';
 var url=paired?proto+'//'+location.host+'/join-signal/'+encodeURIComponent(roomId):proto+'//'+location.host+'/signal/'+encodeURIComponent(roomId)+'?role='+role+'&token='+encodeURIComponent(token)+'&code='+encodeURIComponent(code||'');
 socket=new WebSocket(url);
 socket.onopen=function(){note('الغرفة متصلة');connected=true;};
 socket.onerror=function(){note('فشل اتصال الغرفة');};
 socket.onclose=function(){connected=false;guestPresent=false;note('اتصال الغرفة اتقطع');if(!host&&!paired)document.getElementById('joinPanel').hidden=false;if(peer){peer.close();peer=null;}};
 socket.onmessage=async function(event){
  var packet;try{packet=JSON.parse(event.data);}catch(e){return;}
  if(packet.type==='ready'){turnServers=Array.isArray(packet.ice_servers)?packet.ice_servers:[];if(music&&packet.track)showTrack(packet.track);note(host?'مستني الضيف يدخل':'مستني صاحب الغرفة يشغّل ملف');}
  if(packet.type==='peer-joined'){guestPresent=true;nearby=packet.connection==='lan';note('الشخص التاني اتصل');if(host&&localStream)queueRTC(makeOffer);}
  if(packet.type==='track'&&music&&!host)showTrack(packet.value);
  if(packet.type==='peer-left'){guestPresent=false;pendingIce=[];note('الشخص التاني خرج');if(peer){peer.close();peer=null;}}
  if(packet.type==='chat'){addMessage(packet.role==='host'?'صاحب الغرفة':'الضيف',packet.text||'');}
  if(packet.type==='typing'){document.getElementById('typing').textContent=packet.text?'الشخص التاني بيكتب...':'';}
  if(packet.type==='reaction'){addMessage('تفاعل',packet.text||'');}
  if(packet.type==='offer'&&!host)queueRTC(async function(){if(peer){peer.close();peer=null;}var pc=makePeer();await pc.setRemoteDescription(packet.value);await drainIce();var answer=await pc.createAnswer();await pc.setLocalDescription(answer);send('answer',pc.localDescription);});
  if(packet.type==='answer'&&host)queueRTC(async function(){if(peer&&peer.signalingState==='have-local-offer'){await peer.setRemoteDescription(packet.value);await drainIce();}});
  if(packet.type==='ice')queueRTC(async function(){if(peer&&peer.remoteDescription){try{await peer.addIceCandidate(packet.value);}catch(e){}}else if(pendingIce.length<100)pendingIce.push(packet.value);});
  if(packet.type==='request-pause'&&host){if(document.getElementById('guestControls').checked){video.paused?video.play():video.pause();}else addMessage('تنبيه','الضيف طلب إيقاف أو تشغيل الفيديو.');}
  if(packet.type==='request-seek'&&host){if(document.getElementById('guestControls').checked){video.currentTime=Math.max(0,video.currentTime+30);}else addMessage('تنبيه','الضيف طلب تقديم الفيديو.');}
  if(packet.type==='sync'&&!host){note('المشاهدة متصلة · '+(packet.value&&packet.value.playing?'تشغيل':'متوقف'));}
  if(packet.type==='subtitle'&&!host){captionEl.textContent=String(packet.value||'').slice(0,400);}
 };
}
function queueRTC(operation){rtcQueue=rtcQueue.then(operation).catch(function(){note('حصل خطأ في اتصال الوسائط. جرّب إعادة الاتصال بالغرفة.');});}
async function drainIce(){while(pendingIce.length){try{await peer.addIceCandidate(pendingIce.shift());}catch(e){}}}
function makePeer(){
 if(peer)return peer;
 peer=new RTCPeerConnection({iceServers:nearby?[]:turnServers.length?turnServers:[{urls:'stun:stun.l.google.com:19302'}]});
 peer.onicecandidate=function(e){if(e.candidate)send('ice',e.candidate.toJSON());};
 peer.onconnectionstatechange=function(){if(!peer)return;
  if(peer.connectionState==='failed')note(turnServers.length?'تعذّر توصيل الوسائط بخادم الترحيل.':'الاتصال المباشر للوسائط فشل. الغرفة دي محتاجة خادم ترحيل علشان تشتغل بين الشبكتين.');
  else note('WebRTC: '+peer.connectionState);
 };
 peer.ontrack=function(event){if(!host){video.srcObject=event.streams[0];video.play().catch(function(){note('اضغط تشغيل في المتصفح للسماح بالصوت');});}};
 if(host&&localStream){localStream.getTracks().forEach(function(track){peer.addTrack(track,localStream);});}
 return peer;
}
async function makeOffer(){
 if(!host||!localStream||!connected||!guestPresent)return;
 if(peer){peer.close();peer=null;}
 var pc=makePeer();
 var quality=document.getElementById('quality').value;
 var maxRate=quality==='high'?4000000:quality==='medium'?1800000:quality==='low'?600000:null;
 if(maxRate){for(var sender of pc.getSenders()){if(sender.track&&sender.track.kind==='video'){var p=sender.getParameters();if(!p.encodings||!p.encodings.length)continue;p.encodings[0].maxBitrate=maxRate;try{await sender.setParameters(p);}catch(e){}}}}
 var offer=await pc.createOffer();await pc.setLocalDescription(offer);send('offer',pc.localDescription);
}
function timeInSeconds(value){
 var match=/^(?:(\d{1,2}):)?(\d{2}):(\d{2})[.,](\d{3})$/.exec(String(value||'').trim());
 return match?Number(match[1]||0)*3600+Number(match[2])*60+Number(match[3])+Number(match[4])/1000:null;
}
function parseSubtitles(text){
 var blocks=String(text||'').replace(/\r/g,'').split(/\n\s*\n/),result=[];
 blocks.forEach(function(block){
  var lines=block.split('\n'),i=lines.findIndex(function(line){return line.includes('-->');});
  if(i<0)return;
  var bits=lines[i].split('-->'),start=timeInSeconds(bits[0]),end=timeInSeconds(bits[1].split(/\s+/)[1]||bits[1].trim());
  var words=lines.slice(i+1).join('\n').trim();
  if(start!==null&&end!==null&&end>start&&words)result.push({start:start,end:end,text:words.slice(0,400)});
 });
 return result.sort(function(a,b){return a.start-b.start;}).slice(0,2500);
}
function updateSubtitle(){
 var elapsed=video.currentTime||0;
 var line=cues.find(function(item){return elapsed>=item.start&&elapsed<item.end;});
 var caption=line?line.text:'';
 if(caption===lastCaption)return;
 lastCaption=caption;captionEl.textContent=caption;
 if(host)send('subtitle',caption);
}
function providerLink(track){
 if(!track)return null;
 if(track.provider==='spotify'&&/^(track|album|playlist)$/.test(track.kind)&&/^[A-Za-z0-9]{22}$/.test(track.id))
  return {name:'Spotify',url:'https://open.spotify.com/'+track.kind+'/'+track.id,
          embed:'https://open.spotify.com/embed/'+track.kind+'/'+track.id};
 if(track.provider==='anghami'&&/^(song|album|playlist|artist)$/.test(track.kind)&&/^[0-9]{1,15}$/.test(track.id))
  return {name:'أنغامي',url:'https://play.anghami.com/'+track.kind+'/'+track.id};
 return null;
}
function showTrack(track){
 var panel=document.getElementById('officialMusic');
 panel.replaceChildren();
 var provider=providerLink(track);
 panel.hidden=!provider;
 video.hidden=!!provider;
 if(!provider)return;
 if(peer){peer.close();peer=null;}
 video.pause();video.srcObject=null;
 if(provider.embed){
  var frame=document.createElement('iframe');
  frame.src=provider.embed;
  frame.title=provider.name;
  frame.style.cssText='width:100%;height:160px;border:0';
  frame.allow='autoplay; encrypted-media; fullscreen; picture-in-picture';
  panel.append(frame);
 }
 var link=document.createElement('a');
 link.href=provider.url;link.target='_blank';link.rel='noopener noreferrer';
 link.textContent='تشغيل في '+provider.name;
 panel.append(link);
}
if(host&&music){
 document.getElementById('musicService').onsubmit=function(event){
  event.preventDefault();
  try{
   if(!connected)throw Error();
   var url=new URL(document.getElementById('musicServiceUrl').value);
   if(url.protocol!=='https:'||url.username||url.password||url.port)throw Error();
   var parts=url.pathname.split('/').filter(Boolean);
   if(parts[0]==='embed')parts.shift();
   var track={provider:url.hostname==='open.spotify.com'?'spotify':url.hostname==='play.anghami.com'?'anghami':'',kind:parts[0],id:parts[1]};
   if(parts.length!==2||!providerLink(track))throw Error();
   loadVersion++;
   if(localStream){localStream.getTracks().forEach(function(t){t.stop();});localStream=null;}
   if(blobUrl){URL.revokeObjectURL(blobUrl);blobUrl=null;}
   officialTrack=track;showTrack(track);video.removeAttribute('src');video.load();
   send('track',track);
  }catch(e){note('اتصل بالغرفة وحط رابط أصلي من Spotify أو أنغامي.');}
 };
}
if(host){
 connect('');
 document.getElementById('subFile').addEventListener('change',async function(e){
  var file=e.target.files&&e.target.files[0];if(!file)return;
  if(file.size>1048576){note('ملف الترجمة كبير جدًا. الحد 1MB');return;}
  try{cues=parseSubtitles(await file.text());lastCaption='';updateSubtitle();
   document.getElementById('mediaNote').textContent='الترجمة اتحملت محليًا. اللي بيتبعت للضيف هو السطر الحالي فقط.';
  }catch(error){note('مش قادر أقرأ ملف الترجمة. جرّب SRT أو VTT');}
 });
 video.addEventListener('timeupdate',updateSubtitle);
 video.addEventListener('seeked',updateSubtitle);
 async function loadMedia(source,external){
  var version=++loadVersion;
  if(officialTrack){officialTrack=null;showTrack(null);send('track',null);}
  if(peer){peer.close();peer=null;}
  if(localStream){localStream.getTracks().forEach(function(track){track.stop();});localStream=null;}
  if(blobUrl){URL.revokeObjectURL(blobUrl);blobUrl=null;}
  video.pause();
  if(external)video.crossOrigin='anonymous';else video.removeAttribute('crossorigin');
  if(!external)blobUrl=URL.createObjectURL(source);
  video.src=external?source:blobUrl;
  try{
   await video.play();
   if(version!==loadVersion)return;
   var capture=video.captureStream||video.mozCaptureStream;
   if(!capture)throw Error('المشغّل لا يدعم مشاركة الوسائط');
   localStream=capture.call(video);
   if(!localStream.getTracks().length)throw Error('الملف مفيهوش صوت أو فيديو متوافق');
   document.getElementById('mediaNote').textContent=external?'المشاركة شغالة من الرابط المباشر.':'الملف بيتشارك مباشرة من جهازك.';
   queueRTC(makeOffer);
  }catch(error){if(version===loadVersion)note(external?'الرابط لازم يكون HTTPS مباشر لملف قابل للتشغيل والمشاركة.':'تعذّر تشغيل الملف. جرّب MP4 أو WebM للفيديو، أو MP3 أو WAV للموسيقى.');}
 }
 document.getElementById('file').addEventListener('change',function(e){
  var file=e.target.files&&e.target.files[0];if(file)void loadMedia(file,false);
 });
 document.getElementById('linkForm').onsubmit=function(event){
  event.preventDefault();
  try{
   var url=new URL(document.getElementById('linkMedia').value);
   if(url.protocol!=='https:'||url.username||url.password)throw Error();
   void loadMedia(url.href,true);
  }catch(error){note('اكتب رابط HTTPS مباشر لملف الوسائط.');}
 };
 window.addEventListener('pagehide',function(){if(blobUrl)URL.revokeObjectURL(blobUrl);if(localStream)localStream.getTracks().forEach(function(track){track.stop();});});
 ['play','pause','seeked'].forEach(function(type){video.addEventListener(type,function(){send('sync',{playing:!video.paused,position:video.currentTime});});});
}else{
 document.getElementById('join').onclick=function(){var code=document.getElementById('code').value.trim();if(!/^[0-9]{6}$/.test(code)){note('الكود لازم يكون 6 أرقام');return;}document.getElementById('joinPanel').hidden=true;connect(code);};
 var automaticCode=location.hash.slice(1);
 if(paired){connect('');}
 else if(/^[0-9]{6}$/.test(automaticCode)){
  document.getElementById('code').value=automaticCode;
  document.getElementById('joinPanel').hidden=true;
  connect(automaticCode);
 }
 document.getElementById('resumePlayback').onclick=function(){video.muted=false;video.play().catch(function(){note('المتصفح منع التشغيل التلقائي؛ اضغط تشغيل مرة تانية.');});};
 document.getElementById('pauseRequest').onclick=function(){send('request-pause',true);};
 document.getElementById('seekRequest').onclick=function(){send('request-seek',30);};
}
function chat(){var input=document.getElementById('chatText'),msg=input.value.trim();if(!msg||!connected||socket.readyState!==WebSocket.OPEN)return;socket.send(JSON.stringify({type:'chat',text:msg}));addMessage(host?'أنا (المضيف)':'أنا (الضيف)',msg);input.value='';send('typing','');}
document.getElementById('send').onclick=chat;
document.getElementById('chatText').onkeydown=function(e){if(e.key==='Enter'){e.preventDefault();chat();}else send('typing','1');};
document.querySelectorAll('.emoji').forEach(function(btn){btn.onclick=function(){send('reaction',btn.dataset.emoji);addMessage('أنا',btn.dataset.emoji);};});
})();
</script></body></html>"""
