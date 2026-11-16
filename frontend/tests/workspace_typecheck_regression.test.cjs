const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../src/components/workspace/WorkspaceStudio.tsx'),'utf8');

test('workspace tabs keep work navigation without comparing impossible narrowed state',()=>{
  const branch=source.split('studio-editor-modes',2)[1].split("editorView==='guardian'?<GuardianDashboard",1)[0];
  assert.ok(branch.includes("setEditorView('work')"));
  assert.doesNotMatch(branch,/editorView\s*===\s*'work'/);
  assert.ok(branch.includes("editorView==='editor'"));
});
test('workspace retains plan, code, preview, diff and guardian navigation',()=>{
 for(const view of ['work','editor','live','guardian','preview','split','diff'])
  assert.ok(source.includes(`setEditorView('${view}')`) || source.includes(`editorView==='${view}'`),view);
});
