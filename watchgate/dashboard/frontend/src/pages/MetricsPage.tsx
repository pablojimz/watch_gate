import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { BarChart3, Bot, ClipboardCheck, Layers } from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api, type AgentUsageMetrics, type OrgMetrics } from '@/api/client'
import { TableSkeleton } from '@/components/dashboard/TableSkeleton'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { buttonVariants } from '@/components/ui/button'
import { cn, semaforoColor } from '@/lib/utils'

export default function MetricsPage() {
  const { t } = useTranslation()
  const [metrics, setMetrics] = useState<OrgMetrics | null>(null)
  const [agentMetrics, setAgentMetrics] = useState<AgentUsageMetrics | null>(null)

  useEffect(() => {
    void api
      .getMetrics()
      .then(setMetrics)
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'Error')
        setMetrics({
          total_prs: 0,
          avg_score: 0,
          repos_count: 0,
          by_semaforo: { verde: 0, amarillo: 0, rojo: 0 },
          feedback_correct: 0,
          feedback_false_positive: 0,
          feedback_pending: 0,
          layer_avg: { static: 0, deps: 0, vulnerabilities: 0, reputation: 0, semantic: 0 },
          by_repo: [],
          trend: [],
        })
      })

    void api
      .getAgentUsageMetrics()
      .then(setAgentMetrics)
      .catch(() => {
        setAgentMetrics({ total_tokens_used: 0, agents_count: 0, by_agent: [] })
      })
  }, [])

  if (metrics === null) {
    return (
      <div className="p-4 sm:px-6 lg:px-8">
        <TableSkeleton rows={8} />
      </div>
    )
  }

  const summary = [
    { label: t('metrics.totalPrs'), value: String(metrics.total_prs) },
    { label: t('metrics.avgScore'), value: String(metrics.avg_score) },
    { label: t('metrics.repos'), value: String(metrics.repos_count) },
    { label: t('metrics.pendingFeedback'), value: String(metrics.feedback_pending) },
  ]

  const riskData = (['verde', 'amarillo', 'rojo'] as const).map((key) => ({
    name: t(`risk.${key}`),
    key,
    value: metrics.by_semaforo[key] ?? 0,
  }))

  const layerData = Object.entries(metrics.layer_avg).map(([key, value]) => ({
    name: t(`layers.${key}`, { defaultValue: key }),
    value,
  }))

  const feedbackTotal =
    metrics.feedback_correct + metrics.feedback_false_positive + metrics.feedback_pending

  return (
    <div className="flex w-full flex-col gap-6 p-4 sm:px-6 lg:px-8 lg:py-6">
      <div className="flex items-start gap-3">
        <BarChart3 className="mt-0.5 size-6 text-primary" strokeWidth={1.75} />
        <div>
          <h1 className="text-xl font-semibold">{t('metrics.title')}</h1>
          <p className="text-sm text-muted-foreground">{t('metrics.subtitle')}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {summary.map((card) => (
          <Card key={card.label}>
            <CardHeader>
              <CardTitle className="text-sm text-muted-foreground">{card.label}</CardTitle>
            </CardHeader>
            <CardContent className="text-2xl font-semibold">{card.value}</CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">
              {t('metrics.riskDistribution')}
            </CardTitle>
          </CardHeader>
          <CardContent className="h-64">
            {metrics.total_prs === 0 ? (
              <p className="text-sm text-muted-foreground">{t('metrics.empty')}</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={riskData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={55}
                    outerRadius={90}
                    paddingAngle={2}
                  >
                    {riskData.map((entry) => (
                      <Cell key={entry.key} fill={semaforoColor(entry.key)} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center gap-2">
            <Layers className="size-4 text-muted-foreground" strokeWidth={1.75} />
            <CardTitle className="text-sm text-muted-foreground">
              {t('metrics.layerAvg')}
            </CardTitle>
          </CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={layerData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} width={36} />
                <Tooltip />
                <Bar dataKey="value" fill="var(--primary)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">{t('metrics.trend')}</CardTitle>
          </CardHeader>
          <CardContent className="h-64">
            {metrics.trend.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('metrics.empty')}</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={metrics.trend}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="day"
                    tick={{ fontSize: 12 }}
                    tickFormatter={(v) => String(v).slice(5)}
                  />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} width={36} />
                  <Tooltip />
                  <Line
                    type="monotone"
                    dataKey="avg_score"
                    stroke="var(--primary)"
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    name={t('metrics.avgScore')}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-3">
          <CardHeader className="flex flex-row items-center gap-2">
            <Bot className="size-4 text-muted-foreground" strokeWidth={1.75} />
            <CardTitle className="text-sm text-muted-foreground">
              Métricas de Agentes de IA y Consumo SaaS
            </CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto p-0">
            {!agentMetrics || agentMetrics.by_agent.length === 0 ? (
              <p className="px-6 pb-6 text-sm text-muted-foreground">{t('metrics.empty')}</p>
            ) : (
              <table className="w-full min-w-[35rem] text-sm">
                <thead className="bg-muted/40 text-left text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-medium">Agente / Identificador</th>
                    <th className="px-4 py-3 font-medium">Análisis Realizados</th>
                    <th className="px-4 py-3 font-medium">Tokens Consumidos</th>
                    <th className="px-4 py-3 font-medium">Riesgo Promedio (Score)</th>
                  </tr>
                </thead>
                <tbody>
                  {agentMetrics.by_agent.map((agent) => (
                    <tr key={agent.agent_id} className="border-t">
                      <td className="px-4 py-3 font-medium">{agent.agent_id}</td>
                      <td className="px-4 py-3">{agent.analyses_count}</td>
                      <td className="px-4 py-3">{agent.tokens_used.toLocaleString()}</td>
                      <td className="px-4 py-3">{agent.avg_score}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center gap-2">
            <ClipboardCheck className="size-4 text-muted-foreground" strokeWidth={1.75} />
            <CardTitle className="text-sm text-muted-foreground">{t('metrics.feedback')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('feedback.correct')}</span>
              <span className="font-medium">{metrics.feedback_correct}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('feedback.falsePositive')}</span>
              <span className="font-medium">{metrics.feedback_false_positive}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('feedback.pending')}</span>
              <span className="font-medium">{metrics.feedback_pending}</span>
            </div>
            {feedbackTotal > 0 ? (
              <p className="pt-2 text-xs text-muted-foreground">
                {t('metrics.feedbackRate', {
                  rate: Math.round(
                    (metrics.feedback_correct /
                      Math.max(1, metrics.feedback_correct + metrics.feedback_false_positive)) *
                      100,
                  ),
                })}
              </p>
            ) : null}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">{t('metrics.byRepo')}</CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto p-0">
            {metrics.by_repo.length === 0 ? (
              <p className="px-6 pb-6 text-sm text-muted-foreground">{t('metrics.empty')}</p>
            ) : (
              <table className="w-full min-w-[40rem] text-sm">
                <thead className="bg-muted/40 text-left text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-medium">{t('admin.repo')}</th>
                    <th className="px-4 py-3 font-medium">{t('metrics.totalPrs')}</th>
                    <th className="px-4 py-3 font-medium">{t('metrics.avgScore')}</th>
                    <th className="px-4 py-3 font-medium">{t('risk.rojo')}</th>
                    <th className="px-4 py-3 font-medium">{t('feedback.pending')}</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {metrics.by_repo.map((row) => (
                    <tr key={row.repo} className="border-t">
                      <td className="px-4 py-3 font-medium">{row.repo}</td>
                      <td className="px-4 py-3">{row.prs}</td>
                      <td className="px-4 py-3">{row.avg_score}</td>
                      <td className="px-4 py-3">{row.rojo}</td>
                      <td className="px-4 py-3">{row.feedback_pending}</td>
                      <td className="px-4 py-3 text-right">
                        <Link
                          to={`/repos/${encodeURIComponent(row.repo)}`}
                          className={cn(buttonVariants({ variant: 'outline', size: 'sm' }))}
                        >
                          {t('repos.open')}
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
