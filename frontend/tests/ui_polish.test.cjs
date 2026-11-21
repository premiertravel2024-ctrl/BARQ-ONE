const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname,'../src');
const read = name => fs.readFileSync(path.join(root,name),'utf8');

test('UI stylesheet is applied after existing styles, preserving the original app modules',()=>{
  const entry = read('main.tsx');
  assert.ok(entry.indexOf("'./styles/barqPolish.css'")>entry.indexOf("'./styles/global.css'"));
});
test('settings navigation search is controlled and filters all groups',()=>{
  const file=read('components/layout/SettingsModal.tsx');
  assert.match(file,/\[sectionQuery,setSectionQuery\]/);
  assert.match(file,/value=\{sectionQuery\}/);
  assert.match(file,/shownGroups\.map\(/);
  for(const id of ['computer','integrations','memory','performance','voice','models','network'])assert.match(file,new RegExp(`'${id}'`));
});
test('chat-only composer keeps send and cancellation, with voice controlled outside the composer',()=>{
  const composer=read('components/chat/Composer.tsx');
  assert.ok(composer.includes('onClick={()=>void send()}'));
  assert.ok(composer.includes('stopGeneration'));
  assert.doesNotMatch(composer,/void mic\(\)|void voiceCommand\(\)|<Mic |<MicOff |<AudioLines /);
  const app=read('App.tsx');
  assert.ok(app.includes('<ApprovalDialog enabled='));
  assert.ok(app.includes('<HandsFreeVoice/>'));
  assert.ok(app.includes('<ComputerControlStatus/>'));
  assert.ok(app.includes('barq-start-live-voice'));
});
test('BARQ ONE navigation retains model selection without mounting the removed workspace',()=>{
  const app=read('App.tsx');
  const sidebar=read('components/layout/OperationsFrame.tsx');
  assert.match(app,/<OperationsRail /);
  assert.match(app,/<ConversationHeader /);
  assert.doesNotMatch(app,/<Sidebar |<TopBar /);
  assert.match(sidebar,/<ModelSelector compact\/>/);
  assert.doesNotMatch(app,/<WorkspaceStudio/);
  assert.ok(sidebar.includes("sections.filter(([key])=>key!=='chat').map("));
  // Chat now lives with the other top-level destinations; no duplicate standalone control.
  assert.match(sidebar,/\['center','chat','library','tools','monitor'\]/);
  assert.doesNotMatch(sidebar,/className="ops-standalone-chat"/);
  assert.doesNotMatch(sidebar,/className="ops-more"/);
  assert.match(sidebar,/onClick=\{\(\)=>navigate\(key\)\}/);
  const shell=read('pages/BarqOne.tsx');
  for(const section of ['chat','center','voice','mission','library','installed','tools','monitor','automation','settings'])
    assert.ok(shell.includes(`['${section}',`),section);
  assert.doesNotMatch(sidebar,/onModeChange/);
  assert.match(read('components/chat/Composer.tsx'),/<ModelSelector\s*\/>/);
});
test('all studio actions remain addressable in the grouped rail',()=>{
  const file=read('components/workspace/WorkspaceStudio.tsx');
  for(const id of ['explorer','search','git','commands','run','guardian','build','tools','github','computer'])assert.ok(file.includes(`'${id}'`),id);
  assert.match(file,/activityGroups\.map\(/);
  assert.match(file,/setActivity\(id\)/);
});
test('the polish covers RTL, light theme, reduced motion and narrow screens',()=>{
  const css=read('styles/barqPolish.css');
  for(const text of ["html[dir='rtl']", "[data-theme='light']",'prefers-reduced-motion','max-width:590px','barq-settings-search','studio-rail-group','barq-composer-actions'])assert.ok(css.includes(text),text);
});

test('voice controller remains functional but has no floating overlay',()=>{
  const voice=read('components/chat/HandsFreeVoice.tsx');
  const composer=read('components/chat/Composer.tsx');
  const styles=read('styles/barqPolish.css');
  assert.doesNotMatch(voice,/barq-voice-float|dockSide|setDockSide|<aside/);
  assert.doesNotMatch(styles,/barq-voice-float/);
  assert.match(voice,/window.addEventListener\('barq-handsfree-start'/);
  assert.match(voice,/window.addEventListener\('barq-handsfree-stop'/);
  assert.match(voice,/mergeLiveTranscript/);
  assert.match(voice,/saveConversation/);
  // Desktop approvals outlive the voice session and live in the global controller.
  const desktop=read('components/workspace/ComputerControlStatus.tsx');
  assert.match(desktop,/\/v1\/computer\/approve/);
  // Stop moved into the chat task card; the floating execution HUD is removed.
  assert.match(read('components/chat/Message.tsx'),/\/v1\/computer\/stop/);
  assert.doesNotMatch(desktop,/barq-execution-panel/);
  assert.match(desktop,/onClick=\{\(\)=>void decide\(true\)\}/);
  assert.match(desktop,/onClick=\{\(\)=>void decide\(false\)\}/);
  assert.match(read('App.tsx'),/<ComputerControlStatus\/>/);
  assert.match(voice,/\/v1\/launch\/execute/);
  assert.doesNotMatch(composer,/handsfreeActive|barq-handsfree-state/);
  assert.match(read('App.tsx'),/barq-start-live-voice/);
});


test('Reading Library opens a published edition in the in-app reader',()=>{
  const one=read('pages/BarqOne.tsx');
  const catalogue=read('pages/BarqStories.tsx');
  const reader=read('pages/BookReader.tsx');
  assert.match(one,/\['stories','مكتبة القراءة','Reading Library'/);
  assert.match(one,/page==='stories'&&<BarqStories\/>/);
  assert.match(catalogue,/<BookReader /);
  assert.doesNotMatch(catalogue,/streamChat|Create a story with BARQ/);
  assert.match(reader,/\/v1\/reading\/books\//);
  // The reading cache remains local, but pages/bookmarks now also persist
  // to barq_library.sqlite3. Don't demand the legacy inline localStorage call.
  assert.match(reader,/loadReadingLocalState\('barq-reader:'\+book\.id\)/);
  assert.match(reader,/saveReadingLocalState\('barq-reader:'\+book\.id,JSON\.stringify\(progress\)\)/);
  const persistence=read('lib/readingLocalState.ts');
  assert.match(persistence,/localStorage\.setItem\(key,value\)/);
  assert.match(persistence,/method:'PUT'/);
  assert.match(persistence,/method:'POST'/);
  assert.match(persistence,/\/v1\/reading\/library\/state/);
  // New SQLite saves keep an offline outbox and expose retries; do not
  // silence a failed durable write or hydrate stale pages over pending edits.
  assert.match(persistence,/barq-reading-pending-v2/);
  assert.match(persistence,/retryReadingLocalState/);
  assert.match(persistence,/reading-storage-status/);
  assert.match(persistence,/\/state\/\x27\+encodeURIComponent\(key\)/);
  assert.match(persistence,/base\+\x27\/flush\x27/);
  assert.match(persistence,/pendingSnapshot\(\)\[key\]!==undefined/);
  assert.match(read('pages/LocalLibraryManager.tsx'),/Retry save|أعد الحفظ/);
});

test('wallpaper gallery supports applying and safe removal with confirmation',()=>{
 const ui=read('pages/Wallpapers.tsx');
 const css=read('pages/wallpaperGallery.css');
 assert.match(ui,/method:'DELETE'/);
 assert.match(ui,/className="bws-remove"/);
 assert.match(ui,/deleteTarget/);
 assert.match(css,/\.bws-active-strip/);
 assert.match(css,/\.bws-confirm/);
});
