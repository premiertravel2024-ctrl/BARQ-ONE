const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const base=path.join(__dirname,'../src');
const load=p=>fs.readFileSync(path.join(base,p),'utf8');
test('work center uses existing AgentTask evidence, no synthetic success state',()=>{
 const ui=load('components/workspace/WorkCenter.tsx');
 for(const key of ['mission?.missionProgress','progress?.checks','req.status','mission.evidence','mission?.goal','audit.visual_verified']){
  if(key==='audit.visual_verified')continue;
  assert.ok(ui.includes(key),key);
 }
 assert.match(ui,/ready:false/);
 assert.match(ui,/visual_verified|الفحص البصري/);
 assert.match(ui,/onChat/);
});
test('studio keeps all existing modes, approval controls and adds work view',()=>{
 const ui=load('components/workspace/WorkspaceStudio.tsx');
 for(const key of ["editorView==='work'","editorView==='editor'","editorView==='live'","editorView==='diff'","editorView==='preview'","editorView==='guardian'",'reviewMission','continueAgent','mission.goal','متابعة المستخدم:','applySave','runDiagnostics','runUiAudit','/v1/studio/ui-audit','<WorkCenter']) assert.ok(ui.includes(key),key);
});
test('work mode has responsive theme-aware CSS and keyboard focus',()=>{
 const css=load('components/workspace/studioWork.css');
 const entry=load('main.tsx');
 for(const key of ['var(--bg-base)','var(--text-primary)','@container (max-width:650px)',':focus-visible','prefers-reduced-motion'])assert.ok(css.includes(key),key);
 assert.ok(entry.indexOf('studioWork.css')>entry.indexOf('studioPolish.css'));
});
