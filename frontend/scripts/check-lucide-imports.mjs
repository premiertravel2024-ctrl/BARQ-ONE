/** BARQ frontend dependency gate: catch unsupported lucide icons before tsc / packaging.
 * This checks the exact installed lucide-react version, not a hardcoded icon list.
 */
import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendRoot=path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const sourceDir=path.join(frontendRoot,'src');

export function parseLucideImports(source){
 const found=[];
 const pattern=/\bimport\s*\{([^}]+)\}\s*from\s*['"]lucide-react['"]/g;
 for(const match of source.matchAll(pattern)){
  for(const entry of match[1].split(',')){
   const name=entry.trim().replace(/^type\s+/, '').split(/\s+as\s+/)[0].trim();
   if(name) found.push(name);
  }
 }
 return found;
}

async function sourceFiles(root){
 const entries=await readdir(root,{withFileTypes:true});
 let paths=[];
 for(const entry of entries){
  const full=path.join(root,entry.name);
  if(entry.isDirectory()) paths.push(...await sourceFiles(full));
  else if(entry.isFile() && /\.(tsx?|jsx?)$/.test(entry.name)) paths.push(full);
 }
 return paths;
}

export function missingExports(imports, actualExports){
 const available=new Set(actualExports);
 return [...new Set(imports)].filter(name=>!available.has(name));
}

async function main(){
 let icons;
 try{ icons=await import('lucide-react'); }
 catch(error){
  console.error('[BARQ dependency check] Cannot import installed lucide-react. Run npm ci first.');
  console.error(String(error));process.exitCode=2;return;
 }
 let count=0;const bad=[];
 for(const full of await sourceFiles(sourceDir)){
  const uses=parseLucideImports(await readFile(full,'utf8'));
  count+=uses.length;
  const missing=missingExports(uses,Object.keys(icons));
  if(missing.length) bad.push({file:path.relative(frontendRoot,full),missing});
 }
 if(bad.length){
  console.error(`[BARQ] Found unsupported lucide-react imports (exact installed version):`);
  for(const {file,missing} of bad) console.error(`  ${file}: ${missing.join(', ')}`);
  console.error('Fix imports and rerun npm run verify:icons BEFORE building Windows EXE.');
  process.exitCode=1;return;
 }
 console.log(`[BARQ] Verified ${count} lucide-react named imports against installed package.`);
}
if(process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) await main();
