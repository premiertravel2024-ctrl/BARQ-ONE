const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../src');
const read = (p) => fs.readFileSync(path.join(root,p), 'utf8');
const css = read('styles/barqPolish.css');

test('the user and assistant chat text share the same 16px scale', () => {
 assert.match(css,/\.message-row \.chat-markdown\{font-size:16px;line-height:1\.65/);
 assert.match(css,/\.message-row \.barq-assistant-content \.chat-markdown\{[^}]*font-size:16px;line-height:1\.7/);
 assert.match(css,/\.message-row \.barq-user-bubble\{/);
});
test('composer and edit textarea use 16px for RTL, desktop and small screens', () => {
 assert.match(css,/\.barq-composer-surface textarea\{font-size:16px;line-height:1\.5/);
 assert.match(read('components/chat/Composer.tsx'), /id="chatComposer"/);
 assert.match(read('components/chat/Composer.tsx'),/px-4 py-\[11px\] text-base leading-\[1\.5\] text-primary/);
 assert.match(read('components/chat/Message.tsx'), /ui-input min-h-24 resize-y text-base/);
 assert.match(css,/@media\(max-width:680px\)\{\.message-row \.barq-assistant-content \.chat-markdown\{font-size:16px;/);
});
test('mobile overrides keep regular chat text at 16px and respect relative scaling', () => {
 assert.match(css,/@media\(max-width:750px\)\{[\s\S]*?\.message-row \.chat-markdown\{font-size:16px\}/);
 assert.match(css,/\.message-row \.chat-markdown h1\{font-size:21px/);
 assert.match(css,/\.message-row \.chat-markdown h2\{font-size:19px/);
 assert.match(css,/\.message-row \.chat-markdown h3\{font-size:17px/);
});
