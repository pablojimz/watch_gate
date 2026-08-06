import {
  AlertTriangle,
  ClipboardCheck,
  Gauge,
  GitPullRequest,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { ScoreOut } from '@/api/client'
import type { LucideIcon } from 'lucide-react'

export function SummaryCards({ scores }: { scores: ScoreOut[] }) {
  const { t } = useTranslation()
  const avg =
    scores.length === 0
      ? 0
      : Math.round(scores.reduce((acc, s) => acc + s.score, 0) / scores.length)
  const red = scores.filter((s) => s.semaforo === 'rojo').length
  const pending = scores.filter((s) => s.human_feedback === null).length

  const cards: { label: string; value: string; icon: LucideIcon }[] = [
    { label: t('summary.avgScore'), value: String(avg), icon: Gauge },
    { label: t('summary.prs'), value: String(scores.length), icon: GitPullRequest },
    { label: t('summary.red'), value: String(red), icon: AlertTriangle },
    { label: t('summary.pendingFeedback'), value: String(pending), icon: ClipboardCheck },
  ]

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => {
        const Icon = card.icon
        return (
          <Card key={card.label}>
            <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
              <CardTitle className="text-sm text-muted-foreground">{card.label}</CardTitle>
              <Icon className="size-4 text-muted-foreground" strokeWidth={1.75} />
            </CardHeader>
            <CardContent className="text-2xl font-semibold">{card.value}</CardContent>
          </Card>
        )
      })}
    </div>
  )
}
