import { defineConfig } from 'vite'

// The site is published at the root of its own domain (fruitless-sessions.j6n.dev via GitHub
// Pages). `VITE_BASE` overrides it, e.g. VITE_BASE=/fruitless-sessions/ for a project page.
export default defineConfig(({ command }) => ({
  base: command === 'serve' ? '/' : (process.env.VITE_BASE ?? '/'),
  build: { chunkSizeWarningLimit: 900 },
}))
