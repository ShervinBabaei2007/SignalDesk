import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Dev: `npm run dev` proxies the API to the FastAPI server on :8000.
// Prod: `npm run build` emits frontend/dist, which FastAPI serves at "/".
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  build: { chunkSizeWarningLimit: 900 },
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
})
