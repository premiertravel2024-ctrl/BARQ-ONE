"""Ephemeral player for shared video and music rooms.

Files stay with the host and only captured tracks travel to the guest.
The browser must support captureStream and the selected media codec.
"""
PAGE = r"""<!doctype html>
<html lang="ar" dir="rtl">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BARQ ONE · Shared Rooms</title>
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

/* BARQ ONE room redesign - identical local and Cloudflare guests */
:root{--room-accent:#ef5076;--room-edge:#42313f;--room-surface:#1b1721;--room-muted:#b5a9b8}
body{background:radial-gradient(ellipse 85% 70% at 75% -30%,rgba(124,31,66,.20),transparent 70%),#100d14}
main{max-width:1530px;padding:clamp(12px,1.6vw,22px)}
.room-head{padding:14px 18px;background:linear-gradient(110deg,#221721,#161219);border:1px solid var(--room-edge);border-radius:16px}
.room-head h1{font-size:clamp(1.08rem,2.3vw,1.5rem);margin:2px 0 3px}
.room-eyebrow{font-size:.68rem;letter-spacing:1.5px;font-weight:850;color:#ff90af}
.room-head-note{margin:0;font-size:.74rem;color:var(--room-muted)}
.status{display:flex;align-items:center;gap:8px;max-width:100%;overflow-wrap:anywhere;font-size:.78rem;padding:8px 11px;background:#36212e;border:1px solid #734559;border-radius:99px}
.status:before{content:"";display:block;width:7px;height:7px;flex:0 0 7px;background:var(--room-accent);border-radius:50%;box-shadow:0 0 10px #e7527b}
.grid{grid-template-columns:minmax(0,1fr) minmax(245px,315px);align-items:start;gap:14px;margin-top:14px}
.panel{border:1px solid #3f3040;border-radius:16px;background:linear-gradient(135deg,#1d1822,#151219);padding:clamp(12px,1.6vw,20px)}
.section-header{display:flex;flex-wrap:wrap;gap:9px;align-items:center;margin-bottom:7px}
.section-header span{background:#3b2130;color:#ff9db4;border-radius:6px;padding:4px 8px;font-size:.7rem}
.section-header strong{font-size:.95rem}
.source-hint{color:#b9a8b9;font-size:.78rem;margin:0 0 11px}
.source-options{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:10px;margin:0 0 12px}
.source-options label{min-width:0}
.file-picker,.subtitle-picker{position:relative;display:flex;align-items:center;flex-wrap:wrap;gap:8px;padding:10px 12px;border:1px dashed #74435c;border-radius:12px;background:#241b27;cursor:pointer}
.file-picker{min-height:74px}
.file-picker:hover,.file-picker:focus-within,.subtitle-picker:hover,.subtitle-picker:focus-within{border-color:#f35b82;background:#33202e}
.file-picker #file,.subtitle-picker #subFile{position:absolute;inset:0;opacity:0;width:100%;height:100%;cursor:pointer;z-index:2}
.file-picker>span:first-child{font-size:.79rem;font-weight:700}
.file-cta{padding:6px 11px;background:#a6385c;border-radius:7px;font-size:.76rem;white-space:nowrap}
.file-name{display:block;flex:1 1 100%;color:#bdacbc;direction:auto;text-align:start;font-size:.72rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
#linkForm{margin:0;display:flex;align-items:stretch;gap:7px;min-width:0;flex-wrap:nowrap}
#linkMedia{flex:1;min-width:0;direction:ltr;text-align:left;padding:9px}
#linkForm button,#musicService button{background:#482a3a;border-color:#845067;white-space:nowrap;font-size:.76rem}
#musicService{display:flex;flex-wrap:wrap;gap:7px;border:1px solid #463042;background:#251a28;border-radius:12px;padding:9px;margin:0 0 11px}
#musicService input{min-width:0;flex:1;direction:ltr;text-align:left}
#localWrap>.row{padding:10px;background:#15121b;border-radius:12px;border:1px solid #372a37;flex-wrap:wrap}
#localWrap label{font-size:.76rem}
#subtitlePicker{padding:7px 10px;min-height:37px;border-style:solid}
#subFileName{color:#e3b8c9}
#guestControls{accent-color:#ec547a}
.player{background:radial-gradient(ellipse at 50% 30%,#311d2a,#08070d 72%);display:grid;place-items:center;border:1px solid #42303c;border-radius:13px;overflow:hidden;min-height:260px}
.player video{width:100%;height:auto;aspect-ratio:16/9;max-height:min(66vh,730px);object-fit:contain;display:block;border-radius:0;background:#060509}
.player[data-fit="cover"] video{object-fit:cover}
.player-screen-actions{position:absolute;top:11px;left:11px;z-index:10;display:flex;gap:7px;direction:rtl}
.player-screen-actions button{font-size:.76rem;background:#221925ed;border:1px solid #6a4055;color:#fff;border-radius:8px;padding:7px 11px;min-height:35px}
.player-screen-actions button:hover{background:#953455}
.player:fullscreen,.player:-webkit-full-screen{width:100vw;height:100vh;max-width:none;max-height:none;border:0;border-radius:0;background:#000;display:flex;align-items:center;justify-content:center}
.player:fullscreen video,.player:-webkit-full-screen video{width:100%;height:100%;max-height:100%;aspect-ratio:auto;border-radius:0;object-fit:contain}
.player[data-fit="cover"]:fullscreen video,.player[data-fit="cover"]:-webkit-full-screen video{object-fit:cover}
.player:fullscreen .player-screen-actions,.player:-webkit-full-screen .player-screen-actions{top:18px;left:18px}
.player:fullscreen .captions{bottom:10%;z-index:2}
.room-music .player{min-height:245px;padding:90px 15px 24px;position:relative;align-items:end}
.room-music .player:before{content:"♫";position:absolute;top:20px;left:calc(50% - 33px);width:66px;height:66px;border-radius:50%;background:linear-gradient(130deg,#522339,#251927);color:#ff9fb7;border:1px solid #795064;box-shadow:0 0 40px #b6385c44;font-size:2rem;display:grid;place-items:center}
.room-music .player audio{width:min(100%,750px);min-height:55px;border-radius:13px;background:#251b28}
.room-chat{position:sticky;top:8px;min-width:0}
.chat-heading{display:flex;justify-content:space-between;align-items:center;gap:8px;border-bottom:1px solid #40303b;padding-bottom:10px;margin-bottom:10px}
.chat-heading h2{margin:0;font-size:1rem}.chat-heading span{font-size:.69rem;color:#b9a6b5}
#messages{height:clamp(225px,40vh,475px);background:#110e16;border-color:#423040;border-radius:12px;padding:9px;overflow:auto}
.msg{border:0;border-radius:10px;background:#2a1e2a;margin-bottom:7px;padding:9px;font-size:.81rem}
.msg small{display:block;font-size:.68rem;color:#d6a6bb;margin-bottom:5px}
.chat-compose{margin:10px 0;display:flex;flex-wrap:nowrap}
#chatText{background:#231926;border:1px solid #644459;padding:10px 11px;min-width:0}
#send{background:#b8395e;border-color:#b8395e;padding:9px 14px;font-weight:700}
#emoji{flex-wrap:wrap}#emoji button{border-radius:10px;background:#332231}
#mediaNote{min-height:20px;font-size:.76rem;margin-bottom:0}
#officialMusic{background:#251c29;border:1px solid #493043;border-radius:12px;padding:12px;flex-wrap:wrap}
#officialMusic a{display:inline-block;background:#a9365a;border-radius:8px;padding:9px 12px;color:#fff;text-decoration:none}
button{transition:background-color .15s ease,border-color .15s ease}
button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid #ff799f;outline-offset:2px}
@media(max-width:1050px){.grid{grid-template-columns:minmax(0,1fr) minmax(220px,280px)}.source-options{grid-template-columns:1fr}}
@media(max-width:700px){main{padding:10px}.grid{grid-template-columns:1fr}.room-chat{position:static}#messages{height:235px}.source-options{grid-template-columns:1fr}#linkForm{flex-wrap:wrap}#linkForm button{width:100%}.room-head-note{display:none}.player{min-height:190px}.room-music .player{min-height:230px}}


/* Compact embedded cinema/music layout and touch-first phone experience */
.room-embedded .room-head{display:none}
.room-embedded main{padding:clamp(9px,1.2vw,17px)}
.room-embedded .grid{margin-top:0}
.room-embedded .panel{background:transparent;border-color:#3e2d3c}
.chat-empty{font-size:.76rem;color:#ab94a7;padding:19px 7px;text-align:center}
#messages{overscroll-behavior:contain;scrollbar-color:#694052 #16121b}
#officialMusic iframe{width:100%;min-width:0;max-width:100%;height:205px;border-radius:12px}
#officialMusic[hidden]{display:none}
.source-options{align-items:stretch}
.room-chat{align-self:start}
@media(max-width:800px){
 .room-head{gap:8px;padding:13px}
 .grid{grid-template-columns:1fr;gap:11px}
 .room-media-panel{order:1}
 .room-chat{order:2}
 .player{min-height:170px}
 .player video{max-height:65dvh}
 .room-music .player{min-height:190px;padding:75px 10px 15px}
 .room-music .player:before{width:54px;height:54px;left:calc(50% - 27px)}
 #messages{height:210px}
 .chat-compose{position:relative}
 .chat-compose #chatText{min-height:44px;flex:1}
 .chat-compose #send{min-height:44px}
 .file-picker{min-height:65px}
 #musicService{flex-direction:column}
 #musicService input,#musicService button{width:100%;min-height:43px}
 #localWrap>.row label{width:auto}
 .player-screen-actions button{min-height:44px;padding:8px 12px}
}
@media(max-width:450px){
 main{padding:8px}
 .panel{padding:12px;border-radius:13px}
 .room-eyebrow{font-size:.61rem}
 .source-options{gap:8px}
 .file-picker{flex-wrap:wrap}
 .source-options #linkForm{flex-wrap:wrap}
 .source-options #linkForm button{width:100%;min-height:43px}
 #localWrap>.row{gap:9px}
 #localWrap>.row>label:last-child{flex-basis:100%}
 .player-screen-actions{top:6px;left:6px;gap:5px}
 .player-screen-actions button{font-size:.68rem}
 .chat-heading h2{font-size:.88rem}
 .msg{padding:8px}
 #messages{height:190px}
}


/* Fireart-inspired audio player, responsive in embedded app and browser */
.room-music .room-head{background:linear-gradient(110deg,#30202f,#191520)}
.room-music .room-head-note{color:#d9becf}
.room-music .player{min-height:330px;background:radial-gradient(circle at 50% 18%,#6c2b4d55,transparent 70%),#141019;display:flex;flex-direction:column;gap:18px;justify-content:flex-end;align-items:stretch;padding:22px}
.room-music .player:before{display:none}
.music-now{display:flex;flex-direction:column;align-items:center;gap:9px;text-align:center;max-width:100%;min-width:0;padding-top:8px}
.music-now-overline{font-size:.67rem;letter-spacing:2px;color:#ffaac7;font-weight:900}
.music-now-art{width:116px;height:116px;display:grid;place-items:center;border-radius:22px;background:radial-gradient(circle at 20% 20%,#bf648a,#4b2545 64%,#291a2a);box-shadow:0 14px 36px #a8325d58;border:1px solid #b06790}
.music-now-art span{font-size:3.25rem;color:#fff;text-shadow:0 3px 15px #f39}
.music-now strong{font-size:clamp(1rem,2vw,1.33rem);max-width:100%;overflow-wrap:anywhere}
.music-now small{font-size:.75rem;color:#c6afc4}
.music-equalizer{height:23px;display:flex;gap:4px;align-items:center}
.music-equalizer i{width:4px;height:30%;display:block;border-radius:5px;background:#ff83ac}
.music-now.is-playing .music-equalizer i{animation:music-pulse .75s ease-in-out infinite alternate}
.music-now.is-playing .music-equalizer i:nth-child(2n){animation-delay:.25s;height:95%}
.music-now.is-playing .music-equalizer i:nth-child(3n){animation-delay:.43s;height:62%}
@keyframes music-pulse{to{transform:scaleY(.3)}}
.room-music .player audio{min-height:57px;background:#251c2a;border-radius:12px}
.room-music #officialMusic{display:grid;gap:9px;justify-items:stretch}
.room-music #officialMusic[hidden]{display:none}
.room-music #officialMusic iframe{height:300px}
.room-music #officialMusic a{text-align:center;justify-self:start}
.room-music #musicService{background:#1a151f}
.room-music #musicService input{min-height:44px}
.room-music .room-chat{background:#1c1722}
@media(max-width:760px){.room-music .player{min-height:300px;padding:16px}.music-now-art{width:86px;height:86px;border-radius:16px}.music-now-art span{font-size:2.5rem}.room-music #officialMusic iframe{height:235px}.room-music .room-chat{position:static}}
@media(prefers-reduced-motion:reduce){.music-now.is-playing .music-equalizer i{animation:none}}


/* BARQ shared-room identity and touch targets */
:root{color-scheme:dark}body{background:#0f1115;color:#f3f4f6}.panel,.room-music .room-chat{background:#191d24;border-color:#ffffff14}.player{background:#111419}.room-head,.room-music .room-head{background:#13161b}button,.room-music button{background:#a72c49;border-color:#cb4c6b;color:#fff}input,select,#chatText{background:#111419;border-color:#ffffff20;color:#f5f5f5}button:focus-visible,input:focus-visible,a:focus-visible,select:focus-visible{outline:2px solid #f28ca7;outline-offset:3px}.msg{overflow-wrap:anywhere}.chat-heading span,.sub{color:#a6afbd}@media(max-width:700px){button,input,select{min-height:44px}main,.panel,.grid{min-width:0}#messages{height:230px}#chatText{font-size:16px}.row{gap:8px}iframe{max-width:100%}}
</style></head>
<body><main><header class="room-head"><div><span class="room-eyebrow">BARQ ONE · SHARED ROOM</span><h1 id="roomTitle">سينما برق</h1><p class="room-head-note">شاركوا اللحظة، والملفات تفضل على جهاز صاحب الغرفة.</p></div><div id="status" class="status" role="status" aria-live="polite">جاري الاتصال...</div></header>
<div id="joinPanel" class="panel" hidden><p>ادخل كود الغرفة اللي بعتهولك صاحبها</p><div class="row"><input id="code" maxlength="6" inputmode="numeric" placeholder="Room code"><button id="join">دخول</button></div></div>
<div class="grid">
<section class="panel room-media-panel">
 <div id="localWrap" hidden>
  <div class="section-header"><span>الوسائط</span><strong id="sourceTitle">اختار اللي هتشغّله</strong></div>
  <p class="source-hint" id="sourceHint">فيديو من جهازك أو رابط مباشر للملف.</p>
  <div class="source-options">
   <label class="file-picker"><span id="fileLabel">فيديو من جهازك</span><span class="file-cta">اختيار ملف</span><span class="file-name" id="fileName">لم يتم اختيار ملف</span><input id="file" type="file" accept="video/*,.mp4,.webm,.mov" aria-label="اختيار ملف للغرفة"></label>
   <form class="row" id="linkForm"><input id="linkMedia" type="url" placeholder="https://…" aria-label="رابط ملف الوسائط" required><button>تشغيل من رابط</button></form>
  </div>
  <form class="row" id="musicService" hidden><input id="musicServiceUrl" type="url" required placeholder="رابط أغنية أو ألبوم" aria-label="رابط Spotify أو أنغامي"><button>مشاركة من Spotify أو أنغامي</button></form>
  <div class="row"><label id="videoQuality">الجودة <select id="quality"><option value="auto">تلقائي</option><option value="high">عالية</option><option value="medium">متوسطة</option><option value="low">منخفضة</option></select></label><label class="subtitle-picker" id="subtitlePicker">ترجمة SRT/VTT <span id="subFileName">اختيار ملف</span><input id="subFile" type="file" accept=".srt,.vtt,text/vtt" aria-label="اختيار ملف ترجمة"></label><label><input id="guestControls" type="checkbox"> السماح للضيف بالتحكم في التشغيل</label></div>
 </div>
 <div class="player" id="videoStage" data-fit="contain"><div class="music-now" id="musicNow" hidden>
  <span class="music-now-overline">NOW PLAYING · BARQ ONE</span>
  <div class="music-now-art" aria-hidden="true"><span>♫</span></div>
  <strong id="musicNowTitle">اختار أغنية نسمعها سوا</strong><small id="musicNowSource">ملف صوتي من جهازك أو رابط رسمي</small>
  <div class="music-equalizer" aria-hidden="true"><i/><i/><i/><i/><i/><i/><i/><i/><i/></div>
 </div><video id="video" controls playsinline></video><div id="captions" class="captions" dir="auto" aria-live="off"></div><div class="player-screen-actions" id="screenActions"><button type="button" id="fitMode" title="اختيار طريقة عرض الفيديو" aria-pressed="false">ملء الإطار</button><button type="button" id="enterFullscreen" title="عرض الفيديو على حجم الشاشة">⛶ ملء الشاشة</button></div></div>
 <div class="row" id="guestWrap" hidden><button id="resumePlayback">تشغيل الوسائط</button><button id="pauseRequest">اطلب إيقاف مؤقت</button><button id="seekRequest">اطلب تقديم 30 ثانية</button></div>
 <section id="officialMusic" hidden class="row"></section>
 <p class="sub" id="mediaNote" role="status"></p>
</section>
<aside class="panel room-chat"><div class="chat-heading"><h2>الدردشة</h2><span>لحظية ومؤقتة</span></div><div id="messages" aria-live="polite"><p class="chat-empty" id="chatEmpty">مفيش رسايل لسه. ابدأوا كلامكم هنا ✨</p></div><div class="row chat-compose"><input id="chatText" maxlength="500" placeholder="اكتب رسالة..." aria-label="Chat message"><button id="send">إرسال</button></div><p class="sub" id="typing"></p><div id="emoji"><button class="emoji" data-emoji="❤️">❤️</button><button class="emoji" data-emoji="🔥">🔥</button><button class="emoji" data-emoji="😂">😂</button><button class="emoji" data-emoji="👏">👏</button></div><p class="sub">الدردشة مؤقتة ومش بتتسجل على الهارد.</p></aside>
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
 document.body.classList.add('room-music');
 document.getElementById('musicNow').hidden=false;
 document.getElementById('sourceTitle').textContent='اختار الأغنية';
 document.getElementById('sourceHint').textContent='شغّل من جهازك أو استخدم رابط صوت مباشر أو Spotify وأنغامي.';
 document.getElementById('screenActions').hidden=true;
 var audio=document.createElement('audio');audio.id='video';audio.controls=true;video.replaceWith(audio);video=audio;
 document.getElementById('roomTitle').textContent='غرفة الموسيقى';
 document.getElementById('fileLabel').textContent='أغنية من جهازك';
 document.getElementById('file').accept='audio/*,.mp3,.m4a,.wav,.ogg,.opus,.flac';
 document.getElementById('videoQuality').hidden=true;
 document.getElementById('subtitlePicker').hidden=true;
}
var captionEl=document.getElementById('captions'),cues=[],lastCaption='';
var stage=document.getElementById('videoStage');
var fullscreenButton=document.getElementById('enterFullscreen'),fitButton=document.getElementById('fitMode');
function updateFullscreenLabel(){fullscreenButton.textContent=document.fullscreenElement?'⤡ إنهاء ملء الشاشة':'⛶ ملء الشاشة';}
document.addEventListener('fullscreenchange',updateFullscreenLabel);
fullscreenButton.onclick=function(){
 if(document.fullscreenElement){void document.exitFullscreen().catch(function(){note('تعذّر إغلاق وضع ملء الشاشة.');});return;}
 if(stage.requestFullscreen){
   void stage.requestFullscreen().then(updateFullscreenLabel).catch(function(){note('المتصفح منع ملء الشاشة. جرّب زر ملء الشاشة في مشغّل الفيديو.');});
 }else if(video.webkitEnterFullscreen){try{video.webkitEnterFullscreen();}catch(e){note('المشغّل لا يدعم ملء الشاشة.');}}
 else note('وضع ملء الشاشة غير متاح في المتصفح الحالي.');
};
fitButton.onclick=function(){
 var fill=stage.dataset.fit!=='cover';
 stage.dataset.fit=fill?'cover':'contain';
 fitButton.setAttribute('aria-pressed',String(fill));
 fitButton.textContent=fill?'إظهار الفيديو كاملًا':'ملء الإطار';
};

var status=document.getElementById('status');
var host=role==='host';
var paired=params.get('paired')==='1';
if(paired)document.body.classList.add('room-embedded');
var turnServers=[],officialTrack=null;
var reconnectTimer=null,reconnectAttempts=0,lastCode='',leaving=false,typingAt=0;
window.addEventListener('pagehide',function(){leaving=true;clearTimeout(reconnectTimer);if(socket)socket.close(1000);if(peer)peer.close();});
var nearby=params.get('lan')==='1'||/^http:\/\/(?:10\.|172\.|192\.168\.|100\.)/.test(location.origin);
document.getElementById('localWrap').hidden=!host;
document.getElementById('musicService').hidden=!host||!music;
document.getElementById('guestWrap').hidden=host;
document.getElementById('joinPanel').hidden=host||paired;
if(!host){video.controls=false;status.textContent='ادخل كود الغرفة';}
function note(text){status.textContent=text;}
function send(type,value){if(socket&&socket.readyState===WebSocket.OPEN){
 var data={type:type};
 if(type==='chat'||type==='reaction'||type==='typing'){data.text=String(value||'');}
 else data.value=value;
 socket.send(JSON.stringify(data));
 return true;
}return false;}
function addMessage(who,text){var box=document.getElementById('messages');var empty=document.getElementById('chatEmpty');if(empty)empty.remove();var row=document.createElement('div');row.className='msg';var meta=document.createElement('small');meta.textContent=who+' · '+new Date().toLocaleTimeString();var span=document.createElement('span');span.textContent=text;row.append(meta,span);box.appendChild(row);if(box.childElementCount>150)box.firstElementChild.remove();box.scrollTop=box.scrollHeight;}
function connect(code){
 clearTimeout(reconnectTimer);lastCode=code||lastCode;code=lastCode;
 if(socket&&(socket.readyState===WebSocket.OPEN||socket.readyState===WebSocket.CONNECTING))return;
 var proto=location.protocol==='https:'?'wss:':'ws:';
 var url=paired?proto+'//'+location.host+'/join-signal/'+encodeURIComponent(roomId):proto+'//'+location.host+'/signal/'+encodeURIComponent(roomId)+'?role='+role+'&token='+encodeURIComponent(token)+'&code='+encodeURIComponent(code||'');
 socket=new WebSocket(url);
 socket.onopen=function(){note('الغرفة متصلة');connected=true;reconnectAttempts=0;};
 socket.onerror=function(){note('فشل اتصال الغرفة');};
 socket.onclose=function(event){connected=false;guestPresent=false;pendingIce=[];note('اتصال الغرفة اتقطع');if(!host&&!paired)document.getElementById('joinPanel').hidden=false;if(peer){peer.close();peer=null;}
 if(!leaving&&![1000,1008].includes(event.code)&&reconnectAttempts<5){var delay=Math.min(15000,1000*Math.pow(2,reconnectAttempts++));note('الاتصال اتقطع؛ بنحاول نرجع الغرفة…');reconnectTimer=setTimeout(function(){connect(lastCode);},delay);}
 };
 socket.onmessage=async function(event){
  var packet;try{packet=JSON.parse(event.data);}catch(e){return;}
  if(packet.type==='ready'){turnServers=Array.isArray(packet.ice_servers)?packet.ice_servers:[];if(music&&packet.track)showTrack(packet.track);note(host?'مستني الضيف يدخل':'مستني صاحب الغرفة يشغّل ملف');}
  if(packet.type==='peer-joined'){guestPresent=true;nearby=packet.connection==='lan';note('الشخص التاني اتصل');if(host&&localStream)queueRTC(makeOffer);}
  if(packet.type==='track'&&music&&!host)showTrack(packet.value);
  if(packet.type==='peer-left'){guestPresent=false;pendingIce=[];note('الشخص التاني خرج');if(peer){peer.close();peer=null;}}
  if(packet.type==='chat'&&packet.text){addMessage(packet.role==='host'?'صاحب الغرفة':'الضيف',packet.text);}
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
  if(peer.connectionState==='failed'){var hasTurn=turnServers.some(function(s){return [].concat(s.urls||[]).some(function(u){return /^turns?:/.test(u);});});note(hasTurn?'تعذّر توصيل الوسائط بخادم الترحيل. جرّب إعادة الاتصال.':'الاتصال المباشر فشل. محتاج إعداد TURN لتوصيل الوسائط بين الشبكتين. الدردشة لسه متاحة.');}
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
  return {name:'أنغامي',url:'https://play.anghami.com/'+track.kind+'/'+track.id,
          embed:'https://widget.anghami.com/'+track.kind+'/'+track.id};
 if(track.provider==='anghami'&&track.kind==='share'&&/^[A-Za-z0-9_-]{5,60}$/.test(track.id))
  return {name:'أنغامي',url:'https://open.anghami.com/'+track.id};
 return null;
}
function showTrack(track){
 var panel=document.getElementById('officialMusic');
 if(music){
  var title=document.getElementById('musicNowTitle'),source=document.getElementById('musicNowSource');
  if(track){title.textContent=track.provider==='spotify'?'Spotify':'أنغامي';source.textContent=track.kind==='share'?'رابط مشاركة من أنغامي':'المشغّل الرسمي · اختار تشغيل داخل البطاقة';}
  else{title.textContent='اختار أغنية نسمعها سوا';source.textContent='ملف من الجهاز أو رابط رسمي';}
 }
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
  frame.style.cssText='width:100%;min-height:195px;height:clamp(195px,34vh,330px);border:0;border-radius:12px';
  frame.allow='autoplay; encrypted-media; fullscreen; picture-in-picture';
  frame.onerror=function(){note('المشغّل الرسمي ما اتحملش. افتح رابط الخدمة تحت المشغّل.');};
  panel.append(frame);
  var hint=document.createElement('p');hint.className='sub';hint.textContent='لو المشغّل فاضي أو الصوت مش شغال، افتح الخدمة من الرابط. التشغيل ممكن يحتاج تسجيل دخول؛ كل مشارك بيشغّل المشغّل الرسمي عنده.';panel.append(hint);
 }
 var link=document.createElement('a');
 link.href=provider.url;link.target='_blank';link.rel='noopener noreferrer';
 link.textContent=provider.embed?'فتح الأغنية في '+provider.name:'فتح رابط أنغامي في المتصفح';
 panel.append(link);
 if(track.kind==='share'){
  var hint=document.createElement('p');hint.className='sub';
  hint.textContent='الرابط المختصر من أنغامي. لو مظهرش مشغّل هنا، افتحه من أنغامي أو انسخ رابط الأغنية الكامل.';
  panel.append(hint);
 }
}
if(host&&music){
 document.getElementById('musicService').onsubmit=async function(event){
  event.preventDefault();
  try{
   if(!connected)throw Error('لازم الغرفة تكون متصلة الأول.');
   var url=new URL(document.getElementById('musicServiceUrl').value.trim());
   if(url.protocol!=='https:'||url.username||url.password||url.port)throw Error('استخدم رابط HTTPS من Spotify أو أنغامي.');
   var parts=url.pathname.split('/').filter(Boolean);
   if(/^intl-[a-z]{2}$/i.test(parts[0]||''))parts.shift();
   if(parts[0]==='embed')parts.shift();
   if(parts.length>2)throw Error('مسار رابط الموسيقى غير مدعوم.');
   var isShort=url.hostname==='open.anghami.com'&&parts.length===1&&/^[A-Za-z0-9_-]{5,60}$/.test(parts[0]);
   var track=isShort?{provider:'anghami',kind:'share',id:parts[0]}:
     {provider:url.hostname==='open.spotify.com'?'spotify':
               ['play.anghami.com','open.anghami.com','widget.anghami.com','www.anghami.com','anghami.com'].includes(url.hostname)?'anghami':'',
      kind:parts[0],id:parts[1]};
   if(!providerLink(track))throw Error('الرابط مش مدعوم. استخدم رابط أغنية رسمي من Spotify أو أنغامي.');
   if(isShort){
    note('جاري تحليل رابط أنغامي المختصر...');
    try{
     var response=await fetch('https://barq-one.ashraf-mohamed.workers.dev/api/resolve/anghami/'+encodeURIComponent(parts[0]),{mode:'cors'});
     if(response.ok){
      var expanded=await response.json();
      if(providerLink(expanded))track=expanded;
     }
    }catch(e){/* If link cannot be resolved safely, offer official external link. */}
   }
   loadVersion++;
   if(localStream){localStream.getTracks().forEach(function(t){t.stop();});localStream=null;}
   if(blobUrl){URL.revokeObjectURL(blobUrl);blobUrl=null;}
   officialTrack=track;showTrack(track);video.removeAttribute('src');video.load();
   send('track',track);
   note(track.kind==='share'?'شاركنا رابط أنغامي المختصر، لكن المشغّل يحتاج رابط الأغنية الكامل.':'تمت مشاركة الأغنية؛ اضغط تشغيل على المشغّل الرسمي.');
  }catch(e){note(e instanceof Error?e.message:'حصل خطأ في رابط الموسيقى.');}
 };
}
if(host){
 connect('');
 document.getElementById('subFile').addEventListener('change',async function(e){
  var file=e.target.files&&e.target.files[0];if(!file)return;
  document.getElementById('subFileName').textContent=file.name;
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
  if(music){var title=document.getElementById('musicNowTitle'),sourceType=document.getElementById('musicNowSource');
   title.textContent=external?new URL(source).pathname.split('/').pop()||'رابط صوت مباشر':source.name||'ملف صوتي';
   sourceType.textContent=external?'رابط صوت مباشر':'من جهاز صاحب الغرفة';
   document.getElementById('musicNow').classList.remove('is-playing');
  }
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
  var file=e.target.files&&e.target.files[0];document.getElementById('fileName').textContent=file?file.name:'لم يتم اختيار ملف';if(file)void loadMedia(file,false);
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
 ['play','pause','seeked'].forEach(function(type){video.addEventListener(type,function(){send('sync',{playing:!video.paused,position:video.currentTime});if(music)document.getElementById('musicNow').classList.toggle('is-playing',!video.paused);});});
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
function chat(){var input=document.getElementById('chatText'),msg=input.value.trim();if(!msg)return;
 if(!guestPresent){note('الشخص التاني مش متصل؛ رسالتك لسه في خانة الكتابة.');return;}
 if(!send('chat',msg)){note('اتصال الغرفة مش جاهز، جرّب لما يظهر متصل.');return;}
 addMessage(host?'أنا (المضيف)':'أنا (الضيف)',msg);input.value='';send('typing','');
}
document.getElementById('send').onclick=chat;
document.getElementById('chatText').onkeydown=function(e){if(e.key==='Enter'){e.preventDefault();chat();}else if(Date.now()-typingAt>1000){typingAt=Date.now();send('typing','1');}};
document.querySelectorAll('.emoji').forEach(function(btn){btn.onclick=function(){send('reaction',btn.dataset.emoji);addMessage('أنا',btn.dataset.emoji);};});
})();
</script></body></html>
"""

