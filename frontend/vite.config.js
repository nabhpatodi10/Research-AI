import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3000,
    open: true
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/mermaid')) return 'mermaid';
          if (id.includes('node_modules/echarts') || id.includes('node_modules/echarts-for-react')) return 'charts';
          if (id.includes('node_modules/html2canvas') || id.includes('node_modules/jspdf')) return 'export-tools';
          if (
            id.includes('node_modules/react-markdown') ||
            id.includes('node_modules/remark-') ||
            id.includes('node_modules/rehype-') ||
            id.includes('node_modules/katex') ||
            id.includes('node_modules/github-markdown-css')
          ) {
            return 'markdown-stack';
          }
          return null;
        },
      },
    },
  },
})
