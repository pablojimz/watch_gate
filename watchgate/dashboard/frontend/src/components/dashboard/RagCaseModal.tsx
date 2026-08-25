import { useEffect, useState } from 'react'
import { Dialog } from 'radix-ui'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { X } from 'lucide-react'
import ReactMarkdown, { type Components } from 'react-markdown'
import { api, type RagCorpusCase } from '@/api/client'

// Sin @tailwindcss/typography (no instalado, y no vale la pena traerlo solo
// para esta vista): en vez de las clases `prose`, cada elemento markdown se
// mapea a su propio estilo explícito con las mismas clases de texto que ya
// usa el resto del dashboard (text-muted-foreground, font-semibold...).
const markdownComponents: Components = {
  h1: () => null, // El título ya se muestra en Dialog.Title -- no duplicar.
  h2: ({ children }) => <h2 className="mt-4 mb-1.5 text-sm font-semibold first:mt-0">{children}</h2>,
  h3: ({ children }) => (
    <h3 className="mt-3 mb-1 text-sm font-medium text-muted-foreground">{children}</h3>
  ),
  p: ({ children }) => <p className="mb-2 text-sm leading-relaxed text-foreground">{children}</p>,
  ul: ({ children }) => <ul className="mb-2 list-disc space-y-1 pl-5 text-sm">{children}</ul>,
  ol: ({ children }) => <ol className="mb-2 list-decimal space-y-1 pl-5 text-sm">{children}</ol>,
  li: ({ children }) => <li className="text-foreground">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  code: ({ children }) => (
    <code className="rounded bg-muted px-1 py-0.5 font-mono text-[13px]">{children}</code>
  ),
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-primary underline">
      {children}
    </a>
  ),
}

export function RagCaseModal({
  caseSummary,
  open,
  onOpenChange,
}: {
  caseSummary: RagCorpusCase | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation()
  const [content, setContent] = useState<string | null>(null)

  useEffect(() => {
    if (!open || !caseSummary) {
      setContent(null)
      return
    }
    void api
      .getRagCorpusCase(caseSummary.id)
      .then((detail) => setContent(detail.content))
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'Error')
        onOpenChange(false)
      })
    // caseSummary cambia de referencia en cada fetch de la lista -- solo
    // nos interesa re-disparar cuando cambia el id realmente mostrado.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, caseSummary?.id])

  if (!caseSummary) return null

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0" />
        <Dialog.Content className="fixed top-1/2 left-1/2 z-50 max-h-[85vh] w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl border bg-card p-6 shadow-lg focus:outline-none">
          <div className="flex items-start justify-between gap-4">
            <Dialog.Title className="text-lg font-semibold leading-snug">
              {caseSummary.title}
            </Dialog.Title>
            <Dialog.Close
              className="flex size-8 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
              aria-label={t('rag.close')}
            >
              <X className="size-4" />
            </Dialog.Close>
          </div>
          <Dialog.Description className="sr-only">{caseSummary.summary}</Dialog.Description>

          {content === null ? (
            <div className="mt-4 space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-4 animate-pulse rounded bg-muted" />
              ))}
            </div>
          ) : (
            <div className="mt-4">
              <ReactMarkdown components={markdownComponents}>{content}</ReactMarkdown>
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
