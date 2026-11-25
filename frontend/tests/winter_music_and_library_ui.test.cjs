const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');

const page=fs.readFileSync(path.join(__dirname,'../src/pages/MusicPlayer.tsx'),'utf8');
const cards=fs.readFileSync(path.join(__dirname,'../src/pages/libraryCards.css'),'utf8');

test('music player keeps regular imports without the WINTER MUSIC shortcut',()=>{
 const tree=ts.createSourceFile('MusicPlayer.tsx',page,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
 assert.equal(tree.parseDiagnostics.length,0);
 assert.doesNotMatch(page,/bm-winter-import|importWinterMusic/);
 assert.ok(page.includes("importMusic('files')")&&page.includes("importMusic('folder')"));
});

test('book covers fill their entire frame and typography is consistent',()=>{
 assert.match(cards,/object-fit:cover/);
 assert.match(cards,/object-position:center/);
 assert.match(cards,/--bs-book-ink:/);
 assert.match(cards,/--bs-book-secondary:/);
 assert.match(cards,/\.bs-card-meta[\s\S]*?var\(--bs-book-secondary/);
});

test('desktop filters and search are one line, smaller windows wrap',()=>{
 assert.match(cards,/@media\(min-width:901px\)/);
 assert.match(cards,/\.bs-hub \.bs-discovery-row\{[\s\S]*?flex-flow:row nowrap/);
 assert.match(cards,/\.bs-hub \.bs-discovery-row \.bs-search\{[\s\S]*?flex:0 0 clamp/);
 assert.match(cards,/@media\(max-width:900px\)/);
});
