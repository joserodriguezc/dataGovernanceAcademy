import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// En desarrollo, /api va al backend FastAPI (uv run academy, puerto 8000).
export default defineConfig({
  plugins: [react()],
  // App local: la lección (formularios y gráficos) es un único fragmento de ~900 kB.
  build: { chunkSizeWarningLimit: 1000 },
  server: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
