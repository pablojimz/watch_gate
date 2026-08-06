import { useTranslation } from 'react-i18next'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { ScoreOut } from '@/api/client'

export function ScoreTrendChart({ scores }: { scores: ScoreOut[] }) {
  const { t } = useTranslation()
  const data = [...scores]
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp))
    .map((s) => ({
      day: s.timestamp.slice(0, 10),
      score: s.score,
      pr: s.pr_id,
    }))

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm text-muted-foreground">
          {t('repo.scoreTrend')}
        </CardTitle>
      </CardHeader>
      <CardContent className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="day" tick={{ fontSize: 12 }} tickFormatter={(v) => String(v).slice(5)} />
            <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} width={40} />
            <Tooltip />
            <Line
              type="monotone"
              dataKey="score"
              stroke="var(--primary)"
              strokeWidth={2}
              dot={{ r: 3 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}
