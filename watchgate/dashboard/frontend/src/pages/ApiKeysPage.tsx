import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { Copy, KeyRound, Trash2 } from 'lucide-react'
import { api, type ApiKey, type CreatedApiKey, type MonitoredRepoResponse } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { TableSkeleton } from '@/components/dashboard/TableSkeleton'

async function copyToClipboard(value: string, message: string) {
  try {
    await navigator.clipboard.writeText(value)
    toast.success(message)
  } catch {
    toast.error('No se pudo copiar')
  }
}

function formatDate(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('es-ES', {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

export default function ApiKeysPage() {
  const { t } = useTranslation()
  const [keys, setKeys] = useState<ApiKey[] | null>(null)
  const [repos, setRepos] = useState<MonitoredRepoResponse[] | null>(null)
  const [name, setName] = useState('')
  const [repoId, setRepoId] = useState('')
  const [creating, setCreating] = useState(false)
  const [revealed, setRevealed] = useState<CreatedApiKey | null>(null)

  function load() {
    void api
      .listApiKeys()
      .then(setKeys)
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'Error')
        setKeys([])
      })
    void api
      .listExternalRepos()
      .then(setRepos)
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'Error')
        setRepos([])
      })
  }

  useEffect(load, [])

  // Mapa id -> repo_path para mostrar el repo de cada clave ya creada sin
  // depender de que el backend lo resuelva siempre (claves legado no lo
  // tienen de todas formas).
  const repoPathById = new Map((repos ?? []).map((r) => [r.id, r.repo_path]))

  async function handleCreate() {
    if (!repoId) return
    setCreating(true)
    try {
      const created = await api.createApiKey(name.trim() || 'API Key', repoId)
      setRevealed(created)
      setName('')
      setRepoId('')
      load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error')
    } finally {
      setCreating(false)
    }
  }

  async function handleDelete(id: string) {
    if (!window.confirm(t('apiKeys.confirmDelete'))) return
    try {
      await api.deleteApiKey(id)
      toast.success(t('apiKeys.deleted'))
      if (revealed?.id === id) setRevealed(null)
      load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error')
    }
  }

  return (
    <div className="flex w-full flex-col gap-4 p-4 sm:px-6 lg:px-8 lg:py-6">
      <div>
        <h1 className="text-xl font-semibold">{t('apiKeys.title')}</h1>
        <p className="text-sm text-muted-foreground">{t('apiKeys.subtitle')}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('apiKeys.newTitle')}</CardTitle>
        </CardHeader>
        <CardContent>
          {repos !== null && repos.length === 0 ? (
            // Sin ningún repo conectado no hay a qué atar la clave -- ya no
            // existe la opción de "clave general" de organización, así que
            // no tiene sentido mostrar el formulario.
            <div className="rounded-md border border-dashed p-4 text-sm">
              <p className="font-medium">{t('apiKeys.noReposTitle')}</p>
              <p className="mt-1 text-muted-foreground">{t('apiKeys.noReposBody')}</p>
              <Button asChild variant="secondary" size="sm" className="mt-3">
                <Link to="/repos">{t('apiKeys.goToExternalRepos')}</Link>
              </Button>
            </div>
          ) : (
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
              <div className="flex-1">
                <label className="mb-1 block text-sm text-muted-foreground">
                  {t('apiKeys.nameLabel')}
                </label>
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={t('apiKeys.namePlaceholder')}
                  maxLength={80}
                />
              </div>
              <div className="flex-1">
                <label className="mb-1 block text-sm text-muted-foreground">
                  {t('apiKeys.repoLabel')}
                </label>
                <select
                  value={repoId}
                  onChange={(e) => setRepoId(e.target.value)}
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
                >
                  <option value="" disabled>
                    {t('apiKeys.repoPlaceholder')}
                  </option>
                  {(repos ?? []).map((repo) => (
                    <option key={repo.id} value={repo.id}>
                      {repo.repo_path}
                    </option>
                  ))}
                </select>
              </div>
              <Button onClick={() => void handleCreate()} disabled={creating || !repoId}>
                <KeyRound className="size-4" strokeWidth={1.75} />
                {t('apiKeys.generate')}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {revealed ? (
        <Card className="border-primary/50 bg-primary/5">
          <CardHeader>
            <CardTitle className="text-base">{t('apiKeys.revealTitle')}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <p className="text-sm text-muted-foreground">{t('apiKeys.revealWarning')}</p>
            <div className="flex items-center gap-2">
              <code className="flex-1 overflow-x-auto rounded-md border bg-background px-3 py-2 text-sm">
                {revealed.raw_token}
              </code>
              <Button
                variant="outline"
                size="icon"
                aria-label={t('apiKeys.copy')}
                onClick={() =>
                  void copyToClipboard(revealed.raw_token, t('apiKeys.copiedToken'))
                }
              >
                <Copy className="size-4" strokeWidth={1.75} />
              </Button>
            </div>
            <div>
              <Button variant="secondary" size="sm" onClick={() => setRevealed(null)}>
                {t('apiKeys.dismiss')}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {keys === null ? (
        <TableSkeleton rows={4} />
      ) : keys.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('apiKeys.empty')}</p>
      ) : (
        <div className="overflow-hidden rounded-xl border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">{t('apiKeys.nameLabel')}</th>
                <th className="px-4 py-3 font-medium">{t('apiKeys.keyColumn')}</th>
                <th className="px-4 py-3 font-medium">{t('apiKeys.repoColumn')}</th>
                <th className="px-4 py-3 font-medium">{t('apiKeys.createdAt')}</th>
                <th className="px-4 py-3 font-medium">{t('apiKeys.lastUsed')}</th>
                <th className="px-4 py-3 text-right font-medium" />
              </tr>
            </thead>
            <tbody>
              {keys.map((key) => (
                <tr key={key.id} className="border-t">
                  <td className="px-4 py-3 font-medium">{key.name}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <code className="rounded bg-muted px-2 py-1 text-xs">
                        {key.key_prefix}••••••••••••••••••••
                      </code>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={t('apiKeys.copy')}
                        title={t('apiKeys.copyPrefixHint')}
                        onClick={() =>
                          void copyToClipboard(key.key_prefix, t('apiKeys.copiedPrefix'))
                        }
                      >
                        <Copy className="size-3.5" strokeWidth={1.75} />
                      </Button>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {key.repo_path ?? repoPathById.get(key.monitored_repo_id ?? '') ?? (
                      <span className="italic">{t('apiKeys.legacyKey')}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {formatDate(key.created_at)}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {formatDate(key.last_used_at)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end">
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={t('apiKeys.revoke')}
                        title={t('apiKeys.revoke')}
                        onClick={() => void handleDelete(key.id)}
                      >
                        <Trash2 className="size-4 text-destructive" strokeWidth={1.75} />
                      </Button>
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
