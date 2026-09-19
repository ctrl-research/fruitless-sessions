import { defineConfig } from 'vite'

// The site is published under a path (GitHub Pages serves a project site at /<repo>/).
// `VITE_BASE` overrides it; the dev server always runs at /.
export default defineConfig(({ command }) => ({
  base: command === 'serve' ? '/' : (process.env.VITE_BASE ?? '/fruitless-sessions/'),
  build: { chunkSizeWarningLimit: 900 },
}))
