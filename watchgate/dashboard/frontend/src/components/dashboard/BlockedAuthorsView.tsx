import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ShieldOff, UserX } from 'lucide-react'
import { api, type BlockedAuthor, type RoleName } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'

export function BlockedAuthorsView({ repo, role }: { repo: string; role: RoleName | null }) {
  const { t } = useTranslation()
  const [blocked, setBlocked] = useState<BlockedAuthor[] | null>(null)
  const [authorLogin, setAuthorLogin] = useState('')
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const canManage = role === 'mantenedor'

  function load() {
    void api
      .listBlockedAuthors(repo)
      .then(setBlocked)
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'Error')
      })
  }

  useEffect(() => {
    setBlocked(null)
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repo])

  async function handleBlock(e: React.FormEvent) {
    e.preventDefault()
    const login = authorLogin.trim()
    if (!login) return
    setSubmitting(true)
    try {
      await api.blockAuthor(repo, login, reason.trim())
      toast.success(t('repo.blockedAuthors.blockedToast', { login }))
      setAuthorLogin('')
      setReason('')
      load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleUnblock(login: string) {
    try {
      await api.unblockAuthor(repo, login)
      toast.success(t('repo.blockedAuthors.unblockedToast', { login }))
      load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error')
    }
  }

  if (blocked === null) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-4 animate-pulse rounded bg-muted" />
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {canManage && (
        <Card>
          <CardContent className="pt-5">
            <form onSubmit={(e) => void handleBlock(e)} className="flex flex-wrap gap-2">
              <Input
                placeholder={t('repo.blockedAuthors.loginPlaceholder')}
                value={authorLogin}
                onChange={(e) => setAuthorLogin(e.target.value)}
                className="min-w-40 flex-1"
              />
              <Input
                placeholder={t('repo.blockedAuthors.reasonPlaceholder')}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="min-w-56 flex-[2]"
              />
              <Button type="submit" size="sm" disabled={submitting || !authorLogin.trim()}>
                <UserX className="size-4" />
                {t('repo.blockedAuthors.blockButton')}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {blocked.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center text-muted-foreground">
            <ShieldOff className="size-8" strokeWidth={1.5} />
            <p className="text-sm">{t('repo.blockedAuthors.empty')}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="divide-y rounded-lg border bg-card">
          {blocked.map((b) => (
            <div
              key={b.author_login}
              className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-medium">{b.author_login}</span>
                  <span className="rounded-full bg-red-500/10 px-2 py-0.5 text-[11px] font-medium text-red-600 dark:text-red-400">
                    {t('repo.blockedAuthors.blockedBadge')}
                  </span>
                </div>
                {b.reason && (
                  <p className="mt-0.5 text-xs text-muted-foreground">{b.reason}</p>
                )}
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  {t('repo.blockedAuthors.blockedByLine', {
                    login: b.blocked_by,
                    date: new Date(b.blocked_at).toLocaleString(),
                  })}
                </p>
              </div>
              {canManage && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => void handleUnblock(b.author_login)}
                >
                  {t('repo.blockedAuthors.unblockButton')}
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
