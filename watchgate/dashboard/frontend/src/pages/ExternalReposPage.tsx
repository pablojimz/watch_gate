import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
// OJO: nada de iconos de marca (Github, Twitter...) -- lucide-react los
// eliminó (aquí, v1.33): importar uno inexistente rompe el módulo entero y
// deja TODA la app en blanco (esta página se importa estáticamente desde
// App.tsx). Solo iconos genéricos verificados.
import { Eye, Plus, RefreshCw, FolderGit2, GitBranch, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { api, type MonitoredRepoResponse } from '@/api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { TableSkeleton } from '@/components/dashboard/TableSkeleton'

export default function ExternalReposPage() {
  const { t } = useTranslation()
  const [repos, setRepos] = useState<MonitoredRepoResponse[] | null>(null)
  const [appInstallUrl, setAppInstallUrl] = useState<string | null>(null)
  const [showGitServers, setShowGitServers] = useState(false)

  // Form state
  const [newRepoPath, setNewRepoPath] = useState('')
  const [newMonitorType, setNewMonitorType] = useState('audited')
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Scan states
  const [scanPrs, setScanPrs] = useState<Record<string, string>>({})
  const [isScanning, setIsScanning] = useState<Record<string, boolean>>({})
  const [isDeleting, setIsDeleting] = useState<Record<string, boolean>>({})

  // Sondeo tras encolar un escaneo: sin esto, tras el toast de "encolado"
  // el usuario no tenía ninguna señal posterior -- ni de que terminó bien
  // (last_scanned_at/status se actualizan en el backend, pero la lista en
  // memoria del frontend se queda congelada) ni de que falló (el nuevo
  // status="error"/consecutive_errors que ahora sí refleja un fallo del
  // ANÁLISIS -- ver tasks.py -- tampoco se vería sin recargar a mano).
  // refetchTimerRef guarda el intervalo activo para poder cancelarlo si el
  // usuario dispara otro escaneo mientras el anterior aún se está
  // sondeando (evita duplicar intervalos apilados).
  const refetchTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchRepos = useCallback(async () => {
    try {
      const data = await api.listExternalRepos()
      setRepos(data)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error')
      setRepos([])
    }
  }, [])

  useEffect(() => {
    void fetchRepos()
    // Info de la GitHub App (para pintar el botón "Instalar"). Best-effort:
    // si el endpoint falla, la página funciona igual sin ese botón.
    void api
      .getGithubAppInfo()
      .then(info => setAppInstallUrl(info.install_url))
      .catch(() => setAppInstallUrl(null))
    return () => {
      if (refetchTimerRef.current) clearInterval(refetchTimerRef.current)
    }
  }, [fetchRepos])

  // Aterrizaje desde la Setup URL de la GitHub App: tras instalar la App,
  // GitHub redirige el navegador aquí con ?installation_id=...&setup_action=
  // install. Se reclama la instalación para la organización del usuario
  // (crea la VCSConnection y da de alta los repos como "managed") y se
  // limpian los parámetros de la URL para que un F5 no re-reclame.
  const claimedRef = useRef(false)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const installationId = params.get('installation_id')
    if (!installationId || claimedRef.current) return
    claimedRef.current = true
    void (async () => {
      try {
        const result = await api.claimInstallation(installationId)
        if (result.app_configured && result.repos.length > 0) {
          toast.success(t('externalRepos.claimSuccess', { count: result.repos.length }))
        } else {
          toast.success(t('externalRepos.claimSuccessNoRepos'))
        }
        await fetchRepos()
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Error al conectar la instalación')
      } finally {
        params.delete('installation_id')
        params.delete('setup_action')
        const query = params.toString()
        window.history.replaceState(
          null,
          '',
          window.location.pathname + (query ? `?${query}` : ''),
        )
      }
    })()
  }, [fetchRepos, t])

  // Refresca cada 5s durante 1 minuto tras encolar un escaneo -- ventana
  // generosa para escaneos de PRs individuales (típicamente segundos) y
  // para el de rama principal (puede tardar más); pasado ese tiempo se
  // asume que el usuario ya recargará si sigue interesado, en vez de
  // sondear indefinidamente un job que quizá se quedó colgado.
  function pollAfterScan() {
    if (refetchTimerRef.current) clearInterval(refetchTimerRef.current)
    let ticks = 0
    refetchTimerRef.current = setInterval(() => {
      ticks += 1
      void fetchRepos()
      if (ticks >= 12 && refetchTimerRef.current) {
        clearInterval(refetchTimerRef.current)
        refetchTimerRef.current = null
      }
    }, 5000)
  }

  async function handleAddRepo(e: React.FormEvent) {
    e.preventDefault()
    if (!newRepoPath.trim()) return

    setIsSubmitting(true)
    try {
      const added = await api.addExternalRepo(newRepoPath.trim(), newMonitorType)
      toast.success(t('externalRepos.addSuccess'))
      if (added.warning) toast.warning(added.warning)
      setNewRepoPath('')
      await fetchRepos()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al añadir repositorio')
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleScanPr(repoId: string) {
    const prInput = scanPrs[repoId]
    const prNumber = parseInt(prInput, 10)

    if (!prInput || isNaN(prNumber)) {
      toast.error('Número de PR inválido')
      return
    }

    setIsScanning(prev => ({ ...prev, [repoId]: true }))
    try {
      const res = await api.scanExternalRepo(repoId, prNumber)
      toast.success(res.message || t('externalRepos.scanEnqueued'))
      setScanPrs(prev => ({ ...prev, [repoId]: '' }))
      pollAfterScan()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al escanear')
    } finally {
      setIsScanning(prev => ({ ...prev, [repoId]: false }))
    }
  }

  async function handleScanAllOpen(repoId: string) {
    setIsScanning(prev => ({ ...prev, [repoId]: true }))
    try {
      const res = await api.scanExternalRepo(repoId, 0)
      toast.success(res.message || 'Escaneo de todas las PRs abiertas encolado')
      pollAfterScan()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al escanear')
    } finally {
      setIsScanning(prev => ({ ...prev, [repoId]: false }))
    }
  }

  async function handleScanMainBranch(repoId: string) {
    setIsScanning(prev => ({ ...prev, [repoId]: true }))
    try {
      const res = await api.scanMainBranch(repoId)
      toast.success(res.message)
      pollAfterScan()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al escanear la rama principal')
    } finally {
      setIsScanning(prev => ({ ...prev, [repoId]: false }))
    }
  }

  async function handleDeleteRepo(repoId: string, repoPath: string) {
    if (!window.confirm(t('externalRepos.confirmDelete', { repo: repoPath }))) return

    setIsDeleting(prev => ({ ...prev, [repoId]: true }))
    try {
      await api.deleteExternalRepo(repoId)
      toast.success(t('externalRepos.deleteSuccess'))
      setRepos(prev => (prev ? prev.filter(r => r.id !== repoId) : prev))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al eliminar repositorio')
    } finally {
      setIsDeleting(prev => ({ ...prev, [repoId]: false }))
    }
  }

  if (repos === null) {
    return (
      <div className="p-6">
        <TableSkeleton rows={4} />
      </div>
    )
  }

  return (
    <div className="flex w-full flex-col gap-6 p-4 sm:px-6 lg:px-8 lg:py-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <Eye className="mt-0.5 size-6 text-primary" strokeWidth={1.75} />
          <div>
            <h1 className="text-xl font-semibold">{t('externalRepos.title')}</h1>
            <p className="text-sm text-muted-foreground">{t('externalRepos.subtitle')}</p>
          </div>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('externalRepos.connectTitle')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          {/* Vía 1: instalar la GitHub App (modo gestionado, webhooks automáticos) */}
          {appInstallUrl && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-secondary/30 p-4">
              <div className="flex items-start gap-3">
                <GitBranch className="mt-0.5 size-5 text-primary" strokeWidth={1.75} />
                <div>
                  <div className="text-sm font-medium">{t('externalRepos.installAppTitle')}</div>
                  <p className="text-xs text-muted-foreground">
                    {t('externalRepos.installAppSubtitle')}
                  </p>
                </div>
              </div>
              <Button asChild className="gap-2">
                <a href={appInstallUrl} target="_blank" rel="noopener noreferrer">
                  <GitBranch className="size-4" />
                  {t('externalRepos.installAppButton')}
                </a>
              </Button>
            </div>
          )}

          {/* Vía 2: añadir un repo de GitHub por nombre (auditoría sin permisos) */}
          <div className="space-y-1.5">
            <div className="text-sm font-medium">{t('externalRepos.manualAddTitle')}</div>
            <p className="text-xs text-muted-foreground">
              {t('externalRepos.manualAddSubtitle')}
            </p>
          </div>
          <form onSubmit={handleAddRepo} className="flex flex-wrap items-end gap-4">
            <div className="flex-1 min-w-[200px] space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                {t('externalRepos.repoPathLabel')}
              </label>
              <Input
                placeholder={t('externalRepos.repoPathPlaceholder')}
                value={newRepoPath}
                onChange={e => setNewRepoPath(e.target.value)}
                disabled={isSubmitting}
              />
            </div>
            
            <div className="w-[200px] space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                {t('externalRepos.monitorTypeLabel')}
              </label>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                value={newMonitorType}
                onChange={e => setNewMonitorType(e.target.value)}
                disabled={isSubmitting}
              >
                <option value="audited">{t('externalRepos.typeAudited')}</option>
                <option value="managed">{t('externalRepos.typeManaged')}</option>
              </select>
            </div>
            
            <Button type="submit" disabled={!newRepoPath.trim() || isSubmitting} className="gap-2">
              <Plus className="size-4" />
              {t('externalRepos.addRepo')}
            </Button>
          </form>

          {/* Vía 3: servidores Git corporativos (GitLab, Gitea, bare SSH...) --
              la integración real que ya existe para ellos es el hook
              pre-receive del lado servidor (bloquea el push antes del merge)
              y los endpoints de webhook de la Engine API. */}
          <div className="border-t pt-4">
            <button
              type="button"
              className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground"
              onClick={() => setShowGitServers(v => !v)}
            >
              <FolderGit2 className="size-4" strokeWidth={1.75} />
              {t('externalRepos.gitServersTitle')}
              <span className="text-xs">{showGitServers ? '▲' : '▼'}</span>
            </button>
            {showGitServers && (
              <div className="mt-3 space-y-2 rounded-lg border bg-secondary/20 p-4 text-sm text-muted-foreground">
                <p>{t('externalRepos.gitServersIntro')}</p>
                <ul className="list-disc space-y-1 pl-5 text-xs">
                  <li>
                    <span className="font-medium text-foreground">
                      {t('externalRepos.gitServersHookTitle')}
                    </span>{' '}
                    {t('externalRepos.gitServersHookBody')}{' '}
                    <code className="rounded bg-muted px-1 py-0.5">docs/manual_git_hooks.md</code>
                  </li>
                  <li>
                    <span className="font-medium text-foreground">
                      {t('externalRepos.gitServersWebhookTitle')}
                    </span>{' '}
                    {t('externalRepos.gitServersWebhookBody')}{' '}
                    <code className="rounded bg-muted px-1 py-0.5">/api/v1/webhooks/gitlab</code>
                  </li>
                  <li>
                    <span className="font-medium text-foreground">
                      {t('externalRepos.gitServersEnterpriseTitle')}
                    </span>{' '}
                    {t('externalRepos.gitServersEnterpriseBody')}
                  </li>
                </ul>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {repos.map(repo => (
          <Card key={repo.id}>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 font-medium">
                  <FolderGit2 className="size-4 text-muted-foreground" />
                  {repo.repo_path}
                </div>
                <span className="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold bg-secondary/50">
                  {repo.monitor_type === 'audited' 
                    ? t('externalRepos.typeAudited') 
                    : t('externalRepos.typeManaged')}
                </span>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="text-sm space-y-1">
                <div className="text-muted-foreground">
                  {t('externalRepos.lastScanned')}:{' '}
                  {repo.last_scanned_at 
                    ? new Date(repo.last_scanned_at).toLocaleString() 
                    : t('externalRepos.neverScanned')}
                </div>
                {repo.last_polled_at && (
                  <div className="text-xs text-muted-foreground">
                    Último barrido: {new Date(repo.last_polled_at).toLocaleString()}
                  </div>
                )}
                {repo.status === 'error' && (
                  <div className="text-xs text-destructive font-medium">
                    {/* consecutive_errors ya cuenta tanto fallos al listar PRs
                        como fallos del propio análisis (token inválido, PR
                        borrada, fallo de red...) -- ver tasks.py -- así que
                        el texto no debe sugerir que es solo lo primero. */}
                    Repositorio con errores ({repo.consecutive_errors} fallos seguidos)
                  </div>
                )}
              </div>

              <div className="space-y-3 pt-2 border-t">
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full h-8 text-xs gap-1.5"
                    disabled={isScanning[repo.id]}
                    onClick={() => handleScanAllOpen(repo.id)}
                  >
                    <RefreshCw className={`size-3.5 ${isScanning[repo.id] ? 'animate-spin' : ''}`} />
                    Escanear todas las PRs abiertas
                  </Button>

                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full h-8 text-xs gap-1.5"
                    disabled={isScanning[repo.id]}
                    onClick={() => handleScanMainBranch(repo.id)}
                  >
                    <GitBranch className={`size-3.5 ${isScanning[repo.id] ? 'animate-spin' : ''}`} />
                    Escanear rama principal
                  </Button>

                  <div className="flex gap-2 pt-1">
                    <Input
                      placeholder={t('externalRepos.scanPrPlaceholder')}
                      value={scanPrs[repo.id] || ''}
                      onChange={e => setScanPrs(prev => ({ ...prev, [repo.id]: e.target.value }))}
                      className="h-9 text-xs"
                      disabled={isScanning[repo.id]}
                    />
                    <Button
                      variant="secondary"
                      size="sm"
                      className="h-9 text-xs gap-1.5 whitespace-nowrap"
                      disabled={!scanPrs[repo.id] || isScanning[repo.id]}
                      onClick={() => handleScanPr(repo.id)}
                    >
                      Audit PR
                    </Button>
                  </div>

                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-full h-8 text-xs gap-1.5 text-destructive hover:text-destructive hover:bg-destructive/10"
                    disabled={isDeleting[repo.id]}
                    onClick={() => handleDeleteRepo(repo.id, repo.repo_path)}
                  >
                    <Trash2 className="size-3.5" />
                    {t('externalRepos.deleteButton')}
                  </Button>
                </div>
            </CardContent>
          </Card>
        ))}
        {repos.length === 0 && (
          <div className="col-span-full py-8 text-center text-sm text-muted-foreground border rounded-lg border-dashed">
            No hay repositorios externos configurados.
          </div>
        )}
      </div>
    </div>
  )
}
