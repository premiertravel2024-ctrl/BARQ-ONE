const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../src');
const composer = fs.readFileSync(path.join(root,'components/chat/Composer.tsx'), 'utf8');
const css = fs.readFileSync(path.join(root,'styles/barqPolish.css'), 'utf8');

test('model and attachments are on the start/right side of RTL input, voice/send remain on the opposite side', () => {
  const surface = composer.indexOf('barq-composer-surface input-halo');
  const controls = composer.indexOf('className="barq-composer-context-tools', surface);
  const textarea = composer.indexOf('id="chatComposer"', surface);
  const actions = composer.indexOf('className="barq-composer-actions', surface);
  assert.ok(surface >= 0 && controls > surface && textarea > controls && actions > textarea);
  assert.match(composer, /dir=\{language==='ar'\?'rtl':'ltr'\}/);
  assert.match(composer, /sm:grid-cols-\[auto_minmax\(0,1fr\)_auto\]/);
  const controlsBlock = composer.slice(controls, textarea);
  assert.match(controlsBlock, /<ModelSelector\s*\/>/);
  assert.match(controlsBlock, /<Paperclip size=\{19\}\/>/);
  assert.equal((composer.match(/<ModelSelector\s*\/>/g)||[]).length, 1);
  assert.equal((composer.match(/ref=\{fileInput\}/g)||[]).length, 1);
  assert.ok(composer.slice(actions).includes('onClick={()=>void send()}'));
});

test('narrow screens keep input usable and put action row below instead of clipping', () => {
  assert.match(composer, /grid-cols-\[auto_minmax\(0,1fr\)\]/);
  assert.match(composer, /barq-composer-toolbar col-span-full/);
  assert.match(composer, /sm:col-span-1/);
  assert.match(css, /\.barq-composer-context-tools\{align-self:center/);
  assert.doesNotMatch(css, /\.barq-composer-toolbar>div:first-child/);
});
