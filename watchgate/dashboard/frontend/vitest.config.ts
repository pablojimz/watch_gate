import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config.ts'

// Config de test separada de vite.config.ts (en vez de meter el bloque
// `test` ahí) para no forzar a `vite.config.ts` -- que hoy solo importa
// `defineConfig` de 'vite' -- a depender del tipado extendido de
// 'vitest/config'. `mergeConfig` reutiliza igualmente los plugins (React,
// Tailwind) y el alias `@` ya definidos allí, así que los componentes bajo
// test resuelven imports exactamente igual que en dev/build.
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
      css: true,
    },
  }),
)
