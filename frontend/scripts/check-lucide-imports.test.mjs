import test from 'node:test';
import assert from 'node:assert/strict';
import {parseLucideImports,missingExports} from './check-lucide-imports.mjs';

test('parses multiline lucide imports, aliases, and types without local identifiers',()=>{
 assert.deepEqual(parseLucideImports("import {Monitor,\n Tablet as Device,\n RefreshCcw} from 'lucide-react';"),['Monitor','Tablet','RefreshCcw']);
});
test('fails on unsupported icon name rather than allowing a later Windows build failure',()=>{
 const source="import {TabletSmart,Tablet} from 'lucide-react'";
 assert.deepEqual(missingExports(parseLucideImports(source),['Tablet']),['TabletSmart']);
});
test('does not report duplicate missing exports repeatedly',()=>{
 assert.deepEqual(missingExports(['A','B','A'],['B']),['A']);
});
