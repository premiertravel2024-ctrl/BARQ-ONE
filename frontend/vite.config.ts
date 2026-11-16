import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
  plugins: [react()],
  base: '/',
  build: { outDir: '../web/react', emptyOutDir: true },
  server: { port: 5173, proxy: { '/v1': { target: 'http://127.0.0.1:8000', ws: true }, '/health': 'http://127.0.0.1:8000' } }
});
