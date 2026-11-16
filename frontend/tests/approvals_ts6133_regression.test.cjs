const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../src/lib/approvals.ts'), 'utf8');

test('safeMissionAutopilot does not declare unused args in the read-only branch', () => {
  const readOnlyBranch = source.split("if(candidate.kind==='execute'){", 2)[1]?.split('const files=', 1)[0];
  assert.ok(readOnlyBranch, 'read-only execution branch should still exist');
  assert.match(readOnlyBranch, /const\s*\{\s*tool\s*\}\s*=\s*steps\[0\]/);
  assert.doesNotMatch(readOnlyBranch, /const\s*\{\s*tool\s*,\s*args\s*\}/);
});

test('write branch still reads tool arguments when it validates file paths', () => {
  assert.match(source, /const\s*\{\s*tool\s*,\s*args\s*\}\s*=\s*steps\[0\]/);
  assert.match(source, /typeof\s+args\.path\s*===\s*'string'/);
});
