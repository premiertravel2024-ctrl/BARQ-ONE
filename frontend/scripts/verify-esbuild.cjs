// Test the locally locked esbuild package and the native binary for this host.
// Runs only during an explicit Windows build; does not contact any cloud service.
const esbuild = require('esbuild');
const result = esbuild.transformSync('const answer: number = 42', {loader: 'ts'});
if (!result.code.includes('answer = 42')) {
  throw new Error('esbuild transform returned unexpected output');
}
console.log(`esbuild ${esbuild.version}: native executable OK`);
