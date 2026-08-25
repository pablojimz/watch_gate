import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Library, Search } from 'lucide-react'
import { api, type RagCorpusCase } from '@/api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { RagCaseModal } from '@/components/dashboard/RagCaseModal'

const TYPE_ORDER: RagCorpusCase['type'][] = [
  'caso_real',
  'aviso',
  'mitre_attck',
  'tecnica',
  'patron',
  'otro',
]

function typeBadgeClass(type: RagCorpusCase['type']) {
  switch (type) {
    case 'caso_real':
      return 'bg-red-500/10 text-red-600 dark:text-red-400'
    case 'aviso':
      return 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
    case 'mitre_attck':
      return 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
    case 'tecnica':
      return 'bg-blue-500/10 text-blue-600 dark:text-blue-400'
    case 'patron':
      return 'bg-purple-500/10 text-purple-600 dark:text-purple-400'
    default:
      return 'bg-muted text-muted-foreground'
  }
}

export default function RagPage() {
  const { t } = useTranslation()
  const [cases, setCases] = useState<RagCorpusCase[] | null>(null)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<RagCorpusCase | null>(null)

  useEffect(() => {
    void api
      .getRagCorpus()
      .then(setCases)
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'Error')
        setCases([])
      })
  }, [])

  const filtered = useMemo(() => {
    if (!cases) return []
    const q = query.trim().toLowerCase()
    const matching = q
      ? cases.filter(
          (c) => c.title.toLowerCase().includes(q) || c.summary.toLowerCase().includes(q),
        )
      : cases
    // Agrupado por tipo (casos reales primero, luego técnicas MITRE ATT&CK,
    // etc.) en vez de alfabético puro -- así los ejemplos concretos, más
    // fáciles de reconocer para alguien sin contexto de seguridad, quedan
    // arriba del todo.
    return [...matching].sort(
      (a, b) => TYPE_ORDER.indexOf(a.type) - TYPE_ORDER.indexOf(b.type) || a.title.localeCompare(b.title),
    )
  }, [cases, query])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">{t('rag.title')}</h1>
          <p className="text-sm text-muted-foreground">
            {cases ? t('rag.subtitle', { count: cases.length }) : t('rag.subtitleLoading')}
          </p>
        </div>
        <div className="relative w-full max-w-xs">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('rag.searchPlaceholder')}
            className="pl-8"
          />
        </div>
      </div>

      {cases === null ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Card key={i} className="h-40 animate-pulse" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-12 text-center text-muted-foreground">
            <Library className="size-8" strokeWidth={1.5} />
            <p className="text-sm">{cases.length === 0 ? t('rag.empty') : t('rag.noMatches')}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {filtered.map((c) => (
            <Card
              key={c.id}
              className="cursor-pointer transition-colors hover:border-primary/50"
              onClick={() => setSelected(c)}
            >
              <CardHeader className="pb-2">
                <span
                  className={`inline-block w-fit rounded-full px-2 py-0.5 text-xs font-medium ${typeBadgeClass(c.type)}`}
                >
                  {t(`rag.type.${c.type}`)}
                </span>
                <CardTitle className="text-sm leading-snug">{c.title}</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="line-clamp-4 text-sm text-muted-foreground">{c.summary}</p>
                <button
                  type="button"
                  className="mt-3 text-xs font-medium text-primary hover:underline"
                  onClick={(e) => {
                    e.stopPropagation()
                    setSelected(c)
                  }}
                >
                  {t('rag.viewFull')}
                </button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <RagCaseModal
        caseSummary={selected}
        open={selected !== null}
        onOpenChange={(open) => {
          if (!open) setSelected(null)
        }}
      />
    </div>
  )
}
