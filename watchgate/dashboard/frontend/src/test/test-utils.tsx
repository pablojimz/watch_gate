import type { ReactElement, ReactNode } from 'react'
import { render, type RenderOptions } from '@testing-library/react'
// Efecto lateral: inicializa la instancia global de i18next (mismo import
// que src/main.tsx hace en la app real) para que useTranslation() no
// reviente por falta de inicialización -- las páginas bajo test usan la
// instancia por defecto directamente, sin <I18nextProvider> explícito, así
// que basta con que este módulo se haya importado antes del render.
import '@/i18n'
import { ThemeProvider } from '@/lib/theme'

// Wrapper compartido para las páginas bajo test: ThemeProvider es el único
// contexto global que estas páginas requieren (App.tsx lo monta en
// main.tsx). No se añade BrowserRouter porque ninguna de las páginas
// cubiertas aquí usa hooks de react-router (useNavigate/useParams/Link) --
// añadirlo sin necesidad solo complicaría las aserciones sin cubrir nada
// real.
function AllProviders({ children }: { children: ReactNode }) {
  return <ThemeProvider>{children}</ThemeProvider>
}

function renderWithProviders(ui: ReactElement, options?: Omit<RenderOptions, 'wrapper'>) {
  return render(ui, { wrapper: AllProviders, ...options })
}

export * from '@testing-library/react'
export { renderWithProviders as render }
