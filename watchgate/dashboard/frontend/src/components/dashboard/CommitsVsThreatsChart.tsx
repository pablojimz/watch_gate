import { useTranslation } from 'react-i18next'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { semaforoColor } from '@/lib/utils'
import type { ScoreOut, ThreatNature } from '@/api/client'

const _NATURE_RANK: Record<ThreatNature, number> = {
  malicioso: 3,
  vulnerabilidad: 2,
  incertidumbre: 1,
}

// Misma jerarquía que `compute_dominant_threat_nature` en el backend
// (watchgate/core/models.py): un PR con al menos una capa maliciosa cuenta
// como "malicioso" aunque otra capa solo tenga una vulnerabilidad, y así
// sucesivamente -- para que un mismo PR no se cuente dos veces al agrupar
// por día.
function dominantNature(score: ScoreOut): ThreatNature | null {
  let best: ThreatNature | null = null
  for (const layer of Object.values(score.layer_results)) {
    if (!layer.threat_nature) continue
    if (!best || _NATURE_RANK[layer.threat_nature] > _NATURE_RANK[best]) {
      best = layer.threat_nature
    }
  }
  return best
}

export function CommitsVsThreatsChart({ scores }: { scores: ScoreOut[] }) {
  const { t } = useTranslation()

  const byDay = new Map<string, { day: string; limpio: number; vulnerabilidad: number; malicioso: number }>()
  for (const score of scores) {
    const day = score.timestamp.slice(0, 10)
    const row = byDay.get(day) ?? { day, limpio: 0, vulnerabilidad: 0, malicioso: 0 }
    const nature = dominantNature(score)
    if (nature === 'malicioso') row.malicioso += 1
    else if (nature === 'vulnerabilidad') row.vulnerabilidad += 1
    else row.limpio += 1
    byDay.set(day, row)
  }
  const data = [...byDay.values()].sort((a, b) => a.day.localeCompare(b.day))

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm text-muted-foreground">
          {t('repo.commitsVsThreats')}
        </CardTitle>
      </CardHeader>
      <CardContent className="h-64">
        {data.length === 0 ? (
          <p className="flex h-full items-center justify-center text-sm text-muted-foreground">
            {t('feedback.empty')}
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="day"
                tick={{ fontSize: 12 }}
                tickFormatter={(v) => String(v).slice(5)}
              />
              <YAxis allowDecimals={false} tick={{ fontSize: 12 }} width={30} />
              <Tooltip />
              <Legend
                formatter={(value) => t(`threatNature.${value}`, { defaultValue: String(value) })}
              />
              <Bar dataKey="limpio" stackId="a" fill={semaforoColor('verde')} name="limpio" />
              <Bar
                dataKey="vulnerabilidad"
                stackId="a"
                fill={semaforoColor('amarillo')}
                name="vulnerabilidad"
              />
              <Bar dataKey="malicioso" stackId="a" fill={semaforoColor('rojo')} name="malicioso" />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  )
}
