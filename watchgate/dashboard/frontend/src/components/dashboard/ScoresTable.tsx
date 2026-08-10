import { Fragment, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown } from 'lucide-react'
import type { ScoreOut } from '@/api/client'
import { RiskBadge } from '@/components/dashboard/RiskBadge'
import { ThreatNatureTag, ThreatSummaryBadges } from '@/components/dashboard/ThreatBadges'
import { cn } from '@/lib/utils'

export function ScoresTable({ scores }: { scores: ScoreOut[] }) {
  const { t } = useTranslation()
  const [openId, setOpenId] = useState<number | null>(null)

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
            <th className="px-4 py-3 text-right font-medium">{t('repo.risk')}</th>
            <th className="w-12 px-2 py-3" />
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
                    <div className="flex justify-end">
                      <RiskBadge semaforo={score.semaforo} />
                    </div>
                  </td>
                  <td className="px-2 py-3">
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
                  </td>
                </tr>
                {open ? (
                  <tr className="border-t bg-muted/20">
                    <td colSpan={8} className="px-4 py-4">
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
    </div>
  )
}
