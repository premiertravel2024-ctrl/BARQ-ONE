const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../src/components/layout/VoiceSettings.tsx'), 'utf8');

test('the hands-free voice button does not return dispatchEvent boolean to React', () => {
  assert.doesNotMatch(source, /onClick\s*=\s*\{\s*\(\s*\)\s*=>\s*window\.dispatchEvent\s*\(/);
  assert.match(source, /onClick\s*=\s*\{\s*\(\s*\)\s*=>\s*\{\s*window\.dispatchEvent\s*\(/);
});

test('both hands-free events remain available with the computer consent setting', () => {
  assert.match(source, /barq-handsfree-stop/);
  assert.match(source, /barq-handsfree-start/);
  assert.match(source, /computerEnabled:allowComputerInConversation&&pcPolicyEnabled/);
});
