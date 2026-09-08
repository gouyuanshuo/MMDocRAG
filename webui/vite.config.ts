import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

// `npm run dev` serves the UI on 3000 and proxies /api to the Python server, so
// the browser sees one origin and no CORS is involved. `npm run build` emits
// dist/, which demo/server.py serves itself -- the demo then needs one command
// and no Node at all.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3000,
    strictPort: false,
    proxy: {
      '/api': {
        target: process.env.MMDOCRAG_API ?? 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 900,
  },
});
