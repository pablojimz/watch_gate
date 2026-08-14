import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Eye, Plus, RefreshCw, FolderGit2 } from 'lucide-react'
import { toast } from 'sonner'
import { api, type MonitoredRepoResponse } from '@/api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { TableSkeleton } from '@/components/dashboard/TableSkeleton'

export default function ExternalReposPage() {
  const { t } = useTranslation()
  const [repos, setRepos] = useState<MonitoredRepoResponse[] | null>(null)
  
  // Form state
  const [newRepoPath, setNewRepoPath] = useState('')
  const [newMonitorType, setNewMonitorType] = useState('audited')
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Scan states
  const [scanPrs, setScanPrs] = useState<Record<string, string>>({})
  const [isScanning, setIsScanning] = useState<Record<string, boolean>>({})

  useEffect(() => {
    void fetchRepos()
  }, [])

  async function fetchRepos() {
    try {
      const data = await api.listExternalRepos()
      setRepos(data)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error')
      setRepos([])
    }
  }

  async function handleAddRepo(e: React.FormEvent) {
    e.preventDefault()
    if (!newRepoPath.trim()) return

    setIsSubmitting(true)
    try {
      await api.addExternalRepo(newRepoPath.trim(), newMonitorType)
      toast.success(t('externalRepos.addSuccess'))
      setNewRepoPath('')
      await fetchRepos()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al añadir repositorio')
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleUpdateRepo(
    repoId: string,
    data: { auto_scan_prs?: boolean; scan_interval_minutes?: number; status?: string }
  ) {
    try {
      const updated = await api.updateExternalRepo(repoId, data)
      toast.success('Configuración actualizada')
      setRepos(prev => (prev ? prev.map(r => (r.id === repoId ? updated : r)) : null))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al actualizar')
    }
  }

  async function handleScan(repoId: string) {
    const prInput = scanPrs[repoId]
    const prNumber = parseInt(prInput, 10)
    
    if (!prInput || isNaN(prNumber)) {
      toast.error('Número de PR inválido')
      return
    }

    setIsScanning(prev => ({ ...prev, [repoId]: true }))
    try {
      await api.scanExternalRepo(repoId, prNumber)
      toast.success(t('externalRepos.scanEnqueued'))
      setScanPrs(prev => ({ ...prev, [repoId]: '' }))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al escanear')
    } finally {
      setIsScanning(prev => ({ ...prev, [repoId]: false }))
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
          <CardTitle className="text-base">{t('externalRepos.addRepo')}</CardTitle>
        </CardHeader>
        <CardContent>
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
                    Error en peticiones ({repo.consecutive_errors} fallos)
                  </div>
                )}
              </div>

              {repo.monitor_type === 'audited' && (
                <div className="space-y-3 pt-2 border-t">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium">Auto Escaneo PRs:</span>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={repo.auto_scan_prs}
                        onChange={e => handleUpdateRepo(repo.id, { auto_scan_prs: e.target.checked })}
                        className="sr-only peer"
                      />
                      <div className="w-9 h-5 bg-muted peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary"></div>
                    </label>
                  </div>

                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium">Intervalo:</span>
                    <select
                      className="h-8 rounded border border-input bg-transparent px-2 text-xs"
                      value={repo.scan_interval_minutes}
                      onChange={e => handleUpdateRepo(repo.id, { scan_interval_minutes: parseInt(e.target.value, 10) })}
                    >
                      <option value={15}>15 minutos</option>
                      <option value={30}>30 minutos</option>
                      <option value={60}>1 hora</option>
                      <option value={120}>2 horas</option>
                      <option value={1440}>24 horas</option>
                    </select>
                  </div>

                  <div className="flex gap-2 pt-1">
                    <Input
                      placeholder={t('externalRepos.scanPrPlaceholder')}
                      value={scanPrs[repo.id] || ''}
                      onChange={e => setScanPrs(prev => ({ ...prev, [repo.id]: e.target.value }))}
                      className="h-9"
                      disabled={isScanning[repo.id]}
                    />
                    <Button 
                      variant="secondary" 
                      size="sm" 
                      className="h-9 gap-1.5"
                      disabled={!scanPrs[repo.id] || isScanning[repo.id]}
                      onClick={() => handleScan(repo.id)}
                    >
                      <RefreshCw className={`size-3.5 ${isScanning[repo.id] ? 'animate-spin' : ''}`} />
                      {t('externalRepos.scanButton')}
                    </Button>
                  </div>
                </div>
              )}
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
