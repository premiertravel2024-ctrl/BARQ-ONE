import { defineConfig, type Plugin } from 'vite';
import {readdirSync, readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {dirname,join} from 'node:path';
import react from '@vitejs/plugin-react';
function pdfResources(): Plugin {
  const root=dirname(createRequire(import.meta.url).resolve('pdfjs-dist/package.json'));
  const files=new Map<string,string>();
  for(const folder of ['cmaps','standard_fonts','wasm','iccs']){
    for(const filename of readdirSync(join(root,folder),{withFileTypes:true})){
      if(filename.isFile())files.set('assets/pdfjs/'+folder+'/'+filename.name,join(root,folder,filename.name));
    }
  }
  return {
    name:'barq-pdf-resources',
    configureServer(server){
      server.middlewares.use((req,res,next)=>{
        const path=files.get(req.url?.slice(1).split('?')[0]||'');
        if(!path)return next();
        res.setHeader('Content-Type',path.endsWith('.wasm')?'application/wasm':'application/octet-stream');
        res.end(readFileSync(path));
      });
    },
    generateBundle(){
      for(const [fileName,path] of files)this.emitFile({type:'asset',fileName,source:readFileSync(path)});
    },
  };
}
export default defineConfig({
  plugins: [react(), pdfResources()],
  base: '/',
  build: { outDir: '../web/react', emptyOutDir: true },
  server: { port: 5173, proxy: { '/v1': 'http://127.0.0.1:8000', '/health': 'http://127.0.0.1:8000' } }
});
