import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    port: 5173,
    watch: {
      // Docker Desktop sobre Windows no propaga eventos inotify nativos a
      // través del bind mount (ruta del host en C:\...) hacia el
      // contenedor -- el watcher de Vite se queda esperando eventos que
      // nunca llegan y el HMR no dispara nunca, aunque el proceso siga
      // "corriendo" sin error. Verificado en vivo: sin esto, editar un
      // fichero no produce ningún log de recompilación. Con polling
      // activo, Vite sondea el sistema de ficheros en vez de depender de
      // esos eventos -- gateado por variable de entorno (activada solo en
      // docker-compose.override.yml) para no gastar CPU de más en
      // desarrollo normal fuera de Docker, donde los eventos nativos sí
      // funcionan.
      //
      // `interval`: sin especificarlo, chokidar sondea cada 100ms por
      // defecto -- 10 veces por segundo, cada una cruzando la frontera
      // Windows/WSL2 del bind mount (más cara que un stat() nativo).
      // Medido en vivo: eso por sí solo sostenía ~70% de CPU en el proceso
      // de Vite sin que nadie tocara ni un fichero. 1000ms sigue dando
      // recarga casi inmediata para un humano guardando código, con una
      // décima parte de las comprobaciones.
      usePolling: process.env.VITE_USE_POLLING === '1',
      interval: process.env.VITE_USE_POLLING === '1' ? 1000 : undefined,
    },
    proxy: {
      // Prefijo /api/ (CON la barra) para no chocar con rutas SPA que
      // empiezan por las mismas letras -- '/api' a secas hacía match por
      // simple prefijo (Vite: `url.startsWith(key)`), así que /api-keys
      // (ruta real de la SPA, ver App.tsx) también caía aquí: navegar
      // directo a esa URL (o recargar estando en ella) devolvía el 404
      // JSON del backend en vez de la página. Reproducido en vivo.
      '/api/': {
        // Configurable para poder apuntar al servicio de Docker
        // (`dashboard-backend`) en vez de `127.0.0.1` cuando Vite corre
        // DENTRO de un contenedor -- ahí `127.0.0.1` es el propio
        // contenedor, no el del backend. Ver docker-compose.override.yml.
        // Sin la variable (desarrollo normal fuera de Docker, front y back
        // ambos en localhost), el comportamiento es exactamente el mismo
        // de siempre.
        target: process.env.VITE_BACKEND_PROXY_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
