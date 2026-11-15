import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// /api is served by the BFF (web/api), which runs on port 8000 locally.
const proxy = { '/api': 'http://localhost:8000' }

export default defineConfig({
  plugins: [react()],
  server: { proxy },
  preview: { proxy },
})
