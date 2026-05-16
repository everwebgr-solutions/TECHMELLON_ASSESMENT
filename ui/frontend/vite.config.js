import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: path.resolve(__dirname, '../static'),
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/events': 'http://localhost:8001',
      '/history': 'http://localhost:8001',
      '/status': 'http://localhost:8001',
      '/start': 'http://localhost:8001',
      '/reset': 'http://localhost:8001',
      '/logs': 'http://localhost:8001',
    },
  },
})
