import { useEffect, useState } from 'react'
import { Dialog } from 'radix-ui'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { X, Plus, GitBranch, FolderGit2, Copy, Terminal } from 'lucide-react'
import { api } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

async function copyToClipboard(value: string, message: string) {
  try {
    await navigator.clipboard.writeText(value)
    toast.success(message)
  } catch {
    toast.error('No se pudo copiar')
  }
}

type ConnectMode = 'github' | 'git_server'

// La instalación del hook `pre-receive` cambia según el servidor: solo
// Gitea/Forgejo soporta la convención `hooks/pre-receive.d/*` (varios
// hooks a la vez); un bare Git plano, GitLab Self-Managed (Custom Hooks),
// Bitbucket Server o Gitolite solo ejecutan un fichero único llamado
// exactamente `hooks/pre-receive` -- ver docs/manual_git_hooks.md §3, §6.3.
// Antes este diálogo daba SIEMPRE la variante `pre-receive.d/watchgate`
// (la única probada en local contra el Forgejo de
// docker-compose.gitserver.yml), así que copiar/pegar el comando en un
// bare repo real no hacía nada -- git nunca mira esa carpeta.
type GitServerType = 'plain' | 'forgejo'

// Diálogo de "Conectar repositorio", reutilizable desde la página de
// Repositorios (donde el usuario espera el botón de añadir) sin sacarle de
// ella. Es distinto de la página de Auditoría Externa, que además LISTA y
// gestiona los repos de terceros -- aquí solo está el alta.
//
// Dos pestañas al mismo nivel (GitHub / Servidor Git propio) en vez de
// GitHub siempre visible arriba y el servidor Git propio escondido en un
// acordeón secundario -- petición explícita del usuario: quería poder
// ELEGIR entre los dos, no que GitHub apareciera siempre por defecto.
//
// OJO iconos: nada de iconos de marca de lucide-react (Github...) -- no
// existen en la versión instalada e importarlos rompe todo el bundle.
export function ConnectRepoDialog({
  open,
  onOpenChange,
  onConnected,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onConnected?: () => void
}) {
  const { t } = useTranslation()
  const [mode, setMode] = useState<ConnectMode>('github')
  const [repoPath, setRepoPath] = useState('')
  const [monitorType, setMonitorType] = useState('audited')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [appInstallUrl, setAppInstallUrl] = useState<string | null>(null)
  const [gitServerRepoPath, setGitServerRepoPath] = useState('')
  const [isConnectingGitServer, setIsConnectingGitServer] = useState(false)
  // Default "plain": es el caso general (bare Git/GitLab/Bitbucket/
  // Gitolite) -- Forgejo/Gitea es la excepción que soporta la carpeta
  // `.d/`, no al revés.
  const [gitServerType, setGitServerType] = useState<GitServerType>('plain')
  const [gitServerResult, setGitServerResult] = useState<{
    repoPath: string
    apiKey: string
    engineApiUrl: string
    hookDownloadUrl: string
  } | null>(null)

  useEffect(() => {
    if (!open) return
    void api
      .getGithubAppInfo()
      .then((info) => setAppInstallUrl(info.install_url))
      .catch(() => setAppInstallUrl(null))
  }, [open])

  // Este diálogo lo monta ReposPage una única vez (solo alterna `open`,
  // ver ExternalReposPage/ReposPage) -- sin este reset, gitServerResult
  // se queda pegado en memoria para siempre tras el primer repo
  // registrado: reabrir el diálogo mostraba el panel de resultado (clave +
  // comando) del ÚLTIMO repo conectado en vez del formulario para
  // registrar uno nuevo, ocultando por completo el campo de nombre.
  useEffect(() => {
    if (open) return
    setGitServerResult(null)
    setGitServerRepoPath('')
  }, [open])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!repoPath.trim()) return
    setIsSubmitting(true)
    try {
      const added = await api.addExternalRepo(repoPath.trim(), monitorType)
      toast.success(t('externalRepos.addSuccess'))
      if (added.warning) toast.warning(added.warning)
      setRepoPath('')
      onConnected?.()
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al añadir repositorio')
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleConnectGitServer(e: React.FormEvent) {
    e.preventDefault()
    if (!gitServerRepoPath.trim()) return
    setIsConnectingGitServer(true)
    try {
      const { repo, api_key, engine_api_url, hook_download_url } =
        await api.connectGitServerRepo(gitServerRepoPath.trim())
      setGitServerResult({
        repoPath: repo.repo_path,
        apiKey: api_key,
        engineApiUrl: engine_api_url,
        hookDownloadUrl: hook_download_url,
      })
      onConnected?.()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error al registrar el repositorio')
    } finally {
      setIsConnectingGitServer(false)
    }
  }

  const installCommand = gitServerResult
    ? gitServerType === 'forgejo'
      ? [
          `mkdir -p hooks/pre-receive.d`,
          `curl -fsSL ${gitServerResult.hookDownloadUrl} -o hooks/pre-receive.d/watchgate`,
          `chmod +x hooks/pre-receive.d/watchgate`,
          `printf 'WATCHGATE_ENGINE_API_URL=${gitServerResult.engineApiUrl}\\nWATCHGATE_ENGINE_API_KEY=${gitServerResult.apiKey}\\n' > hooks/watchgate.env`,
        ].join('\n')
      : [
          // El hook resuelve su .env como "un nivel por encima de donde
          // esté él mismo" ($(dirname "$0")/../watchgate.env, ver
          // pre_receive_hook.sh) -- en la variante Forgejo eso cae en
          // hooks/watchgate.env (sube desde hooks/pre-receive.d/), pero
          // aquí el script vive directo en hooks/, así que un nivel por
          // encima es la RAÍZ del bare repo, no hooks/ otra vez. Puesto
          // en hooks/watchgate.env (como antes) el hook nunca lo
          // encontraba -- verificado en vivo: "WATCHGATE_ENGINE_API_KEY
          // no configurada" pese a que el fichero SÍ existía, solo que
          // en el sitio equivocado.
          `curl -fsSL ${gitServerResult.hookDownloadUrl} -o hooks/pre-receive`,
          `chmod +x hooks/pre-receive`,
          `printf 'WATCHGATE_ENGINE_API_URL=${gitServerResult.engineApiUrl}\\nWATCHGATE_ENGINE_API_KEY=${gitServerResult.apiKey}\\n' > watchgate.env`,
        ].join('\n')
    : ''

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0" />
        <Dialog.Content className="fixed top-1/2 left-1/2 z-50 max-h-[85vh] w-full max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl border bg-card p-6 shadow-lg focus:outline-none">
          <div className="flex items-start justify-between gap-4">
            <div>
              <Dialog.Title className="text-lg font-semibold">
                {t('externalRepos.connectTitle')}
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-muted-foreground">
                {t('connectRepo.dialogSubtitle')}
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button
                className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                aria-label={t('common.close', 'Cerrar')}
              >
                <X className="size-4" />
              </button>
            </Dialog.Close>
          </div>

          {/* Elección explícita GitHub / Servidor Git propio -- ninguna de
              las dos aparece preferida por defecto en el contenido, solo en
              qué pestaña queda seleccionada al abrir. */}
          <div className="mt-5 grid grid-cols-2 gap-2 rounded-lg bg-secondary/30 p-1">
            <button
              type="button"
              onClick={() => setMode('github')}
              className={cn(
                'flex items-center justify-center gap-2 rounded-md py-2 text-sm font-medium transition-colors',
                mode === 'github'
                  ? 'bg-card text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <GitBranch className="size-4" strokeWidth={1.75} />
              {t('externalRepos.modeGithub')}
            </button>
            <button
              type="button"
              onClick={() => setMode('git_server')}
              className={cn(
                'flex items-center justify-center gap-2 rounded-md py-2 text-sm font-medium transition-colors',
                mode === 'git_server'
                  ? 'bg-card text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <FolderGit2 className="size-4" strokeWidth={1.75} />
              {t('externalRepos.modeGitServer')}
            </button>
          </div>

          {mode === 'github' ? (
            <div className="mt-5 space-y-5">
              {/* Explicación de qué es la GitHub App y cómo se conecta --
                  petición explícita del usuario: quería esto documentado
                  aquí mismo, no solo explicado por chat. */}
              <p className="text-xs leading-relaxed text-muted-foreground">
                {t('externalRepos.githubExplainer')}
              </p>

              {/* Vía 1: instalar la GitHub App (solo si está anunciada) */}
              {appInstallUrl && (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-secondary/30 p-4">
                  <div className="flex items-start gap-3">
                    <GitBranch className="mt-0.5 size-5 text-primary" strokeWidth={1.75} />
                    <div>
                      <div className="text-sm font-medium">
                        {t('externalRepos.installAppTitle')}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {t('externalRepos.installAppSubtitle')}
                      </p>
                    </div>
                  </div>
                  <Button asChild className="gap-2">
                    <a href={appInstallUrl}>
                      <GitBranch className="size-4" />
                      {t('externalRepos.installAppButton')}
                    </a>
                  </Button>
                </div>
              )}

              {/* Vía 2: alta manual por nombre */}
              <div className="space-y-1.5">
                <div className="text-sm font-medium">{t('externalRepos.manualAddTitle')}</div>
                <p className="text-xs text-muted-foreground">
                  {t('externalRepos.manualAddSubtitle')}
                </p>
              </div>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    {t('externalRepos.repoPathLabel')}
                  </label>
                  <Input
                    placeholder={t('externalRepos.repoPathPlaceholder')}
                    value={repoPath}
                    onChange={(e) => setRepoPath(e.target.value)}
                    disabled={isSubmitting}
                    autoFocus
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    {t('externalRepos.monitorTypeLabel')}
                  </label>
                  <select
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                    value={monitorType}
                    onChange={(e) => setMonitorType(e.target.value)}
                    disabled={isSubmitting}
                  >
                    <option value="audited">{t('externalRepos.typeAudited')}</option>
                    <option value="managed">{t('externalRepos.typeManaged')}</option>
                  </select>
                </div>
                <Button
                  type="submit"
                  disabled={!repoPath.trim() || isSubmitting}
                  className="w-full gap-2"
                >
                  <Plus className="size-4" />
                  {t('externalRepos.addRepo')}
                </Button>
              </form>
            </div>
          ) : (
            <div className="mt-5 space-y-3 text-sm text-muted-foreground">
              <p>{t('externalRepos.gitServersIntro')}</p>

              {!gitServerResult ? (
                <form onSubmit={handleConnectGitServer} className="space-y-2">
                  <label className="text-xs font-medium text-muted-foreground">
                    {t('externalRepos.gitServersRepoPathLabel')}
                  </label>
                  <div className="flex gap-2">
                    <Input
                      placeholder={t('externalRepos.repoPathPlaceholder')}
                      value={gitServerRepoPath}
                      onChange={(e) => setGitServerRepoPath(e.target.value)}
                      disabled={isConnectingGitServer}
                      autoFocus
                    />
                    <Button
                      type="submit"
                      disabled={!gitServerRepoPath.trim() || isConnectingGitServer}
                      className="shrink-0 gap-2"
                    >
                      <Terminal className="size-4" />
                      {t('externalRepos.gitServersRegisterButton')}
                    </Button>
                  </div>
                </form>
              ) : (
                <div className="space-y-3 rounded-md border bg-card p-3">
                  <p className="text-xs font-medium text-foreground">
                    {t('externalRepos.gitServersResultTitle', {
                      repo: gitServerResult.repoPath,
                    })}
                  </p>

                  <div className="space-y-1">
                    <p className="text-xs">{t('externalRepos.gitServersResultWarning')}</p>
                    <div className="flex items-center gap-2">
                      <code className="flex-1 overflow-x-auto rounded bg-muted px-2 py-1.5 text-xs">
                        {gitServerResult.apiKey}
                      </code>
                      <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        className="shrink-0"
                        onClick={() =>
                          void copyToClipboard(
                            gitServerResult.apiKey,
                            t('externalRepos.gitServersCopiedKey'),
                          )
                        }
                      >
                        <Copy className="size-4" strokeWidth={1.75} />
                      </Button>
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <p className="text-xs font-medium text-foreground">
                      {t('externalRepos.gitServersTypeLabel')}
                    </p>
                    <div className="grid grid-cols-2 gap-2 rounded-lg bg-secondary/30 p-1">
                      <button
                        type="button"
                        onClick={() => setGitServerType('plain')}
                        className={cn(
                          'rounded-md py-1.5 text-xs font-medium transition-colors',
                          gitServerType === 'plain'
                            ? 'bg-card text-foreground shadow-sm'
                            : 'text-muted-foreground hover:text-foreground',
                        )}
                      >
                        {t('externalRepos.gitServersTypePlain')}
                      </button>
                      <button
                        type="button"
                        onClick={() => setGitServerType('forgejo')}
                        className={cn(
                          'rounded-md py-1.5 text-xs font-medium transition-colors',
                          gitServerType === 'forgejo'
                            ? 'bg-card text-foreground shadow-sm'
                            : 'text-muted-foreground hover:text-foreground',
                        )}
                      >
                        {t('externalRepos.gitServersTypeForgejo')}
                      </button>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {gitServerType === 'forgejo'
                        ? t('externalRepos.gitServersTypeHintForgejo')
                        : t('externalRepos.gitServersTypeHintPlain')}
                    </p>
                  </div>

                  <div className="space-y-1">
                    <p className="text-xs">{t('externalRepos.gitServersNextStepsIntro')}</p>
                    <div className="flex items-start gap-2">
                      <pre className="flex-1 overflow-x-auto whitespace-pre-wrap rounded bg-muted px-2 py-1.5 text-xs">
                        {installCommand}
                      </pre>
                      <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        className="shrink-0"
                        onClick={() =>
                          void copyToClipboard(
                            installCommand,
                            t('externalRepos.gitServersCopiedCommand'),
                          )
                        }
                      >
                        <Copy className="size-4" strokeWidth={1.75} />
                      </Button>
                    </div>
                    <p className="text-xs">{t('externalRepos.gitServersRunFrom')}</p>
                  </div>

                  <p className="text-xs">
                    {t('externalRepos.gitServersDocsHint')}{' '}
                    <code className="rounded bg-muted px-1 py-0.5">docs/manual_git_hooks.md</code>
                  </p>
                </div>
              )}

              <ul className="list-disc space-y-1 pl-5 text-xs">
                <li>
                  <span className="font-medium text-foreground">
                    {t('externalRepos.gitServersWebhookTitle')}
                  </span>{' '}
                  {t('externalRepos.gitServersWebhookBody')}{' '}
                  <code className="rounded bg-muted px-1 py-0.5">/api/v1/webhooks/gitlab</code>
                </li>
                <li>
                  <span className="font-medium text-foreground">
                    {t('externalRepos.gitServersEnterpriseTitle')}
                  </span>{' '}
                  {t('externalRepos.gitServersEnterpriseBody')}
                </li>
              </ul>
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
