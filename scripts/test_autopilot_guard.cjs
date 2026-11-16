/* Keep BARQ's optional source-only autopilot away from privileged tool calls. */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');
let ts;
try {ts=require(path.resolve(__dirname,'../frontend/node_modules/typescript'))}
catch {ts=require('typescript')}
const input=fs.readFileSync(path.resolve(__dirname,'../frontend/src/lib/approvals.ts'),'utf8');
const code=ts.transpileModule(input,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
const sandboxExports={};
vm.runInNewContext(code,{exports:sandboxExports,require:()=>({})});
const {safeMissionAutopilot: allowed}=sandboxExports;
assert.equal(typeof allowed,'function');
const file='barq-app/main.py';
const scope={autopilot:true,kind:'coding',missionProgress:{files:[{path:file,status:'pending'}]}};
const candidate=(tool,pathArg=file)=>({kind:'execute',task:{...scope,plan:{plan:{steps:[{tool,args:{path:pathArg}}]}}}});
const save=(pathArg=file)=>({kind:'save',task:{...scope,pendingEdit:{approval_id:'abc',path:pathArg}}});
assert(allowed(candidate('workspace_edit')));
assert(allowed(candidate('code_check')));
for (const tool of ['workspace_list','workspace_read','code_search','code_outline','project_map','project_diagnostics','project_plan','git_status','git_diff','git_log']) assert(allowed(candidate(tool)),`Safe read not automated: ${tool}`);
assert(allowed(candidate('project_directory','barq-app/models')));
assert(allowed(save()));
assert(!allowed(candidate('workspace_edit','other-project/main.py')));
assert(!allowed(candidate('project_directory','other-project/.ssh')));
assert(!allowed(save('other-project/main.py')));
for (const tool of ['project_build','run_tests','project_acceptance','project_smoke','prepare_test_environment','mcp_call','rea_analyze','project_bootstrap','prepare_test_environment','code_replace']) {
 assert(!allowed(candidate(tool)),`Unauthorized autopilot: ${tool}`);
}
assert(!allowed({...save(),task:{...scope,autopilot:false}}));
assert(!allowed({kind:'execute',task:{...scope,missionProgress:{files:[]},plan:{plan:{steps:[{tool:'workspace_edit',args:{path:file}}]}}}}));
console.log('BARQ scoped-autopilot guard: reads/planning and tracked-edit checks passed');
