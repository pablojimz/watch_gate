import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import ReactMarkdown, { type Components } from 'react-markdown'
import { FolderTree, RefreshCw } from 'lucide-react'
import { api, type RepoGraphNode, type RepoKnowledgeGraph } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'

// Mismo criterio que RagCaseModal.tsx: sin @tailwindcss/typography, cada
// elemento markdown se mapea a un estilo explícito ya usado en el resto
// del dashboard, en vez de traer las clases `prose`.
const markdownComponents: Components = {
  h2: ({ children }) => <h2 className="mt-4 mb-1.5 text-sm font-semibold first:mt-0">{children}</h2>,
  h3: ({ children }) => (
    <h3 className="mt-3 mb-1 text-sm font-medium text-muted-foreground">{children}</h3>
  ),
  p: ({ children }) => <p className="mb-2 text-sm leading-relaxed text-foreground">{children}</p>,
  ul: ({ children }) => <ul className="mb-2 list-disc space-y-1 pl-5 text-sm">{children}</ul>,
  li: ({ children }) => <li className="text-foreground">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
}

// Mismo patrón de badges por categoría que typeBadgeClass en RagPage.tsx.
function categoryBadgeClass(category: string): string {
  switch (category) {
    case 'entrypoint':
      return 'bg-red-500/10 text-red-600 dark:text-red-400'
    case 'api':
      return 'bg-blue-500/10 text-blue-600 dark:text-blue-400'
    case 'model':
      return 'bg-purple-500/10 text-purple-600 dark:text-purple-400'
    case 'test':
      return 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
    case 'config':
    case 'infra':
      return 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
    case 'ui':
      return 'bg-pink-500/10 text-pink-600 dark:text-pink-400'
    default:
      return 'bg-muted text-muted-foreground'
  }
}

function groupByDirectory(nodes: RepoGraphNode[]): Map<string, RepoGraphNode[]> {
  const groups = new Map<string, RepoGraphNode[]>()
  for (const node of nodes) {
    const dir = node.file_path.includes('/') ? node.file_path.split('/')[0] : '(raíz)'
    const bucket = groups.get(dir) ?? []
    bucket.push(node)
    groups.set(dir, bucket)
  }
  return groups
}

export function RepoKnowledgeGraphView({ repo }: { repo: string }) {
  const { t } = useTranslation()
  const [graph, setGraph] = useState<RepoKnowledgeGraph | null>(null)
  const [rebuilding, setRebuilding] = useState(false)

  function load() {
    void api
      .getKnowledgeGraph(repo)
      .then((g) => {
        setGraph(g)
        // Alguien puede llegar a esta vista con una reconstrucción ya en
        // marcha (otra persona la lanzó, o esta misma sigue tras
        // recargar la página) -- también hay que vigilarla hasta que
        // termine, no solo cuando el botón se pulsa en esta sesión.
        if (g.status === 'building') setWatching(true)
      })
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'Error')
      })
  }

  useEffect(() => {
    setGraph(null)
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repo])

  // El resultado de la reconstrucción (éxito o el mensaje de error) no
  // llega solo -- antes `load()` se llamaba una única vez justo al
  // encolar, cuando el job de fondo casi nunca ha terminado todavía, y la
  // vista se quedaba congelada ahí para siempre hasta que el usuario
  // recargaba la página a mano (reproducido en vivo: el botón "encolaba"
  // pero parecía no hacer nada). `watching` solo se activa tras pulsar
  // "Reconstruir" -- sondear sin más en un repo que nunca se ha
  // construido (status "pending" de toda la vida) gastaría peticiones
  // para siempre sin motivo.
  const [watching, setWatching] = useState(false)
  useEffect(() => {
    if (!watching) return
    if (graph !== null && (graph.status === 'ready' || graph.status === 'error')) {
      setWatching(false)
      return
    }
    const timer = window.setInterval(load, 3000)
    return () => window.clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watching, graph?.status])

  async function handleRebuild() {
    setRebuilding(true)
    setWatching(true)
    try {
      await api.rebuildKnowledgeGraph(repo)
      toast.success(t('repo.knowledgeGraph.rebuildQueued'))
      load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error')
    } finally {
      setRebuilding(false)
    }
  }

  if (graph === null) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-4 animate-pulse rounded bg-muted" />
        ))}
      </div>
    )
  }

  if (graph.status === 'pending' || graph.status === 'building' || graph.status === 'error') {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-12 text-center text-muted-foreground">
          <FolderTree className="size-8" strokeWidth={1.5} />
          <p className="text-sm">
            {graph.status === 'building'
              ? t('repo.knowledgeGraph.building')
              : graph.status === 'error'
                ? t('repo.knowledgeGraph.errorState', { error: graph.error_message })
                : t('repo.knowledgeGraph.pending')}
          </p>
          {graph.status !== 'building' && (
            <Button size="sm" variant="outline" onClick={() => void handleRebuild()} disabled={rebuilding}>
              <RefreshCw className="size-4" />
              {t('repo.knowledgeGraph.rebuildButton')}
            </Button>
          )}
        </CardContent>
      </Card>
    )
  }

  const groups = groupByDirectory(graph.nodes)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          {t('repo.knowledgeGraph.summaryLine', {
            projectType: graph.project_type || t('repo.knowledgeGraph.unknown'),
            languages: graph.languages || t('repo.knowledgeGraph.unknown'),
            nodeCount: graph.node_count,
            edgeCount: graph.edge_count,
          })}
        </p>
        <Button size="sm" variant="outline" onClick={() => void handleRebuild()} disabled={rebuilding}>
          <RefreshCw className={rebuilding ? 'size-4 animate-spin' : 'size-4'} />
          {t('repo.knowledgeGraph.rebuildButton')}
        </Button>
      </div>

      <Card>
        <CardContent className="pt-5">
          <ReactMarkdown components={markdownComponents}>{graph.overview}</ReactMarkdown>
        </CardContent>
      </Card>

      {graph.module_breakdown.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {graph.module_breakdown.map((module) => (
            <Card key={module.name}>
              <CardContent className="space-y-1.5 pt-4">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-mono text-sm font-medium">{module.name}/</span>
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${categoryBadgeClass(module.dominant_category)}`}
                  >
                    {module.dominant_category}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">
                  {t('repo.knowledgeGraph.fileCount', { count: module.file_count })}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <div className="space-y-2">
        {Array.from(groups.entries()).map(([dir, nodes]) => (
          <details key={dir} className="rounded-lg border bg-card">
            <summary className="flex cursor-pointer items-center justify-between gap-2 px-4 py-2.5 text-sm font-medium">
              <span className="font-mono">{dir}/</span>
              <span className="text-xs font-normal text-muted-foreground">
                {t('repo.knowledgeGraph.fileCount', { count: nodes.length })}
              </span>
            </summary>
            <div className="divide-y border-t">
              {nodes.map((node) => (
                <div key={node.file_path} className="flex flex-col gap-1 px-4 py-2.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs">{node.file_path}</span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${categoryBadgeClass(node.category)}`}
                    >
                      {node.category}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground">{node.summary}</p>
                </div>
              ))}
            </div>
          </details>
        ))}
      </div>
    </div>
  )
}
