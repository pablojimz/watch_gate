import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Save, UserRound } from 'lucide-react'
import { api, type UserSettings, type UiSettings } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { applyUiTheme } from '@/lib/utils'

function SectionCard({
  title,
  hint,
  children,
}: {
  title: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <Card className="p-5">
      <h2 className="text-base font-semibold">{title}</h2>
      {hint ? <p className="mb-4 text-xs text-muted-foreground">{hint}</p> : null}
      {children}
    </Card>
  )
}

export function UserSettingsPage() {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [settings, setSettings] = useState<UserSettings | null>(null)

  // Form state
  const [displayName, setDisplayName] = useState('')
  const [githubUrl, setGithubUrl] = useState('https://api.github.com')
  const [githubToken, setGithubToken] = useState('')
  const [clearToken, setClearToken] = useState(false)

  // Cambio de contraseña -- formulario aparte (no forma parte del guardado
  // de perfil de arriba): exige la contraseña actual, ver
  // routers/user_settings.py::change_own_password.
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [changingPassword, setChangingPassword] = useState(false)

  // Appearance
  const [primaryColor, setPrimaryColor] = useState('#3b6ea5')
  const [accentColor, setAccentColor] = useState('#5b7c99')
  const [radius, setRadius] = useState<UiSettings['radius']>('md')
  const [fontScale, setFontScale] = useState<UiSettings['font_scale']>('md')
  const [density, setDensity] = useState<UiSettings['density']>('comfortable')
  const [defaultTheme, setDefaultTheme] = useState<UiSettings['default_theme']>('system')

  useEffect(() => {
    let active = true
    void api
      .getUserSettings()
      .then((data) => {
        if (!active) return
        setSettings(data)
        setDisplayName(data.display_name)
        setGithubUrl(data.github_api_url || 'https://api.github.com')
        if (data.ui_settings) {
          setPrimaryColor(data.ui_settings.primary_color || '#3b6ea5')
          setAccentColor(data.ui_settings.accent_color || '#5b7c99')
          setRadius(data.ui_settings.radius || 'md')
          setFontScale(data.ui_settings.font_scale || 'md')
          setDensity(data.ui_settings.density || 'comfortable')
          setDefaultTheme(data.ui_settings.default_theme || 'system')
        }
      })
      .catch((err) => {
        toast.error(err instanceof Error ? err.message : 'Error al cargar perfil')
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [])

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      const ui: UiSettings = {
        primary_color: primaryColor,
        accent_color: accentColor,
        radius,
        font_scale: fontScale,
        density,
        default_theme: defaultTheme,
        logo_data_url: settings?.ui_settings?.logo_data_url || null,
      }

      const updated = await api.putUserSettings({
        display_name: displayName,
        github_api_url: githubUrl,
        github_token: clearToken ? null : githubToken.trim() || null,
        clear_github_token: clearToken,
        ui_settings: ui,
      })

      setSettings(updated)
      setGithubToken('')
      setClearToken(false)
      applyUiTheme(ui)
      toast.success(t('user.saved'))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al guardar')
    } finally {
      setSaving(false)
    }
  }

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault()
    if (newPassword.length < 8) {
      toast.error(t('user.passwordTooShort'))
      return
    }
    if (newPassword !== confirmPassword) {
      toast.error(t('user.passwordMismatch'))
      return
    }
    setChangingPassword(true)
    try {
      await api.changePassword(currentPassword, newPassword)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      toast.success(t('user.passwordChanged'))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al cambiar la contraseña')
    } finally {
      setChangingPassword(false)
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl space-y-6 p-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <div className="flex items-start gap-3">
        <UserRound className="mt-1 size-6 text-primary" strokeWidth={1.75} />
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t('user.pageTitle')}</h1>
          <p className="text-sm text-muted-foreground">{t('user.pageHint')}</p>
        </div>
      </div>

      <form onSubmit={(e) => void handleSave(e)} className="space-y-6">
        <SectionCard title={t('user.profileTitle')}>
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <span className="mb-1 block text-xs text-muted-foreground">{t('user.login')}</span>
              <Input value={settings?.login || ''} disabled className="bg-muted" />
            </div>
            <div>
              <span className="mb-1 block text-xs text-muted-foreground">{t('user.role')}</span>
              <Input value={settings?.role || ''} disabled className="bg-muted" />
            </div>
            <div>
              <span className="mb-1 block text-xs text-muted-foreground">{t('user.displayName')}</span>
              <Input
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Tu nombre"
              />
            </div>
          </div>
        </SectionCard>

        <SectionCard title={t('user.permissionsTitle')} hint={t('user.permissionsHint')}>
          {settings?.repo_roles.length ? (
            <div className="overflow-hidden rounded-lg border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-left text-muted-foreground">
                  <tr>
                    <th className="px-4 py-2 font-medium">{t('user.permissionsRepo')}</th>
                    <th className="px-4 py-2 font-medium">{t('user.permissionsRole')}</th>
                  </tr>
                </thead>
                <tbody>
                  {settings.repo_roles.map((item) => (
                    <tr key={item.repo} className="border-t">
                      <td className="px-4 py-2">{item.repo}</td>
                      <td className="px-4 py-2">{t(`roles.${item.role}`)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{t('user.permissionsEmpty')}</p>
          )}
        </SectionCard>

        <SectionCard
          title={t('user.githubSectionTitle')}
          hint={t('user.githubSectionHint')}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <span className="mb-1 block text-xs text-muted-foreground">{t('user.githubUrl')}</span>
              <Input
                value={githubUrl}
                onChange={(e) => setGithubUrl(e.target.value)}
                placeholder="https://api.github.com"
              />
            </div>
            <div>
              <span className="mb-1 block text-xs text-muted-foreground">{t('user.githubToken')}</span>
              <Input
                type="password"
                autoComplete="off"
                value={githubToken}
                disabled={clearToken}
                onChange={(e) => setGithubToken(e.target.value)}
                placeholder={
                  settings?.github_token_set
                    ? t('user.githubTokenSet', { masked: settings.github_token_masked })
                    : t('user.githubTokenEmpty')
                }
              />
              {settings?.github_token_set ? (
                <label className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={clearToken}
                    onChange={(e) => setClearToken(e.target.checked)}
                  />
                  {t('user.githubClearToken')}
                </label>
              ) : null}
            </div>
          </div>
        </SectionCard>

        <SectionCard title={t('user.appearanceTitle')} hint={t('user.appearanceHint')}>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <div>
              <span className="mb-1 block text-xs text-muted-foreground">Color Primario</span>
              <div className="flex gap-2">
                <input
                  type="color"
                  value={primaryColor}
                  onChange={(e) => setPrimaryColor(e.target.value)}
                  className="size-9 rounded cursor-pointer border"
                />
                <Input value={primaryColor} onChange={(e) => setPrimaryColor(e.target.value)} />
              </div>
            </div>
            <div>
              <span className="mb-1 block text-xs text-muted-foreground">Color Acento</span>
              <div className="flex gap-2">
                <input
                  type="color"
                  value={accentColor}
                  onChange={(e) => setAccentColor(e.target.value)}
                  className="size-9 rounded cursor-pointer border"
                />
                <Input value={accentColor} onChange={(e) => setAccentColor(e.target.value)} />
              </div>
            </div>
            <div>
              <span className="mb-1 block text-xs text-muted-foreground">Tema por Defecto</span>
              <select
                className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                value={defaultTheme}
                onChange={(e) => setDefaultTheme(e.target.value as UiSettings['default_theme'])}
              >
                <option value="system">Sistema</option>
                <option value="light">Claro</option>
                <option value="dark">Oscuro</option>
              </select>
            </div>
            <div>
              <span className="mb-1 block text-xs text-muted-foreground">Radio de Bordes</span>
              <select
                className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                value={radius}
                onChange={(e) => setRadius(e.target.value as UiSettings['radius'])}
              >
                <option value="none">Sin radio</option>
                <option value="sm">Suave</option>
                <option value="md">Medio</option>
                <option value="lg">Redondeado</option>
              </select>
            </div>
            <div>
              <span className="mb-1 block text-xs text-muted-foreground">Tamaño de Fuente</span>
              <select
                className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                value={fontScale}
                onChange={(e) => setFontScale(e.target.value as UiSettings['font_scale'])}
              >
                <option value="sm">Compacto</option>
                <option value="md">Normal</option>
                <option value="lg">Grande</option>
              </select>
            </div>
            <div>
              <span className="mb-1 block text-xs text-muted-foreground">Densidad</span>
              <select
                className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                value={density}
                onChange={(e) => setDensity(e.target.value as UiSettings['density'])}
              >
                <option value="compact">Compacta</option>
                <option value="comfortable">Cómoda</option>
              </select>
            </div>
          </div>
        </SectionCard>

        <div className="flex justify-end">
          <Button type="submit" disabled={saving}>
            <Save className="mr-2 size-4" />
            {saving ? 'Guardando...' : 'Guardar Cambios'}
          </Button>
        </div>
      </form>

      <form onSubmit={(e) => void handleChangePassword(e)}>
        <SectionCard title={t('user.passwordSectionTitle')} hint={t('user.passwordSectionHint')}>
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <span className="mb-1 block text-xs text-muted-foreground">
                {t('user.currentPassword')}
              </span>
              <Input
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
              />
            </div>
            <div>
              <span className="mb-1 block text-xs text-muted-foreground">
                {t('user.newPassword')}
              </span>
              <Input
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            </div>
            <div>
              <span className="mb-1 block text-xs text-muted-foreground">
                {t('user.confirmPassword')}
              </span>
              <Input
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
            </div>
          </div>
          <div className="mt-4 flex justify-end">
            <Button
              type="submit"
              variant="secondary"
              disabled={changingPassword || !currentPassword || !newPassword}
            >
              {changingPassword ? t('user.passwordChanging') : t('user.passwordChangeButton')}
            </Button>
          </div>
        </SectionCard>
      </form>
    </div>
  )
}
