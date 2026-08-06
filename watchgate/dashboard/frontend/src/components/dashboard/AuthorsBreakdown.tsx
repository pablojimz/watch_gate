import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown } from 'lucide-react'
import type { ScoreOut, Semaforo } from '@/api/client'
import { RiskBadge } from '@/components/dashboard/RiskBadge'
import { cn } from '@/lib/utils'

interface AuthorStats {
  author: string
  prs: number
  avg: number
  high: number
  medium: number
  low: number
  latest: Semaforo
  scores: ScoreOut[]
}

function buildStats(scores: ScoreOut[]): AuthorStats[] {
  const byAuthor = new Map<string, ScoreOut[]>()
  for (const score of scores) {
    const key = score.author_login || 'desconocido'
    const list = byAuthor.get(key) ?? []
    list.push(score)
    byAuthor.set(key, list)
  }

  return [...byAuthor.entries()]
    .map(([author, list]) => {
      const avg = Math.round(list.reduce((acc, s) => acc + s.score, 0) / list.length)
      const sorted = [...list].sort((a, b) => b.timestamp.localeCompare(a.timestamp))
      return {
        author,
        prs: list.length,
        avg,
        high: list.filter((s) => s.semaforo === 'rojo').length,
        medium: list.filter((s) => s.semaforo === 'amarillo').length,
        low: list.filter((s) => s.semaforo === 'verde').length,
        latest: sorted[0].semaforo,
        scores: sorted,
      }
    })
    .sort((a, b) => b.high - a.high || b.avg - a.avg)
}

export function AuthorsBreakdown({ scores }: { scores: ScoreOut[] }) {
  const { t } = useTranslation()
  const [openAuthor, setOpenAuthor] = useState<string | null>(null)
  const stats = useMemo(() => buildStats(scores), [scores])

  if (stats.length === 0) {
    return <p className="text-sm text-muted-foreground">{t('repo.authorsEmpty')}</p>
  }

  return (
    <div className="overflow-hidden rounded-xl border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-left text-muted-foreground">
          <tr>
            <th className="px-4 py-3 font-medium">{t('repo.author')}</th>
            <th className="px-4 py-3 font-medium">PRs</th>
            <th className="px-4 py-3 font-medium">{t('summary.avgScore')}</th>
            <th className="px-4 py-3 font-medium">{t('risk.rojo')}</th>
            <th className="px-4 py-3 font-medium">{t('risk.amarillo')}</th>
            <th className="px-4 py-3 font-medium">{t('risk.verde')}</th>
            <th className="px-4 py-3 text-right font-medium">{t('repo.latestRisk')}</th>
            <th className="w-12 px-2 py-3" />
          </tr>
        </thead>
        <tbody>
          {stats.map((row) => {
            const open = openAuthor === row.author
            return (
              <FragmentRow
                key={row.author}
                row={row}
                open={open}
                onToggle={() => setOpenAuthor(open ? null : row.author)}
              />
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function FragmentRow({
  row,
  open,
  onToggle,
}: {
  row: AuthorStats
  open: boolean
  onToggle: () => void
}) {
  const { t } = useTranslation()

  return (
    <>
      <tr className="cursor-pointer border-t hover:bg-muted/30" onClick={onToggle}>
        <td className="px-4 py-3 font-medium">{row.author}</td>
        <td className="px-4 py-3">{row.prs}</td>
        <td className="px-4 py-3">{row.avg}</td>
        <td className="px-4 py-3">{row.high}</td>
        <td className="px-4 py-3">{row.medium}</td>
        <td className="px-4 py-3">{row.low}</td>
        <td className="px-4 py-3">
          <div className="flex justify-end">
            <RiskBadge semaforo={row.latest} />
          </div>
        </td>
        <td className="px-2 py-3">
          <button
            type="button"
            className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent"
            aria-label={t('repo.expand')}
            onClick={(e) => {
              e.stopPropagation()
              onToggle()
            }}
          >
            <ChevronDown
              className={cn('size-5 transition-transform duration-200', open && 'rotate-180')}
            />
          </button>
        </td>
      </tr>
      {open ? (
        <tr className="border-t bg-muted/20">
          <td colSpan={8} className="px-4 py-4">
            <div className="space-y-2">
              {row.scores.map((score) => (
                <div
                  key={score.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-card px-3 py-2"
                >
                  <div className="text-sm">
                    <span className="font-medium">PR #{score.pr_id}</span>
                    <span className="text-muted-foreground">
                      {' '}
                      · {score.timestamp.slice(0, 10)} · score {score.score}
                    </span>
                    {score.layer_results.semantic?.justification ? (
                      <p className="mt-1 text-xs text-muted-foreground">
                        {score.layer_results.semantic.justification}
                      </p>
                    ) : null}
                  </div>
                  <RiskBadge semaforo={score.semaforo} />
                </div>
              ))}
            </div>
          </td>
        </tr>
      ) : null}
    </>
  )
}
