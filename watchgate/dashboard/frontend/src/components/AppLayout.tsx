import {
  BarChart3,
  FolderGit2,
  KeyRound,
  Library,
  LogOut,
  Settings2,
  Shield,
  User,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { ThemeToggle } from '@/components/ThemeToggle'
import { api } from '@/api/client'
import { applyRiskColors, applyUiTheme, cn } from '@/lib/utils'
import { useTheme, type ThemeMode } from '@/lib/theme'

function navLinkClass({ isActive }: { isActive: boolean }) {
  return cn(
    'inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
    isActive
      ? 'bg-primary text-primary-foreground'
      : 'text-muted-foreground hover:bg-accent hover:text-foreground',
  )
}

export function AppLayout({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useTranslation()
  const { setMode } = useTheme()
  const [logoUrl, setLogoUrl] = useState<string | null>(null)

  useEffect(() => {
    void Promise.all([api.getDefaultSettings(), api.getUiSettings()])
      .then(([settings, ui]) => {
        applyRiskColors(settings.risk_colors)
        applyUiTheme(ui)
        setLogoUrl(ui.logo_data_url)
        if (!localStorage.getItem('watchgate-theme') && ui.default_theme) {
          setMode(ui.default_theme as ThemeMode)
        }
      })
      .catch(() => {
        /* defaults CSS */
      })
  }, [setMode])

  async function handleLogout() {
    try {
      await api.logout()
    } catch {
      toast.error('No se pudo cerrar sesión en el servidor')
    } finally {
      window.location.href = '/login'
    }
  }

  return (
    <div className="flex h-screen flex-col bg-background">
      <header className="flex items-center gap-3 border-b px-4 py-3 sm:gap-4 sm:px-6">
        <div className="flex items-center gap-2">
          {logoUrl ? (
            <img src={logoUrl} alt={t('brand')} className="size-8 object-contain" />
          ) : (
            <Shield className="size-5 text-primary" strokeWidth={1.75} />
          )}
          <span className="font-semibold tracking-tight">{t('brand')}</span>
        </div>
        <nav className="flex flex-wrap gap-1">
          <NavLink to="/repos" className={navLinkClass}>
            <FolderGit2 className="size-4" strokeWidth={1.75} />
            <span className="hidden sm:inline">{t('nav.repos')}</span>
          </NavLink>
          <NavLink to="/metrics" className={navLinkClass}>
            <BarChart3 className="size-4" strokeWidth={1.75} />
            <span className="hidden sm:inline">{t('nav.metrics')}</span>
          </NavLink>
          <NavLink to="/rag" className={navLinkClass}>
            <Library className="size-4" strokeWidth={1.75} />
            <span className="hidden sm:inline">{t('nav.rag')}</span>
          </NavLink>
          <NavLink to="/api-keys" className={navLinkClass}>
            <KeyRound className="size-4" strokeWidth={1.75} />
            <span className="hidden sm:inline">{t('nav.apiKeys')}</span>
          </NavLink>
          <NavLink to="/user-settings" className={navLinkClass}>
            <User className="size-4" strokeWidth={1.75} />
            <span className="hidden sm:inline">{t('nav.userSettings')}</span>
          </NavLink>
          {isAdmin ? (
            <NavLink to="/admin" className={navLinkClass}>
              <Settings2 className="size-4" strokeWidth={1.75} />
              <span className="hidden sm:inline">{t('nav.admin')}</span>
            </NavLink>
          ) : null}
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <ThemeToggle />
          <Button
            variant="ghost"
            size="icon"
            onClick={() => void handleLogout()}
            aria-label={t('nav.logout')}
            title={t('nav.logout')}
          >
            <LogOut className="size-4" strokeWidth={1.75} />
          </Button>
        </div>
      </header>
      <main className="min-h-0 flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
