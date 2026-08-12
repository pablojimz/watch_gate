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
              <div className="text-sm text-muted-foreground">
                {t('externalRepos.lastScanned')}:{' '}
                {repo.last_scanned_at 
                  ? new Date(repo.last_scanned_at).toLocaleString() 
                  : t('externalRepos.neverScanned')}
              </div>
              
              {repo.monitor_type === 'audited' && (
                <div className="flex gap-2">
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
