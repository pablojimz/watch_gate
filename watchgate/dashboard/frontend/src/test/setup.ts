// Entrypoint específico de vitest (no el genérico
// '@testing-library/jest-dom'): engancha los matchers directamente sobre
// el `expect` de vitest en vez de asumir un `expect` global estilo Jest --
// con `globals: true` en vitest.config.ts ambos acaban siendo el mismo
// objeto, pero este import es el soportado explícitamente para vitest.
import '@testing-library/jest-dom/vitest'

// jsdom no implementa matchMedia -- ThemeProvider (src/lib/theme.tsx) lo
// llama de forma síncrona en su primer render (resolveMode) para resolver
// el modo 'system', así que cualquier página envuelta en ThemeProvider
// (ver src/test/test-utils.tsx) revienta sin este polyfill mínimo, incluso
// en tests que no tocan el tema para nada.
if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }) as unknown as MediaQueryList
}
