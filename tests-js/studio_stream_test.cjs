/** Uses the project's installed TypeScript, not a machine-specific global path. */
const path=require('node:path');
const fs=require('node:fs');const vm=require('node:vm');const assert=require('node:assert/strict');
const projectRoot=path.resolve(__dirname,'..');
function loadTypeScript() {
 const candidates=[
  process.env.TYPESCRIPT_MODULE,
  path.join(projectRoot,'frontend','node_modules','typescript'),
  'typescript',
  process.env.NODE_PATH && path.join(process.env.NODE_PATH,'typescript'),
 ];
 for(const candidate of candidates){
  if(!candidate) continue;
  try{return require(candidate)}catch(error){if(error.code!=='MODULE_NOT_FOUND')throw error}
 }
 throw new Error('TypeScript is missing. Run npm ci in the frontend folder before running this test.');
}
const ts=loadTypeScript();
const source=fs.readFileSync(path.join(projectRoot,'frontend','src','lib','studioStream.ts'),'utf8');
const js=ts.transpileModule(source,{fileName:'studioStream.ts',compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const exported={};
vm.runInNewContext(js,{exports:exported,require(name){if(name==='./backend')return {APIError:Error};throw Error(name)},TextDecoder,AbortController,JSON,fetch:undefined});
const blocks=exported.generatedBlocks('ابدأ\n```python src/app.py\nprint(1)\n```\nثم\n```tsx src/App.tsx\nexport default function App() {\n');
assert.equal(blocks.length,2);assert.equal(blocks[0].filename,'src/app.py');assert.equal(blocks[0].content,'print(1)\n');assert.equal(blocks[0].complete,true);
assert.equal(blocks[1].filename,'src/App.tsx');assert.equal(blocks[1].complete,false);
assert.equal(exported.generatedBlocks('no fenced code').length,0);
console.log('Live studio parser tests: PASS');
