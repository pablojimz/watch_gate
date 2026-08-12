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
import type { ScoreOut } from '@/api/client'

// El propio agregador (watchgate/core/models.py, campo `threat_summary` de
// AggregatedResult) ya calcula, por PR, cuántas capas son de cada
// naturaleza -- misma jerarquía que usa `ThreatSummaryBadges` en la tabla.
// Un PR cuenta como "malicioso" si threat_summary.malicioso > 0 (aunque
// otra capa solo tenga una vulnerabilidad), luego "vulnerabilidad", y
// "limpio" si no hay ninguna naturaleza registrada -- para no reconstruir
// en el cliente algo que el backend ya resuelve de forma autoritativa.
function dominantNature(score: ScoreOut): 'malicioso' | 'vulnerabilidad' | 'limpio' {
  if ((score.threat_summary.malicioso ?? 0) > 0) return 'malicioso'
  if ((score.threat_summary.vulnerabilidad ?? 0) > 0) return 'vulnerabilidad'
  return 'limpio'
}

export function CommitsVsThreatsChart({ scores }: { scores: ScoreOut[] }) {
  const { t } = useTranslation()

  const byDay = new Map<string, { day: string; limpio: number; vulnerabilidad: number; malicioso: number }>()
  for (const score of scores) {
    const day = score.timestamp.slice(0, 10)
    const row = byDay.get(day) ?? { day, limpio: 0, vulnerabilidad: 0, malicioso: 0 }
    row[dominantNature(score)] += 1
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
                formatter={(value) => t(`threat.${value}`, { defaultValue: String(value) })}
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
