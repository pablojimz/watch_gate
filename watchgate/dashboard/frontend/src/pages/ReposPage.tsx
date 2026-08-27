import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowRight, FolderGit2, Layers, Plus, Search, ShieldCheck, Eye, Trash2, X } from 'lucide-react'
import { toast } from 'sonner'
import { api, type ScoreOut, type Semaforo } from '@/api/client'
import { RiskBadge } from '@/components/dashboard/RiskBadge'
import { TableSkeleton } from '@/components/dashboard/TableSkeleton'
import { ConnectRepoDialog } from '@/components/dashboard/ConnectRepoDialog'
import { DashboardTabs } from '@/components/dashboard/DashboardTabs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button, buttonVariants } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

// Origen de un repo en la vista unificada:
//  - 'own': repo propio -- analizado por la Action/CI o conectado vía
//    GitHub App (monitor_type 'managed'). Es "tu" código.
//  - 'audited': repo de terceros dado de alta en auditoría externa
//    (monitor_type 'audited'), sin permisos de escritura.
type RepoSource = 'own' | 'audited'

interface RepoSummary {
  repo: string
  scores: ScoreOut[]
  latest: ScoreOut | null
  avg: number
  red: number
  medium: number
  pending: number
  latestSemaforo: Semaforo | null
  source: RepoSource
}

type RiskFilter = 'all' | Semaforo
type SourceFilter = 'all' | RepoSource
type SortKey = 'name' | 'risk' | 'avg' | 'prs' | 'recent'

const RISK_ORDER: Record<Semaforo, number> = { rojo: 0, amarillo: 1, verde: 2 }

export default function ReposPage() {
  const { t } = useTranslation()
  const [summaries, setSummaries] = useState<RepoSummary[] | null>(null)
  const [connectOpen, setConnectOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [riskFilter, setRiskFilter] = useState<RiskFilter>('all')
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all')
  const [onlyPending, setOnlyPending] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('name')

  const loadSummaries = useCallback(async () => {
    try {
      // Dos fuentes distintas, unificadas en esta vista:
      //  - listRepos: repos que ya tienen resultados (scores/roles/settings).
      //  - listExternalRepos: repos CONECTADOS (tabla MonitoredRepo), tengan
      //    o no análisis todavía, con su monitor_type (managed/audited).
      // Un repo recién conectado sale aquí de inmediato aunque aún no se haya
      // escaneado -- antes solo era visible en la página de Auditoría Externa.
      const [scoredRepos, externalRepos] = await Promise.all([
        api.listRepos(),
        api.listExternalRepos().catch(() => []),
      ])

      // monitor_type por repo_path (audited => origen "auditoría externa").
      const monitorTypeByRepo = new Map(
        externalRepos.map((r) => [r.repo_path, r.monitor_type]),
      )
      const allRepoPaths = Array.from(
        new Set([...scoredRepos, ...externalRepos.map((r) => r.repo_path)]),
      )

      const rows = await Promise.all(
        allRepoPaths.map(async (repo) => {
          // Un repo externo recién conectado puede no tener rol/scores aún:
          // listScores daría 403 -- se trata como "sin análisis todavía".
          const scores = await api.listScores(repo).catch(() => [] as ScoreOut[])
          const avg =
            scores.length === 0
              ? 0
              : Math.round(scores.reduce((acc, s) => acc + s.score, 0) / scores.length)
          const latest =
            scores.length === 0
              ? null
              : [...scores].sort((a, b) => b.timestamp.localeCompare(a.timestamp))[0]
          const source: RepoSource =
            monitorTypeByRepo.get(repo) === 'audited' ? 'audited' : 'own'
          return {
            repo,
            scores,
            latest,
            avg,
            red: scores.filter((s) => s.semaforo === 'rojo').length,
            medium: scores.filter((s) => s.semaforo === 'amarillo').length,
            pending: scores.filter((s) => s.human_feedback === null).length,
            latestSemaforo: latest?.semaforo ?? null,
            source,
          }
        }),
      )
      setSummaries(rows)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error')
      setSummaries([])
    }
  }, [])

  useEffect(() => {
    void loadSummaries()
  }, [loadSummaries])

  // Aterrizaje desde la Setup URL de la GitHub App: tras instalar la App,
  // GitHub redirige aquí con ?installation_id=...&setup_action=install. Se
  // reclama la instalación para la organización del usuario (crea la
  // VCSConnection y da de alta los repos como "managed") y se limpia la URL
  // para que un F5 no re-reclame.
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
        await loadSummaries()
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
  }, [loadSummaries, t])

  const filtered = useMemo(() => {
    if (!summaries) return []
    const q = query.trim().toLowerCase()
    const rows = summaries.filter((item) => {
      if (q && !item.repo.toLowerCase().includes(q)) return false
      if (riskFilter !== 'all' && item.latestSemaforo !== riskFilter) return false
      if (sourceFilter !== 'all' && item.source !== sourceFilter) return false
      if (onlyPending && item.pending === 0) return false
      return true
    })

    return [...rows].sort((a, b) => {
      if (sortKey === 'name') return a.repo.localeCompare(b.repo)
      if (sortKey === 'avg') return b.avg - a.avg
      if (sortKey === 'prs') return b.scores.length - a.scores.length
      if (sortKey === 'recent') {
        const at = a.latest?.timestamp ?? ''
        const bt = b.latest?.timestamp ?? ''
        return bt.localeCompare(at)
      }
      const ar = a.latestSemaforo ? RISK_ORDER[a.latestSemaforo] : 3
      const br = b.latestSemaforo ? RISK_ORDER[b.latestSemaforo] : 3
      return ar - br || a.repo.localeCompare(b.repo)
    })
  }, [summaries, query, riskFilter, sourceFilter, onlyPending, sortKey])

  const hasActiveFilters =
    query.trim() !== '' ||
    riskFilter !== 'all' ||
    sourceFilter !== 'all' ||
    onlyPending ||
    sortKey !== 'name'

  async function handleDelete(repoPath: string) {
    if (!window.confirm(t('repos.confirmDelete', { repo: repoPath }))) return
    try {
      await api.deleteRepo(repoPath)
      toast.success(t('repos.deleteSuccess'))
      await loadSummaries()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error')
    }
  }

  function clearFilters() {
    setQuery('')
    setRiskFilter('all')
    setSourceFilter('all')
    setOnlyPending(false)
    setSortKey('name')
  }

  if (summaries === null) {
    return (
      <div className="p-6">
        <TableSkeleton rows={4} />
      </div>
    )
  }

  const riskFilters: { id: RiskFilter; label: string }[] = [
    { id: 'all', label: t('repos.filterAll') },
    { id: 'rojo', label: t('risk.rojo') },
    { id: 'amarillo', label: t('risk.amarillo') },
    { id: 'verde', label: t('risk.verde') },
  ]

  // Desplegable de origen a la izquierda (mismas tabs verticales que la
  // página de Configuración): todos / propios / auditoría externa.
  const sourceTabs = [
    { id: 'all' as const, label: t('repos.sourceAll'), icon: Layers },
    { id: 'own' as const, label: t('repos.sourceOwn'), icon: ShieldCheck },
    { id: 'audited' as const, label: t('repos.sourceAudited'), icon: Eye },
  ]

  return (
    <div className="flex w-full flex-col gap-6 p-4 sm:px-6 lg:px-8 lg:py-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <FolderGit2 className="mt-0.5 size-6 text-primary" strokeWidth={1.75} />
          <div>
            <h1 className="text-xl font-semibold">{t('repos.title')}</h1>
            <p className="text-sm text-muted-foreground">{t('repos.subtitle')}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {summaries.length > 0 ? (
            <p className="text-sm text-muted-foreground">
              {t('repos.showing', { shown: filtered.length, total: summaries.length })}
            </p>
          ) : null}
          {/* Conectar un repositorio (propio o de auditoría externa): abre el
              diálogo aquí mismo, sin sacar al usuario de la página. */}
          <Button size="sm" className="gap-2" onClick={() => setConnectOpen(true)}>
            <Plus className="size-4" />
            {t('repos.connectRepo')}
          </Button>
        </div>
      </div>

      {summaries.length === 0 ? (
        <div className="flex flex-col items-start gap-3">
          <p className="text-sm text-muted-foreground">{t('repos.empty')}</p>
          <Button className="gap-2" onClick={() => setConnectOpen(true)}>
            <Plus className="size-4" />
            {t('repos.connectRepo')}
          </Button>
        </div>
      ) : (
        <div className="flex w-full flex-col gap-4 md:flex-row md:gap-6">
          <DashboardTabs
            tabs={sourceTabs}
            active={sourceFilter}
            onChange={setSourceFilter}
            orientation="vertical"
          />
          <div className="flex min-w-0 flex-1 flex-col gap-4">
          <div className="flex flex-col gap-3 rounded-xl border bg-card p-4">
            <div className="relative min-w-0 flex-1">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                strokeWidth={1.75}
              />
              <Input
                className="pl-9"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t('repos.searchPlaceholder')}
                aria-label={t('repos.searchPlaceholder')}
              />
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium text-muted-foreground">
                {t('repos.filterRisk')}
              </span>
              {riskFilters.map((f) => (
                <Button
                  key={f.id}
                  size="sm"
                  variant={riskFilter === f.id ? 'default' : 'outline'}
                  onClick={() => setRiskFilter(f.id)}
                >
                  {f.label}
                </Button>
              ))}
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={onlyPending}
                  onChange={(e) => setOnlyPending(e.target.checked)}
                />
                {t('repos.filterPending')}
              </label>

              <label className="ml-auto flex items-center gap-2 text-sm">
                <span className="text-muted-foreground">{t('repos.sortBy')}</span>
                <select
                  className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
                  value={sortKey}
                  onChange={(e) => setSortKey(e.target.value as SortKey)}
                >
                  <option value="name">{t('repos.sortName')}</option>
                  <option value="risk">{t('repos.sortRisk')}</option>
                  <option value="avg">{t('repos.sortAvg')}</option>
                  <option value="prs">{t('repos.sortPrs')}</option>
                  <option value="recent">{t('repos.sortRecent')}</option>
                </select>
              </label>

              {hasActiveFilters ? (
                <Button size="sm" variant="ghost" className="gap-1.5" onClick={clearFilters}>
                  <X className="size-3.5" strokeWidth={1.75} />
                  {t('repos.clearFilters')}
                </Button>
              ) : null}
            </div>
          </div>

          {filtered.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t('repos.noMatches')}</p>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {filtered.map((item) => (
                <Card key={item.repo}>
                  <CardHeader className="flex flex-row items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <CardTitle className="truncate text-base">{item.repo}</CardTitle>
                        {item.source === 'audited' ? (
                          <span className="shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">
                            {t('repos.sourceAuditedBadge')}
                          </span>
                        ) : null}
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {item.scores.length} PRs · score medio {item.avg}
                        {item.pending > 0
                          ? ` · ${t('repos.pendingCount', { count: item.pending })}`
                          : ''}
                      </p>
                    </div>
                    {item.latestSemaforo ? (
                      <RiskBadge semaforo={item.latestSemaforo} />
                    ) : null}
                  </CardHeader>
                  <CardContent className="flex items-center justify-between gap-3">
                    <div className="text-sm text-muted-foreground">
                      {item.latest
                        ? `Último PR #${item.latest.pr_id} · ${item.latest.score}/100`
                        : 'Sin análisis'}
                      {item.red > 0 ? ` · ${t('repos.highCount', { count: item.red })}` : ''}
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      <Button
                        size="sm"
                        variant="outline"
                        className="gap-1.5 text-destructive hover:text-destructive"
                        onClick={() => void handleDelete(item.repo)}
                      >
                        <Trash2 className="size-3.5" strokeWidth={1.75} />
                      </Button>
                      <Link
                        to={`/repos/${encodeURIComponent(item.repo)}`}
                        className={cn(
                          buttonVariants({ variant: 'outline', size: 'sm' }),
                          'shrink-0 gap-1.5',
                        )}
                      >
                        {t('repos.open')}
                        <ArrowRight className="size-3.5" strokeWidth={1.75} />
                      </Link>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
          </div>
        </div>
      )}

      <ConnectRepoDialog
        open={connectOpen}
        onOpenChange={setConnectOpen}
        onConnected={() => void loadSummaries()}
      />
    </div>
  )
}
