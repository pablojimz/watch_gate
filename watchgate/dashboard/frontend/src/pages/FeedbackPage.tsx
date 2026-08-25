import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { MessageSquareText } from 'lucide-react'
import { api, type ScoreOut } from '@/api/client'
import { RiskBadge } from '@/components/dashboard/RiskBadge'
import { TableSkeleton } from '@/components/dashboard/TableSkeleton'
import { Button, buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export default function FeedbackPage() {
  // Un solo segmento de URL codificado (ver App.tsx) -- no ":owner/:name",
  // que rompía cualquier repo sin exactamente una barra.
  const { repo: repoParam = '' } = useParams()
  const repo = decodeURIComponent(repoParam)
  const { t } = useTranslation()
  const [scores, setScores] = useState<ScoreOut[] | null>(null)

  useEffect(() => {
    // Ver el mismo comentario en RepoPage.tsx: sin esta guarda, navegar
    // rápido entre repos puede dejar en pantalla los scores de OTRO repo si
    // esa petición anterior resuelve después de la del repo actual.
    let cancelled = false
    void api
      .listScores(repo)
      .then((s) => {
        if (!cancelled) setScores(s)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        toast.error(err instanceof Error ? err.message : 'Error')
        setScores([])
      })
    return () => {
      cancelled = true
    }
  }, [repo])

  async function submit(scoreId: number, feedback: 'correcto' | 'falso_positivo') {
    try {
      const updated = await api.submitFeedback(scoreId, feedback)
      setScores((prev) =>
        prev ? prev.map((s) => (s.id === scoreId ? updated : s)) : prev,
      )
      toast.success('Feedback registrado')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error')
    }
  }

  if (scores === null) {
    return (
      <div className="p-6">
        <TableSkeleton rows={6} />
      </div>
    )
  }

  return (
    <div className="flex w-full flex-col gap-4 p-4 sm:px-6 lg:px-8 lg:py-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-start gap-3">
          <MessageSquareText className="mt-0.5 size-6 text-primary" strokeWidth={1.75} />
          <div>
            <h1 className="text-xl font-semibold">{t('feedback.title')}</h1>
            <p className="text-sm text-muted-foreground">{repo}</p>
          </div>
        </div>
        <Link
          to={`/repos/${encodeURIComponent(repo)}`}
          className={cn(buttonVariants({ variant: 'outline' }))}
        >
          Volver
        </Link>
      </div>

      {scores.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('feedback.empty')}</p>
      ) : (
        <div className="overflow-hidden rounded-xl border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">PR</th>
                <th className="px-4 py-3 font-medium">Score</th>
                <th className="px-4 py-3 font-medium">Estado</th>
                <th className="px-4 py-3 font-medium" />
                <th className="px-4 py-3 text-right font-medium">{t('repo.risk')}</th>
              </tr>
            </thead>
            <tbody>
              {scores.map((score) => (
                <tr key={score.id} className="border-t">
                  <td className="px-4 py-3 font-medium">#{score.pr_id}</td>
                  <td className="px-4 py-3">{score.score}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {score.human_feedback ?? t('feedback.pending')}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-2">
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => void submit(score.id, 'correcto')}
                      >
                        {t('feedback.correct')}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void submit(score.id, 'falso_positivo')}
                      >
                        {t('feedback.falsePositive')}
                      </Button>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end">
                      <RiskBadge semaforo={score.semaforo} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
