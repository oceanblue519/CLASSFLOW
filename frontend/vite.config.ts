import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
  base: './',
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        configure(proxy) {
          proxy.on('proxyReq', (proxyRequest, request) => {
            if (request.headers.host) proxyRequest.setHeader('X-Forwarded-Host', request.headers.host);
            proxyRequest.setHeader('X-Forwarded-Proto', request.headers['x-forwarded-proto'] || 'http');
          });
        },
      },
    },
  },
});
