import { Fragment, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { CheckCircle2, ChevronDown, FileText, Undo2 } from 'lucide-react'
import { api, type ScoreOut } from '@/api/client'
import { ReportModal } from '@/components/dashboard/ReportModal'
import { RiskBadge } from '@/components/dashboard/RiskBadge'
import { ThreatNatureTag, ThreatSummaryBadges } from '@/components/dashboard/ThreatBadges'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export function ScoresTable({
  scores,
  canAccept = false,
  onScoreUpdated,
}: {
  scores: ScoreOut[]
  canAccept?: boolean
  onScoreUpdated?: (score: ScoreOut) => void
}) {
  const { t } = useTranslation()
  const [openId, setOpenId] = useState<number | null>(null)
  const [reportScore, setReportScore] = useState<ScoreOut | null>(null)
  const [pendingId, setPendingId] = useState<number | null>(null)

  async function toggleAccept(score: ScoreOut) {
    setPendingId(score.id)
    try {
      const updated = score.accepted_by
        ? await api.unacceptScore(score.id)
        : await api.acceptScore(score.id)
      onScoreUpdated?.(updated)
      toast.success(updated.accepted_by ? t('accept.accepted') : t('accept.revoked'))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error')
    } finally {
      setPendingId(null)
    }
  }

  return (
    <div className="overflow-hidden rounded-xl border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-left text-muted-foreground">
          <tr>
            <th className="px-4 py-3 font-medium">PR</th>
            <th className="px-4 py-3 font-medium">{t('repo.author')}</th>
            <th className="px-4 py-3 font-medium">Score</th>
            <th className="px-4 py-3 font-medium">Fecha</th>
            <th className="px-4 py-3 font-medium">Feedback</th>
            <th className="px-4 py-3 font-medium">{t('threat.summaryTitle')}</th>
            <th className="px-4 py-3 font-medium">{t('accept.column')}</th>
            <th className="px-4 py-3 text-right font-medium">{t('repo.risk')}</th>
            <th className="px-2 py-3" />
          </tr>
        </thead>
        <tbody>
          {scores.map((score) => {
            const open = openId === score.id
            return (
              <Fragment key={score.id}>
                <tr
                  className="cursor-pointer border-t hover:bg-muted/30"
                  onClick={() => setOpenId(open ? null : score.id)}
                >
                  <td className="px-4 py-3 font-medium">#{score.pr_id}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {score.author_login ?? '—'}
                  </td>
                  <td className="px-4 py-3">{score.score}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {score.timestamp.slice(0, 10)}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {score.human_feedback ?? t('feedback.pending')}
                  </td>
                  <td className="px-4 py-3">
                    <ThreatSummaryBadges summary={score.threat_summary} />
                  </td>
                  <td className="px-4 py-3">
                    {score.accepted_by ? (
                      <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                        <CheckCircle2 className="size-3.5" />
                        {score.accepted_by}
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground">
                        {t('accept.notAccepted')}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end">
                      <RiskBadge semaforo={score.semaforo} />
                    </div>
                  </td>
                  <td className="px-2 py-3">
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
                        aria-label={t('report.open')}
                        onClick={(e) => {
                          e.stopPropagation()
                          setReportScore(score)
                        }}
                      >
                        <FileText className="size-4" />
                      </button>
                      {canAccept ? (
                        <Button
                          type="button"
                          size="sm"
                          variant={score.accepted_by ? 'outline' : 'secondary'}
                          disabled={pendingId === score.id}
                          onClick={(e) => {
                            e.stopPropagation()
                            void toggleAccept(score)
                          }}
                        >
                          {score.accepted_by ? (
                            <Undo2 className="size-3.5" />
                          ) : (
                            <CheckCircle2 className="size-3.5" />
                          )}
                          {score.accepted_by ? t('accept.revoke') : t('accept.accept')}
                        </Button>
                      ) : null}
                      <button
                        type="button"
                        className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
                        aria-label={t('repo.expand')}
                        onClick={(e) => {
                          e.stopPropagation()
                          setOpenId(open ? null : score.id)
                        }}
                      >
                        <ChevronDown
                          className={cn(
                            'size-5 transition-transform duration-200',
                            open && 'rotate-180',
                          )}
                        />
                      </button>
                    </div>
                  </td>
                </tr>
                {open ? (
                  <tr className="border-t bg-muted/20">
                    <td colSpan={9} className="px-4 py-4">
                      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                        {Object.values(score.layer_results).map((layer) => (
                          <div
                            key={layer.layer_name}
                            className="rounded-lg border bg-card p-3"
                          >
                            <div className="flex items-center justify-between gap-2">
                              <div className="text-xs text-muted-foreground">
                                {t(`layers.${layer.layer_name}`, {
                                  defaultValue: layer.layer_name,
                                })}
                              </div>
                              {layer.threat_nature ? (
                                <ThreatNatureTag nature={layer.threat_nature} />
                              ) : null}
                            </div>
                            <div className="mt-1 text-lg font-semibold">
                              {layer.skipped ? t('repo.skipped') : layer.risk_score}
                            </div>
                            {layer.justification ? (
                              <p className="mt-2 text-xs text-muted-foreground">
                                {layer.justification}
                              </p>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            )
          })}
        </tbody>
      </table>
      <ReportModal
        score={reportScore}
        open={reportScore !== null}
        onOpenChange={(next) => {
          if (!next) setReportScore(null)
        }}
      />
    </div>
  )
}
