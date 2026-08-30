import { Fragment, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { CheckCircle2, ChevronDown, FileText } from 'lucide-react'
import { api, type ScoreOut } from '@/api/client'
import { ReportModal } from '@/components/dashboard/ReportModal'
import { RiskBadge } from '@/components/dashboard/RiskBadge'
import { ThreatNatureTag, ThreatSummaryBadges } from '@/components/dashboard/ThreatBadges'
import { Button } from '@/components/ui/button'
import { cn, layerRiskColor } from '@/lib/utils'

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

  // Sin botón de revocar (petición explícita): "Aceptar" queda como
  // registro de auditoría de un solo sentido -- si además mergeó el PR
  // de verdad en GitHub, "revocar" no lo desmergearía, así que ofrecer
  // ese botón invitaba a pensar que sí lo hacía.
  async function handleAccept(score: ScoreOut) {
    setPendingId(score.id)
    try {
      const updated = await api.acceptScore(score.id)
      onScoreUpdated?.(updated)
      if (!updated.merge_attempted) {
        // Sin PR real que mergear (ingesta genérica de CI, análisis de
        // rama principal, hook local...) -- mismo comportamiento que
        // antes de añadir el merge automático.
        toast.success(t('accept.accepted'))
      } else if (updated.merged) {
        toast.success(t('accept.mergedOnGithub'))
      } else {
        // El merge falló (rama protegida, checks pendientes, conflictos,
        // PR ya cerrado...) -- la aceptación en sí SÍ quedó registrada.
        toast.error(updated.merge_message ?? t('accept.mergeFailed'))
      }
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
                  <td className="px-4 py-3 font-medium">
                    <div className="flex items-center gap-2">
                      #{score.pr_id}
                      {score.pr_state === 'closed' ? (
                        <span className="inline-flex items-center rounded-full border px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                          {t('repo.prClosed')}
                        </span>
                      ) : null}
                    </div>
                  </td>
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
                      {canAccept && !score.accepted_by ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          disabled={pendingId === score.id}
                          onClick={(e) => {
                            e.stopPropagation()
                            void handleAccept(score)
                          }}
                        >
                          <CheckCircle2 className="size-3.5" />
                          {t('accept.accept')}
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
                            className="min-w-0 rounded-lg border bg-card p-3"
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
                            <div className="mt-1 flex items-center gap-1.5 text-lg font-semibold">
                              {layer.skipped ? (
                                t('repo.skipped')
                              ) : (
                                <>
                                  <span
                                    className="size-2.5 shrink-0 rounded-full"
                                    style={{ background: layerRiskColor(layer.risk_score) }}
                                    aria-hidden="true"
                                  />
                                  {layer.risk_score}
                                </>
                              )}
                            </div>
                            {layer.justification ? (
                              <p className="mt-2 text-xs break-words whitespace-pre-line text-muted-foreground">
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
