import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

// Общие страницы и компоненты сайтов (формы Log, Гости, Параметры сервисов) — web/shared_web/frontend, копия
// parlaments/shared_web (см. shared_web/README.md). Они импортируют модули сайта через '@app/...', а npm-пакеты
// берутся из node_modules этого проекта (resolve.dedupe): у shared_web своего node_modules нет.
const SHARED_WEB = fileURLToPath(new URL('../shared_web/frontend', import.meta.url))
const APP_SRC = fileURLToPath(new URL('./src', import.meta.url))

// SPA раздаётся Flask'ом из корня сайта (см. api_v2.py), поэтому base = '/'.
// В dev-режиме (npm run dev) API и статика проксируются на локальный Flask (start_ohi_web.py, PORT=8082).
export default defineConfig({
  base: '/',
  plugins: [react()],
  resolve: {
    alias: { '@app': APP_SRC, '@shared-web': SHARED_WEB },
    dedupe: ['react', 'react-dom', 'react-router-dom', '@mui/material', '@mui/icons-material', '@emotion/react',
      '@emotion/styled', 'chart.js', 'react-chartjs-2'],
  },
  server: {
    port: 5175,
    fs: { allow: ['.', SHARED_WEB] },
    proxy: {
      '/api': 'http://127.0.0.1:8082',
      '/static': 'http://127.0.0.1:8082',
      '/one_new': 'http://127.0.0.1:8082',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
