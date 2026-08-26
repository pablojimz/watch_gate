import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ClipboardList, History, MessageSquareWarning, Network, ShieldOff, Users } from 'lucide-react'
import { api, type RoleName, type ScoreOut } from '@/api/client'
import { AuthorsBreakdown } from '@/components/dashboard/AuthorsBreakdown'
import { BlockedAuthorsView } from '@/components/dashboard/BlockedAuthorsView'
import { ChartSkeleton } from '@/components/dashboard/ChartSkeleton'
import { CommitsVsThreatsChart } from '@/components/dashboard/CommitsVsThreatsChart'
import { DashboardTabs } from '@/components/dashboard/DashboardTabs'
import { RepoKnowledgeGraphView } from '@/components/dashboard/RepoKnowledgeGraphView'
import { ScoreTrendChart } from '@/components/dashboard/ScoreTrendChart'
import { ScoresTable } from '@/components/dashboard/ScoresTable'
import { SummaryCards } from '@/components/dashboard/SummaryCards'
import { SummaryCardsSkeleton } from '@/components/dashboard/SummaryCardsSkeleton'
import { TableSkeleton } from '@/components/dashboard/TableSkeleton'
import { buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type Tab = 'history' | 'authors' | 'knowledge-graph' | 'blocked-authors'

export default function RepoPage() {
  // Un solo segmento de URL codificado (ver App.tsx) -- no ":owner/:name",
  // que rompía cualquier repo sin exactamente una barra.
  const { repo: repoParam = '' } = useParams()
  const repo = decodeURIComponent(repoParam)
  const { t } = useTranslation()
  const [scores, setScores] = useState<ScoreOut[] | null>(null)
  const [role, setRole] = useState<RoleName | null>(null)
  const [tab, setTab] = useState<Tab>('history')
  // Por defecto se ocultan las PRs ya cerradas/mergeadas (pr_state==='closed',
  // ver RepoPollingService.mark_prs_closed) -- siguen en el histórico
  // (nunca se borran), pero no aportan nada como "pendientes de revisar".
  // Un toggle deja verlas todas sin tener que ir a otro sitio.
  const [showClosed, setShowClosed] = useState(false)

  useEffect(() => {
    // Guarda de "sigue siendo la respuesta actual": sin esto, navegar rápido
    // entre repos (p. ej. botón atrás + clic) puede dejar en pantalla el
    // título/URL de un repo con los scores/rol de OTRO, si la petición del
    // repo anterior resuelve después de la del actual.
    let cancelled = false
    void Promise.all([api.listScores(repo), api.myRole(repo)])
      .then(([s, r]) => {
        if (cancelled) return
        setScores(s)
        setRole(r.role)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        toast.error(err instanceof Error ? err.message : 'Error')
        setScores([])
      })
    return () => {
      cancelled = true
    }
  }, [repo])

  const canFeedback = role === 'mantenedor' || role === 'admin_organizacion'
  const tabs: { id: Tab; label: string; icon: typeof History }[] = [
    { id: 'history', label: t('repo.tabHistory'), icon: History },
    { id: 'authors', label: t('repo.tabAuthors'), icon: Users },
    { id: 'knowledge-graph', label: t('repo.tabKnowledgeGraph'), icon: Network },
    { id: 'blocked-authors', label: t('repo.tabBlockedAuthors'), icon: ShieldOff },
  ]

  return (
    <div className="flex w-full flex-col gap-6 p-4 sm:px-6 lg:px-8 lg:py-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-start gap-3">
          <ClipboardList className="mt-0.5 size-6 text-primary" strokeWidth={1.75} />
          <div>
            <h1 className="text-xl font-semibold">{repo}</h1>
            <p className="text-sm text-muted-foreground">{t('repo.title')}</p>
          </div>
        </div>
        {canFeedback ? (
          <Link
            to={`/repos/${encodeURIComponent(repo)}/feedback`}
            className={cn(buttonVariants({ variant: 'outline' }), 'gap-2')}
          >
            <MessageSquareWarning className="size-4" strokeWidth={1.75} />
            {t('repo.feedbackLink')}
          </Link>
        ) : null}
      </div>

      {scores === null ? (
        <>
          <SummaryCardsSkeleton />
          <ChartSkeleton />
          <TableSkeleton rows={6} />
        </>
      ) : (
        <>
          <SummaryCards scores={scores} />
          <div className="grid gap-4 lg:grid-cols-2">
            <ScoreTrendChart scores={scores} />
            <CommitsVsThreatsChart scores={scores} />
          </div>

          <div className="flex flex-col gap-4 lg:flex-row lg:gap-6">
            <DashboardTabs tabs={tabs} active={tab} onChange={setTab} />
            <div className="min-w-0 flex-1">
              {tab === 'history' ? (
                <div>
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <h2 className="text-lg font-semibold">{t('repo.recent')}</h2>
                    <label className="flex items-center gap-2 text-xs text-muted-foreground">
                      <input
                        type="checkbox"
                        checked={showClosed}
                        onChange={(e) => setShowClosed(e.target.checked)}
                        className="size-3.5 rounded border-input"
                      />
                      {t('repo.showClosedPrs')}
                    </label>
                  </div>
                  <ScoresTable
                    scores={showClosed ? scores : scores.filter((s) => s.pr_state !== 'closed')}
                    canAccept={canFeedback}
                    onScoreUpdated={(updated) =>
                      setScores((prev) =>
                        prev ? prev.map((s) => (s.id === updated.id ? updated : s)) : prev,
                      )
                    }
                  />
                </div>
              ) : tab === 'authors' ? (
                <div>
                  <h2 className="mb-3 text-lg font-semibold">{t('repo.authorsTitle')}</h2>
                  <p className="mb-4 text-sm text-muted-foreground">
                    {t('repo.authorsHint')}
                  </p>
                  <AuthorsBreakdown scores={scores} />
                </div>
              ) : tab === 'knowledge-graph' ? (
                <div>
                  <h2 className="mb-3 text-lg font-semibold">{t('repo.tabKnowledgeGraph')}</h2>
                  <p className="mb-4 text-sm text-muted-foreground">
                    {t('repo.knowledgeGraph.hint')}
                  </p>
                  <RepoKnowledgeGraphView repo={repo} />
                </div>
              ) : (
                <div>
                  <h2 className="mb-3 text-lg font-semibold">{t('repo.tabBlockedAuthors')}</h2>
                  <p className="mb-4 text-sm text-muted-foreground">
                    {t('repo.blockedAuthors.hint')}
                  </p>
                  <BlockedAuthorsView repo={repo} role={role} />
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
