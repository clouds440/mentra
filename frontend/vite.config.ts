import { defineConfig, searchForWorkspaceRoot } from 'vite';
import { realpathSync } from 'node:fs';
import react from '@vitejs/plugin-react';

export default defineConfig({
  cacheDir: '.cache/vite',
  plugins: [react()],
  worker: { format: 'es' },
  optimizeDeps: { exclude: ['prismjs'] },
  server: {
    // Worktrees can share a junctioned dependency directory with the main checkout.
    fs: { allow: [searchForWorkspaceRoot(process.cwd()), realpathSync('node_modules')] },
    host: '0.0.0.0',
    port: 5173,
  },
  preview: {
    host: '0.0.0.0',
    port: 4173,
  },
});
