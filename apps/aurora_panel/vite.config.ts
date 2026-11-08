import { fileURLToPath } from 'node:url';

import tailwindcss from '@tailwindcss/vite';
import Vue from '@vitejs/plugin-vue';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [Vue(), tailwindcss()],
  build: {
    rolldownOptions: {
      input: {
        index: fileURLToPath(new URL('index.html', import.meta.url)),
        kun: fileURLToPath(new URL('kun.html', import.meta.url)),
      },
      output: {
        strictExecutionOrder: true,
        codeSplitting: {
          groups: [
            { name: 'vue-vendor', test: /node_modules[\\/](?:@vue[\\/]|vue[\\/]|vue-router[\\/]|pinia[\\/])/ },
            { name: 'naive-ui', test: /node_modules[\\/]naive-ui[\\/]/, maxSize: 300_000 },
          ],
        },
      },
    },
  },
  server: { host: '127.0.0.1', port: 5173, strictPort: true },
  preview: { host: '127.0.0.1', port: 4173, strictPort: true },
});
