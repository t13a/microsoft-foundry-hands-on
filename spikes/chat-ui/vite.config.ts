import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// /api stands in for the BFF: it relays to the local hosted agent unchanged.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': { target: 'http://localhost:8088', rewrite: (path) => path.replace(/^\/api/, '') } } },
  preview: { proxy: { '/api': { target: 'http://localhost:8088', rewrite: (path) => path.replace(/^\/api/, '') } } },
})
