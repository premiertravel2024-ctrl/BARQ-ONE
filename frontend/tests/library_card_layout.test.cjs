const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');

const root=path.join(__dirname,'..','src','pages');
const read=(name)=>fs.readFileSync(path.join(root,name),'utf8');

function cardNodes(name){
 const file=ts.createSourceFile(name,read(name),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
 assert.equal(file.parseDiagnostics.length,0, name+' must parse as TSX');
 const cards=[];
 function visit(node){
  if(ts.isJsxElement(node)&&node.openingElement.tagName.getText(file)==='article'){
   const klass=node.openingElement.attributes.properties.find(x=>
    ts.isJsxAttribute(x)&&x.name.getText(file)==='className');
   if(klass&&klass.getText(file).includes('bs-library-card'))cards.push(node);
  }
  ts.forEachChild(node,visit);
 }
 visit(file);
 return {file,cards};
}

test('every catalogue book and series uses a matching accessible action footer',()=>{
 for(const [name,expected] of [['DriveBooks.tsx',2],['BarqStories.tsx',1]]){
  const {file,cards}=cardNodes(name);
  assert.equal(cards.length,expected, name+' must use the one card component');
  for(const card of cards){
   const direct=card.children.filter(child=>ts.isJsxElement(child)||ts.isJsxSelfClosingElement(child));
   const directTags=direct.map(child=>ts.isJsxElement(child)?
    child.openingElement.tagName.getText(file):child.tagName.getText(file));
   assert.ok(directTags.includes('EditableCover'),name+': cover in grid row 1');
   assert.ok(directTags.includes('div'),name+': copy in grid row 1');
   assert.ok(directTags.includes('LibraryCardActions'),name+': footer must be DIRECT child of card');
   assert.equal(directTags.at(-1),'LibraryCardActions',name+': footer must be last');
  }
 }
});

test('actions share one primary and accessible square shortcuts',()=>{
 const source=read('LibraryCardActions.tsx');
 assert.match(source,/className="bs-card-primary"/);
 assert.match(source,/className="bs-card-secondary"/);
 assert.match(source,/aria-label=\{action\.label\}/);
 assert.match(source,/aria-pressed=\{action\.pressed\}/);
 assert.match(source,/secondary\.map\(/);
 const drive=read('DriveBooks.tsx');
 assert.match(drive,/label=\{ar\?'عرض الأعداد':'View issues'\}/);
 assert.match(drive,/label=\{ar\?'اقرأ':'Read'\}/);
 const published=read('BarqStories.tsx');
 assert.match(published,/secondary=\{\[\{/);
 assert.match(published,/pressed:favorites\.includes\(book\.id\)/);
});

test('all library actions remain aligned and responsive in RTL and reduced motion',()=>{
 const component=read('BarqStories.tsx');
 assert.match(component,/import '\.\/libraryCards\.css'/);
 const css=read('libraryCards.css');
 assert.match(css,/grid-template-rows:minmax\(0,1fr\) auto/);
 assert.match(css,/grid-column:1 \/ -1/);
 assert.match(css,/grid-row:2/);
 assert.match(css,/\.bs-card-actions>\.bs-card-primary/);
 assert.match(css,/\.bs-card-actions>\.bs-card-secondary/);
 assert.match(css,/@media\(max-width:430px\)/);
 assert.match(css,/@media\(prefers-reduced-motion:reduce\)/);
 assert.doesNotMatch(css,/!important/);
});
