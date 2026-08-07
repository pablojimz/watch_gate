import { useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import {
  KeyRound,
  Palette,
  Scale,
  Trash2,
  Upload,
  Users,
} from 'lucide-react'
import { toast } from 'sonner'
import {
  api,
  type LlmProvider,
  type LlmSettings,
  type RepoRole,
  type RepoSettings,
  type RoleName,
  type Semaforo,
  type UiSettings,
} from '@/api/client'
import { DashboardTabs } from '@/components/dashboard/DashboardTabs'
import { RiskBadge } from '@/components/dashboard/RiskBadge'
import { TableSkeleton } from '@/components/dashboard/TableSkeleton'
import { Button, buttonVariants } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { applyRiskColors, applyUiTheme, cn } from '@/lib/utils'
import { useTheme, type ThemeMode } from '@/lib/theme'

const ROLES: RoleName[] = ['admin_organizacion', 'mantenedor', 'revisor']
const RISK_KEYS: Semaforo[] = ['verde', 'amarillo', 'rojo']
const LLM_PROVIDERS: LlmProvider[] = ['anthropic', 'gemini', 'openai', 'local']
const DEFAULT_MODELS: Record<LlmProvider, string> = {
  anthropic: 'claude-sonnet-5',
  gemini: 'gemini-2.5-flash',
  openai: 'gpt-4.1',
  local: 'llama3.1',
}
const EMPTY_UI: UiSettings = {
  primary_color: '#3b6ea5',
  accent_color: '#5b7c99',
  radius: 'md',
  font_scale: 'md',
  density: 'comfortable',
  default_theme: 'system',
  logo_data_url: null,
}
// Mismo límite que _MAX_LOGO_DATA_URL_LENGTH en schemas.py (400_000
// caracteres de base64 ~= 290 KB reales) -- se valida aquí también para
// dar un error inmediato en vez de esperar al 422 del servidor.
const MAX_LOGO_FILE_BYTES = 280 * 1024
type Tab = 'access' | 'config' | 'appearance' | 'llm'
type ConfigScope = 'default' | 'repo'

const EMPTY_SETTINGS: RepoSettings = {
  weights: { static: 0.25, deps: 0.25, reputation: 0.15, semantic: 0.35 },
  thresholds: { amarillo: 34, rojo: 66 },
  layers_enabled: { static: true, deps: true, reputation: true, semantic: true },
  risk_colors: { verde: '#3d9b5f', amarillo: '#d4a017', rojo: '#c23b3b' },
  block_on_high: true,
  require_feedback_on_high: false,
  source: 'default',
}

function SectionCard({
  title,
  hint,
  children,
  className = '',
}: {
  title: string
  hint?: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className={`rounded-xl border bg-card p-4 sm:p-5 ${className}`}>
      <div className="mb-4">
        <h2 className="text-sm font-semibold">{title}</h2>
        {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
      </div>
      {children}
    </div>
  )
}

function SettingsForm({
  settings,
  onChange,
  onSave,
  onReset,
  saving,
  showReset,
}: {
  settings: RepoSettings
  onChange: (next: RepoSettings) => void
  onSave: () => void
  onReset?: () => void
  saving: boolean
  showReset?: boolean
}) {
  const { t } = useTranslation()
  const colors = { ...EMPTY_SETTINGS.risk_colors, ...settings.risk_colors }

  useEffect(() => {
    applyRiskColors(colors)
  }, [colors.verde, colors.amarillo, colors.rojo])

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 xl:grid-cols-2">
        <SectionCard title={t('admin.weights')} hint={t('admin.weightsHint')}>
          <div className="grid gap-3 sm:grid-cols-2">
            {Object.entries(settings.weights).map(([key, value]) => (
              <label key={key} className="text-sm">
                <span className="mb-1 block text-muted-foreground">
                  {t(`layers.${key}`, { defaultValue: key })}
                </span>
                <Input
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={value}
                  onChange={(e) =>
                    onChange({
                      ...settings,
                      weights: { ...settings.weights, [key]: Number(e.target.value) },
                    })
                  }
                />
              </label>
            ))}
          </div>
        </SectionCard>

        <SectionCard title={t('admin.thresholds')} hint={t('admin.thresholdsHint')}>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-sm">
              <span className="mb-1 block text-muted-foreground">{t('admin.thresholdMedium')}</span>
              <Input
                type="number"
                min="0"
                max="100"
                value={settings.thresholds.amarillo ?? 34}
                onChange={(e) =>
                  onChange({
                    ...settings,
                    thresholds: { ...settings.thresholds, amarillo: Number(e.target.value) },
                  })
                }
              />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-muted-foreground">{t('admin.thresholdHigh')}</span>
              <Input
                type="number"
                min="0"
                max="100"
                value={settings.thresholds.rojo ?? 66}
                onChange={(e) =>
                  onChange({
                    ...settings,
                    thresholds: { ...settings.thresholds, rojo: Number(e.target.value) },
                  })
                }
              />
            </label>
          </div>
        </SectionCard>

        <SectionCard title={t('admin.riskColors')} hint={t('admin.riskColorsHint')}>
          <div className="grid gap-4 sm:grid-cols-3">
            {RISK_KEYS.map((key) => (
              <label key={key} className="flex flex-col gap-2 text-sm">
                <span className="text-muted-foreground">{t(`risk.${key}`)}</span>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    className="h-10 w-12 cursor-pointer rounded border bg-transparent p-1"
                    value={colors[key]}
                    onChange={(e) =>
                      onChange({
                        ...settings,
                        risk_colors: { ...colors, [key]: e.target.value },
                      })
                    }
                  />
                  <Input
                    value={colors[key]}
                    onChange={(e) =>
                      onChange({
                        ...settings,
                        risk_colors: { ...colors, [key]: e.target.value },
                      })
                    }
                  />
                </div>
              </label>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <span className="text-xs text-muted-foreground">{t('admin.preview')}</span>
            {RISK_KEYS.map((key) => (
              <RiskBadge key={key} semaforo={key} className="size-12 text-[10px]" />
            ))}
          </div>
        </SectionCard>

        <SectionCard title={t('admin.layersEnabled')}>
          <div className="grid gap-3 sm:grid-cols-2">
            {Object.entries(settings.layers_enabled).map(([key, enabled]) => (
              <label
                key={key}
                className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm"
              >
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={(e) =>
                    onChange({
                      ...settings,
                      layers_enabled: {
                        ...settings.layers_enabled,
                        [key]: e.target.checked,
                      },
                    })
                  }
                />
                {t(`layers.${key}`, { defaultValue: key })}
              </label>
            ))}
          </div>
        </SectionCard>

        <SectionCard title={t('admin.policy')} className="xl:col-span-2">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex items-center gap-2 rounded-lg border px-3 py-3 text-sm">
              <input
                type="checkbox"
                checked={settings.block_on_high}
                onChange={(e) => onChange({ ...settings, block_on_high: e.target.checked })}
              />
              {t('admin.blockOnHigh')}
            </label>
            <label className="flex items-center gap-2 rounded-lg border px-3 py-3 text-sm">
              <input
                type="checkbox"
                checked={settings.require_feedback_on_high}
                onChange={(e) =>
                  onChange({ ...settings, require_feedback_on_high: e.target.checked })
                }
              />
              {t('admin.requireFeedbackOnHigh')}
            </label>
          </div>
        </SectionCard>
      </div>

      <div className="sticky bottom-0 z-10 -mx-1 flex flex-wrap gap-2 border-t bg-background/95 px-1 py-3 backdrop-blur">
        <Button disabled={saving} onClick={onSave}>
          {t('admin.saveSettings')}
        </Button>
        {showReset && onReset ? (
          <Button variant="outline" disabled={saving} onClick={onReset}>
            {t('admin.resetToDefault')}
          </Button>
        ) : null}
      </div>
    </div>
  )
}

function AppearanceForm({
  settings,
  onSaved,
}: {
  settings: UiSettings
  onSaved: (next: UiSettings) => void
}) {
  const { t } = useTranslation()
  const { setMode } = useTheme()
  const [form, setForm] = useState<UiSettings>(settings)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setForm(settings)
    applyUiTheme(settings)
  }, [settings])

  useEffect(() => {
    applyUiTheme(form)
  }, [form])

  async function save() {
    setSaving(true)
    try {
      const updated = await api.putUiSettings(form)
      onSaved(updated)
      applyUiTheme(updated)
      if (!localStorage.getItem('watchgate-theme')) {
        setMode(updated.default_theme as ThemeMode)
      }
      toast.success(t('admin.appearanceSaved'))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error')
    } finally {
      setSaving(false)
    }
  }

  function handleLogoFile(file: File | undefined) {
    if (!file) return
    if (!file.type.startsWith('image/')) {
      toast.error(t('admin.logoInvalidType'))
      return
    }
    if (file.size > MAX_LOGO_FILE_BYTES) {
      toast.error(t('admin.logoTooLarge'))
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      setForm({ ...form, logo_data_url: reader.result as string })
    }
    reader.onerror = () => toast.error(t('admin.logoReadError'))
    reader.readAsDataURL(file)
  }

  return (
    <div className="flex flex-col gap-4">
      <SectionCard title={t('admin.logoTitle')} hint={t('admin.logoHint')}>
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex size-16 shrink-0 items-center justify-center rounded-md border bg-muted">
            {form.logo_data_url ? (
              <img
                src={form.logo_data_url}
                alt={t('admin.logoPreviewAlt')}
                className="size-full rounded-md object-contain p-1"
              />
            ) : (
              <span className="text-xs text-muted-foreground">{t('admin.logoNone')}</span>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <label>
              <span
                className={cn(
                  buttonVariants({ variant: 'outline', size: 'sm' }),
                  'cursor-pointer',
                )}
              >
                <Upload className="size-4" strokeWidth={1.75} />
                {t('admin.logoUpload')}
              </span>
              <input
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => handleLogoFile(e.target.files?.[0])}
              />
            </label>
            {form.logo_data_url ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setForm({ ...form, logo_data_url: null })}
              >
                <Trash2 className="size-4" strokeWidth={1.75} />
                {t('admin.logoRemove')}
              </Button>
            ) : null}
          </div>
        </div>
      </SectionCard>

      <SectionCard title={t('admin.brandColors')} hint={t('admin.brandColorsHint')}>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-2 text-sm">
            <span className="text-muted-foreground">{t('admin.primaryColor')}</span>
            <div className="flex items-center gap-2">
              <input
                type="color"
                className="h-10 w-12 cursor-pointer rounded border bg-transparent p-1"
                value={form.primary_color}
                onChange={(e) => setForm({ ...form, primary_color: e.target.value })}
              />
              <Input
                value={form.primary_color}
                onChange={(e) => setForm({ ...form, primary_color: e.target.value })}
              />
            </div>
          </label>
          <label className="flex flex-col gap-2 text-sm">
            <span className="text-muted-foreground">{t('admin.accentColor')}</span>
            <div className="flex items-center gap-2">
              <input
                type="color"
                className="h-10 w-12 cursor-pointer rounded border bg-transparent p-1"
                value={form.accent_color}
                onChange={(e) => setForm({ ...form, accent_color: e.target.value })}
              />
              <Input
                value={form.accent_color}
                onChange={(e) => setForm({ ...form, accent_color: e.target.value })}
              />
            </div>
          </label>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button size="sm" type="button" style={{ background: form.primary_color, color: '#fff' }}>
            {t('admin.previewPrimary')}
          </Button>
          <Button size="sm" variant="outline" type="button">
            {t('admin.previewSecondary')}
          </Button>
        </div>
      </SectionCard>

      <SectionCard title={t('admin.layoutDesign')} hint={t('admin.layoutDesignHint')}>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <label className="text-sm">
            <span className="mb-1 block text-muted-foreground">{t('admin.radius')}</span>
            <select
              className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
              value={form.radius}
              onChange={(e) =>
                setForm({ ...form, radius: e.target.value as UiSettings['radius'] })
              }
            >
              {(['none', 'sm', 'md', 'lg'] as const).map((r) => (
                <option key={r} value={r}>
                  {t(`admin.radiusOptions.${r}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-muted-foreground">{t('admin.fontScale')}</span>
            <select
              className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
              value={form.font_scale}
              onChange={(e) =>
                setForm({ ...form, font_scale: e.target.value as UiSettings['font_scale'] })
              }
            >
              {(['sm', 'md', 'lg'] as const).map((r) => (
                <option key={r} value={r}>
                  {t(`admin.fontOptions.${r}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-muted-foreground">{t('admin.density')}</span>
            <select
              className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
              value={form.density}
              onChange={(e) =>
                setForm({ ...form, density: e.target.value as UiSettings['density'] })
              }
            >
              {(['compact', 'comfortable'] as const).map((r) => (
                <option key={r} value={r}>
                  {t(`admin.densityOptions.${r}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-muted-foreground">{t('admin.defaultTheme')}</span>
            <select
              className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
              value={form.default_theme}
              onChange={(e) =>
                setForm({
                  ...form,
                  default_theme: e.target.value as UiSettings['default_theme'],
                })
              }
            >
              {(['light', 'dark', 'system'] as const).map((r) => (
                <option key={r} value={r}>
                  {t(`theme.${r}`)}
                </option>
              ))}
            </select>
          </label>
        </div>
      </SectionCard>

      <div className="sticky bottom-0 z-10 -mx-1 flex flex-wrap gap-2 border-t bg-background/95 px-1 py-3 backdrop-blur">
        <Button disabled={saving} onClick={() => void save()}>
          {t('admin.saveSettings')}
        </Button>
      </div>
    </div>
  )
}

function LlmSettingsForm({
  settings,
  onSaved,
}: {
  settings: LlmSettings
  onSaved: (next: LlmSettings) => void
}) {
  const { t } = useTranslation()
  const [provider, setProvider] = useState<LlmProvider>(settings.provider)
  const [model, setModel] = useState(settings.model)
  const [baseUrl, setBaseUrl] = useState(settings.base_url ?? '')
  const [apiKey, setApiKey] = useState('')
  const [clearKey, setClearKey] = useState(false)
  const [budget, setBudget] = useState(settings.monthly_budget_tokens ?? 2_000_000)
  const [maxDiff, setMaxDiff] = useState(settings.max_diff_tokens ?? 80_000)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setProvider(settings.provider)
    setModel(settings.model)
    setBaseUrl(settings.base_url ?? '')
    setBudget(settings.monthly_budget_tokens ?? 2_000_000)
    setMaxDiff(settings.max_diff_tokens ?? 80_000)
    setApiKey('')
    setClearKey(false)
  }, [settings])

  async function save() {
    setSaving(true)
    try {
      const updated = await api.putLlmSettings({
        provider,
        model,
        base_url: baseUrl.trim() || null,
        api_key: clearKey ? null : apiKey.trim() || null,
        clear_api_key: clearKey,
        monthly_budget_tokens: budget,
        max_diff_tokens: maxDiff,
      })
      onSaved(updated)
      setApiKey('')
      setClearKey(false)
      toast.success(t('admin.llmSaved'))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <SectionCard title={t('admin.llmTitle')} hint={t('admin.llmHint')}>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <label className="text-sm">
            <span className="mb-1 block text-muted-foreground">{t('admin.llmProvider')}</span>
            <select
              className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
              value={provider}
              onChange={(e) => {
                const next = e.target.value as LlmProvider
                setProvider(next)
                setModel(DEFAULT_MODELS[next])
                if (next === 'local' && !baseUrl) setBaseUrl('http://localhost:11434/v1')
                if (next === 'openai' && !baseUrl) setBaseUrl('https://api.openai.com/v1')
              }}
            >
              {LLM_PROVIDERS.map((p) => (
                <option key={p} value={p}>
                  {t(`admin.providers.${p}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-muted-foreground">{t('admin.llmModel')}</span>
            <Input value={model} onChange={(e) => setModel(e.target.value)} />
          </label>
          <label className="text-sm sm:col-span-2 xl:col-span-1">
            <span className="mb-1 block text-muted-foreground">{t('admin.llmBaseUrl')}</span>
            <Input
              placeholder={
                provider === 'local'
                  ? 'http://localhost:11434/v1'
                  : provider === 'openai'
                    ? 'https://api.openai.com/v1'
                    : t('admin.llmBaseUrlOptional')
              }
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
            />
          </label>
          <label className="text-sm sm:col-span-2">
            <span className="mb-1 block text-muted-foreground">{t('admin.llmApiKey')}</span>
            <Input
              type="password"
              autoComplete="off"
              placeholder={
                settings.api_key_set
                  ? t('admin.llmApiKeySet', { masked: settings.api_key_masked })
                  : t('admin.llmApiKeyEmpty')
              }
              value={apiKey}
              disabled={clearKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
            <label className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={clearKey}
                onChange={(e) => setClearKey(e.target.checked)}
              />
              {t('admin.llmClearKey')}
            </label>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-muted-foreground">{t('admin.llmBudget')}</span>
            <Input
              type="number"
              min={0}
              value={budget}
              onChange={(e) => setBudget(Number(e.target.value))}
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-muted-foreground">{t('admin.llmMaxDiff')}</span>
            <Input
              type="number"
              min={0}
              value={maxDiff}
              onChange={(e) => setMaxDiff(Number(e.target.value))}
            />
          </label>
        </div>
        <div className="mt-5">
          <Button disabled={saving} onClick={() => void save()}>
            {t('admin.saveSettings')}
          </Button>
        </div>
      </SectionCard>
    </div>
  )
}

export default function AdminPage() {
  const { t } = useTranslation()
  const [tab, setTab] = useState<Tab>('access')
  const [configScope, setConfigScope] = useState<ConfigScope>('default')
  const [roles, setRoles] = useState<RepoRole[] | null>(null)
  const [repos, setRepos] = useState<string[]>([])
  const [selectedRepo, setSelectedRepo] = useState('')
  const [settings, setSettings] = useState<RepoSettings | null>(null)
  const [llmSettings, setLlmSettings] = useState<LlmSettings | null>(null)
  const [uiSettings, setUiSettings] = useState<UiSettings | null>(null)
  const [saving, setSaving] = useState(false)
  const [userLogin, setUserLogin] = useState('')
  const [repo, setRepo] = useState('acme/payments-api')
  const [role, setRole] = useState<RoleName>('revisor')

  async function reloadRoles() {
    const data = await api.listRoles()
    setRoles(data)
  }

  useEffect(() => {
    void reloadRoles().catch((err: unknown) => {
      toast.error(err instanceof Error ? err.message : 'Error')
      setRoles([])
    })
    void api
      .listRepos()
      .then((list) => {
        setRepos(list)
        if (list.length > 0) setSelectedRepo(list[0])
      })
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'Error')
      })
  }, [])

  useEffect(() => {
    if (tab !== 'config') return
    setSettings(null)
    if (configScope === 'default') {
      void api
        .getDefaultSettings()
        .then(setSettings)
        .catch((err: unknown) => {
          toast.error(err instanceof Error ? err.message : 'Error')
          setSettings(EMPTY_SETTINGS)
        })
      return
    }
    if (!selectedRepo) return
    void api
      .getSettings(selectedRepo)
      .then(setSettings)
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'Error')
        setSettings(null)
      })
  }, [tab, configScope, selectedRepo])

  useEffect(() => {
    if (tab !== 'llm') return
    setLlmSettings(null)
    void api
      .getLlmSettings()
      .then(setLlmSettings)
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'Error')
      })
  }, [tab])

  useEffect(() => {
    if (tab !== 'appearance') return
    setUiSettings(null)
    void api
      .getUiSettings()
      .then(setUiSettings)
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'Error')
        setUiSettings(EMPTY_UI)
      })
  }, [tab])

  async function addRole() {
    // El backend ya normaliza (minúsculas, sin espacios) y por tanto ya
    // impide duplicados de la misma persona con distinta may/min -- esto
    // solo evita una llamada de más si el campo quedó vacío tras recortar.
    const normalizedLogin = userLogin.trim().toLowerCase()
    if (!normalizedLogin) {
      toast.error(t('admin.userRequired'))
      return
    }
    try {
      await api.upsertRole({ user_login: normalizedLogin, repo, role })
      setUserLogin('')
      await reloadRoles()
      toast.success(t('admin.roleSaved'))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error')
    }
  }

  async function removeRole(item: RepoRole) {
    try {
      await api.deleteRole(item.user_login, item.repo)
      await reloadRoles()
      toast.success(t('admin.roleRemoved'))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error')
    }
  }

  async function saveSettings() {
    if (!settings) return
    setSaving(true)
    try {
      const updated =
        configScope === 'default'
          ? await api.putDefaultSettings(settings)
          : await api.putSettings(selectedRepo, settings)
      setSettings(updated)
      if (configScope === 'default') applyRiskColors(updated.risk_colors)
      toast.success(t('admin.settingsSaved'))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error')
    } finally {
      setSaving(false)
    }
  }

  async function resetRepoSettings() {
    if (!selectedRepo) return
    setSaving(true)
    try {
      const updated = await api.resetSettings(selectedRepo)
      setSettings(updated)
      toast.success(t('admin.resetDone'))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error')
    } finally {
      setSaving(false)
    }
  }

  const tabs: { id: Tab; label: string; icon: typeof Users }[] = [
    { id: 'access', label: t('admin.tabAccess'), icon: Users },
    { id: 'config', label: t('admin.tabConfig'), icon: Scale },
    { id: 'appearance', label: t('admin.tabAppearance'), icon: Palette },
    { id: 'llm', label: t('admin.tabLlm'), icon: KeyRound },
  ]

  if (roles === null) {
    return (
      <div className="p-4 sm:px-6 lg:px-8">
        <TableSkeleton rows={6} />
      </div>
    )
  }

  return (
    <div className="flex w-full flex-col gap-4 p-4 sm:px-6 md:flex-row md:gap-6 lg:px-8 lg:py-6">
      <DashboardTabs tabs={tabs} active={tab} onChange={setTab} orientation="vertical" />

      <div className="min-w-0 flex-1">
        {tab === 'access' ? (
          <section className="flex flex-col gap-6">
            <div className="flex items-center gap-2">
              <Users className="size-5 text-primary" strokeWidth={1.75} />
              <h1 className="text-xl font-semibold">{t('admin.title')}</h1>
            </div>

            <div className="grid gap-3 rounded-xl border p-4 sm:grid-cols-2 xl:grid-cols-4">
              <div>
                <Input
                  placeholder={t('admin.user')}
                  value={userLogin}
                  onChange={(e) => setUserLogin(e.target.value)}
                />
                <p className="mt-1 text-xs text-muted-foreground">{t('admin.userHint')}</p>
              </div>
              <Input
                placeholder={t('admin.repo')}
                value={repo}
                onChange={(e) => setRepo(e.target.value)}
              />
              <select
                className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
                value={role}
                onChange={(e) => setRole(e.target.value as RoleName)}
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {t(`roles.${r}`)}
                  </option>
                ))}
              </select>
              <Button onClick={() => void addRole()}>{t('admin.add')}</Button>
            </div>

            <div className="overflow-x-auto rounded-xl border">
              <table className="w-full min-w-[36rem] text-sm">
                <thead className="bg-muted/50 text-left text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-medium">{t('admin.user')}</th>
                    <th className="px-4 py-3 font-medium">{t('admin.repo')}</th>
                    <th className="px-4 py-3 font-medium">{t('admin.role')}</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {roles.map((item) => (
                    <tr key={`${item.user_login}:${item.repo}`} className="border-t">
                      <td className="px-4 py-3">{item.user_login}</td>
                      <td className="px-4 py-3">{item.repo}</td>
                      <td className="px-4 py-3">{t(`roles.${item.role}`)}</td>
                      <td className="px-4 py-3 text-right">
                        <Button size="sm" variant="outline" onClick={() => void removeRole(item)}>
                          {t('admin.remove')}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}

        {tab === 'config' ? (
          <section className="flex flex-col gap-5">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
              <div className="min-w-0">
                <h1 className="text-xl font-semibold">{t('admin.configTitle')}</h1>
                <p className="text-sm text-muted-foreground">{t('admin.configHint')}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant={configScope === 'default' ? 'default' : 'outline'}
                  onClick={() => setConfigScope('default')}
                >
                  {t('admin.scopeDefault')}
                </Button>
                <Button
                  size="sm"
                  variant={configScope === 'repo' ? 'default' : 'outline'}
                  onClick={() => setConfigScope('repo')}
                >
                  {t('admin.scopeRepo')}
                </Button>
              </div>
            </div>

            {configScope === 'repo' ? (
              <div className="flex flex-wrap items-end gap-3 rounded-xl border bg-muted/20 p-4">
                <label className="min-w-[14rem] flex-1 text-sm">
                  <span className="mb-1 block text-muted-foreground">{t('admin.repo')}</span>
                  <select
                    className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                    value={selectedRepo}
                    onChange={(e) => setSelectedRepo(e.target.value)}
                  >
                    {repos.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </label>
                {settings ? (
                  <span className="rounded-md border bg-background px-2 py-1 text-xs text-muted-foreground">
                    {settings.source === 'repo'
                      ? t('admin.sourceCustom')
                      : t('admin.sourceDefault')}
                  </span>
                ) : null}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">{t('admin.defaultHint')}</p>
            )}

            {settings ? (
              <SettingsForm
                settings={settings}
                onChange={setSettings}
                onSave={() => void saveSettings()}
                onReset={() => void resetRepoSettings()}
                saving={saving}
                showReset={configScope === 'repo' && settings.source === 'repo'}
              />
            ) : (
              <TableSkeleton rows={4} />
            )}
          </section>
        ) : null}

        {tab === 'appearance' ? (
          <section className="flex flex-col gap-5">
            <div className="flex items-start gap-2">
              <Palette className="mt-1 size-5 text-primary" strokeWidth={1.75} />
              <div>
                <h1 className="text-xl font-semibold">{t('admin.appearanceTitle')}</h1>
                <p className="text-sm text-muted-foreground">{t('admin.appearanceHint')}</p>
              </div>
            </div>
            {uiSettings ? (
              <AppearanceForm settings={uiSettings} onSaved={setUiSettings} />
            ) : (
              <TableSkeleton rows={4} />
            )}
          </section>
        ) : null}

        {tab === 'llm' ? (
          <section className="flex flex-col gap-5">
            <div className="flex items-start gap-2">
              <KeyRound className="mt-1 size-5 text-primary" strokeWidth={1.75} />
              <div>
                <h1 className="text-xl font-semibold">{t('admin.llmPageTitle')}</h1>
                <p className="text-sm text-muted-foreground">{t('admin.llmPageHint')}</p>
              </div>
            </div>
            {llmSettings ? (
              <LlmSettingsForm settings={llmSettings} onSaved={setLlmSettings} />
            ) : (
              <TableSkeleton rows={4} />
            )}
          </section>
        ) : null}
      </div>
    </div>
  )
}
