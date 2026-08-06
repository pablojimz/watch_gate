import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowRight, FolderGit2, Search, X } from 'lucide-react'
import { toast } from 'sonner'
import { api, type ScoreOut, type Semaforo } from '@/api/client'
import { RiskBadge } from '@/components/dashboard/RiskBadge'
import { TableSkeleton } from '@/components/dashboard/TableSkeleton'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button, buttonVariants } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

interface RepoSummary {
  repo: string
  scores: ScoreOut[]
  latest: ScoreOut | null
  avg: number
  red: number
  medium: number
  pending: number
  latestSemaforo: Semaforo | null
}

type RiskFilter = 'all' | Semaforo
type SortKey = 'name' | 'risk' | 'avg' | 'prs' | 'recent'

const RISK_ORDER: Record<Semaforo, number> = { rojo: 0, amarillo: 1, verde: 2 }

export default function ReposPage() {
  const { t } = useTranslation()
  const [summaries, setSummaries] = useState<RepoSummary[] | null>(null)
  const [query, setQuery] = useState('')
  const [riskFilter, setRiskFilter] = useState<RiskFilter>('all')
  const [onlyPending, setOnlyPending] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('name')

  useEffect(() => {
    void (async () => {
      try {
        const repos = await api.listRepos()
        const rows = await Promise.all(
          repos.map(async (repo) => {
            const scores = await api.listScores(repo)
            const avg =
              scores.length === 0
                ? 0
                : Math.round(scores.reduce((acc, s) => acc + s.score, 0) / scores.length)
            const latest =
              scores.length === 0
                ? null
                : [...scores].sort((a, b) => b.timestamp.localeCompare(a.timestamp))[0]
            return {
              repo,
              scores,
              latest,
              avg,
              red: scores.filter((s) => s.semaforo === 'rojo').length,
              medium: scores.filter((s) => s.semaforo === 'amarillo').length,
              pending: scores.filter((s) => s.human_feedback === null).length,
              latestSemaforo: latest?.semaforo ?? null,
            }
          }),
        )
        setSummaries(rows)
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Error')
        setSummaries([])
      }
    })()
  }, [])

  const filtered = useMemo(() => {
    if (!summaries) return []
    const q = query.trim().toLowerCase()
    const rows = summaries.filter((item) => {
      if (q && !item.repo.toLowerCase().includes(q)) return false
      if (riskFilter !== 'all' && item.latestSemaforo !== riskFilter) return false
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
  }, [summaries, query, riskFilter, onlyPending, sortKey])

  const hasActiveFilters =
    query.trim() !== '' || riskFilter !== 'all' || onlyPending || sortKey !== 'name'

  function clearFilters() {
    setQuery('')
    setRiskFilter('all')
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
        {summaries.length > 0 ? (
          <p className="text-sm text-muted-foreground">
            {t('repos.showing', { shown: filtered.length, total: summaries.length })}
          </p>
        ) : null}
      </div>

      {summaries.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('repos.empty')}</p>
      ) : (
        <>
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
                      <CardTitle className="truncate text-base">{item.repo}</CardTitle>
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
                    <Link
                      to={`/repos/${item.repo}`}
                      className={cn(
                        buttonVariants({ variant: 'outline', size: 'sm' }),
                        'shrink-0 gap-1.5',
                      )}
                    >
                      {t('repos.open')}
                      <ArrowRight className="size-3.5" strokeWidth={1.75} />
                    </Link>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
