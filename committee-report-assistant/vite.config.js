import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { viteSingleFile } from 'vite-plugin-singlefile';

// `npm run dev` for development, `npm run build` creates one self-contained dist/index.html
export default defineConfig({
  plugins: [react(), viteSingleFile()],
  base: './',
});
