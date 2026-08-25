import { Dialog } from 'radix-ui'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'
import type { Finding, ScoreOut } from '@/api/client'
import { RiskBadge } from '@/components/dashboard/RiskBadge'
import { ThreatNatureTag, ThreatSummaryBadges } from '@/components/dashboard/ThreatBadges'
import { cn } from '@/lib/utils'

function FindingRow({ finding }: { finding: Finding }) {
  const { t } = useTranslation()
  return (
    <div className="rounded-md border bg-background p-2.5 text-xs">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-mono text-muted-foreground">
          {finding.file_path}
          {finding.line ? `:${finding.line}` : ''}
        </span>
        <span
          className={cn(
            'shrink-0 rounded px-1.5 py-0.5 font-medium',
            finding.severity === 'error'
              ? 'bg-destructive/15 text-destructive'
              : finding.severity === 'warning'
                ? 'bg-amber-500/15 text-amber-600 dark:text-amber-400'
                : 'bg-muted text-muted-foreground',
          )}
        >
          {finding.rule_id}
        </span>
      </div>
      <p className="mt-1.5 text-foreground">{finding.message}</p>
      <span className="mt-1 inline-block text-[11px] text-muted-foreground">
        {t(`threat.${finding.threat_nature}`, { defaultValue: finding.threat_nature })}
      </span>
    </div>
  )
}

export function ReportModal({
  score,
  open,
  onOpenChange,
}: {
  score: ScoreOut | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation()
  if (!score) return null

  const layers = Object.values(score.layer_results)

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0" />
        <Dialog.Content className="fixed top-1/2 left-1/2 z-50 max-h-[85vh] w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl border bg-card p-6 shadow-lg focus:outline-none">
          <div className="flex items-start justify-between gap-4">
            <div>
              <Dialog.Title className="text-lg font-semibold">
                {t('report.title', { pr: score.pr_id })}
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-muted-foreground">
                {score.repo} · {score.timestamp.slice(0, 10)}
                {score.author_login ? ` · ${score.author_login}` : ''}
              </Dialog.Description>
            </div>
            <div className="flex items-center gap-3">
              <RiskBadge semaforo={score.semaforo} />
              <Dialog.Close
                className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
                aria-label={t('report.close')}
              >
                <X className="size-4" />
              </Dialog.Close>
            </div>
          </div>

          <ThreatSummaryBadges summary={score.threat_summary} className="mt-4" />

          {score.accepted_by ? (
            <p className="mt-4 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-700 dark:text-emerald-400">
              {t('report.acceptedBy', {
                user: score.accepted_by,
                date: (score.accepted_at ?? '').slice(0, 10),
              })}
            </p>
          ) : null}

          <div className="mt-5 flex flex-col gap-3">
            {layers.map((layer) => (
              <div key={layer.layer_name} className="min-w-0 rounded-lg border p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold">
                      {t(`layers.${layer.layer_name}`, { defaultValue: layer.layer_name })}
                    </span>
                    {layer.threat_nature ? <ThreatNatureTag nature={layer.threat_nature} /> : null}
                  </div>
                  <span className="text-sm font-mono text-muted-foreground">
                    {layer.skipped ? t('repo.skipped') : `${layer.risk_score}/100`}
                  </span>
                </div>
                {layer.skipped ? (
                  <p className="mt-1 text-xs break-words whitespace-pre-line text-muted-foreground">
                    {layer.skip_reason}
                  </p>
                ) : (
                  <>
                    {layer.justification ? (
                      <p className="mt-1.5 text-xs break-words whitespace-pre-line text-muted-foreground">
                        {layer.justification}
                      </p>
                    ) : null}
                    {layer.findings.length > 0 ? (
                      <div className="mt-2.5 flex flex-col gap-1.5">
                        {layer.findings.map((finding, idx) => (
                          <FindingRow key={idx} finding={finding} />
                        ))}
                      </div>
                    ) : null}
                  </>
                )}
              </div>
            ))}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
