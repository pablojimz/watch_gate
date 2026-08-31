import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { KeyRound, UserMinus, UserPlus } from 'lucide-react'
import { api, type RepoRole, type RoleName } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'

// RBAC de "dueño de repo": un `mantenedor` gestiona SOLO el acceso a este
// repo concreto (ver feedback.py::upsert_role/delete_role) -- por eso el
// selector no ofrece "admin_organizacion" aquí, ni falta que hace: quien
// necesite conceder ese rango ya tiene el panel de administración de la
// organización completo (`/admin`).
const ASSIGNABLE_ROLES: RoleName[] = ['revisor', 'mantenedor']

export function RepoAccessView({ repo, role }: { repo: string; role: RoleName | null }) {
  const { t } = useTranslation()
  const [roles, setRoles] = useState<RepoRole[] | null>(null)
  const [login, setLogin] = useState('')
  const [newRole, setNewRole] = useState<RoleName>('revisor')
  const [submitting, setSubmitting] = useState(false)
  const canManage = role === 'mantenedor' || role === 'admin_organizacion'

  function load() {
    void api
      .listRepoRoles(repo)
      .then(setRoles)
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'Error')
      })
  }

  useEffect(() => {
    setRoles(null)
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repo])

  function roleLabel(r: RoleName): string {
    return r === 'mantenedor'
      ? t('repo.access.roleMantenedor')
      : r === 'admin_organizacion'
        ? t('repo.access.roleAdminOrganizacion')
        : t('repo.access.roleRevisor')
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    const targetLogin = login.trim()
    if (!targetLogin) return
    setSubmitting(true)
    try {
      await api.upsertRole({ user_login: targetLogin, repo, role: newRole })
      toast.success(
        t('repo.access.addedToast', { login: targetLogin, role: roleLabel(newRole) }),
      )
      setLogin('')
      load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRemove(targetLogin: string) {
    try {
      await api.deleteRole(targetLogin, repo)
      toast.success(t('repo.access.removedToast', { login: targetLogin }))
      load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error')
    }
  }

  if (roles === null) {
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
            <form onSubmit={(e) => void handleAdd(e)} className="flex flex-wrap gap-2">
              <Input
                placeholder={t('repo.access.loginPlaceholder')}
                value={login}
                onChange={(e) => setLogin(e.target.value)}
                className="min-w-40 flex-1"
              />
              <select
                value={newRole}
                onChange={(e) => setNewRole(e.target.value as RoleName)}
                className="rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                {ASSIGNABLE_ROLES.map((r) => (
                  <option key={r} value={r}>
                    {roleLabel(r)}
                  </option>
                ))}
              </select>
              <Button type="submit" size="sm" disabled={submitting || !login.trim()}>
                <UserPlus className="size-4" />
                {t('repo.access.addButton')}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {roles.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center text-muted-foreground">
            <KeyRound className="size-8" strokeWidth={1.5} />
            <p className="text-sm">{t('repo.access.empty')}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="divide-y rounded-lg border bg-card">
          {roles.map((r) => (
            <div
              key={r.user_login}
              className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-sm font-medium">{r.user_login}</span>
                <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
                  {roleLabel(r.role)}
                </span>
              </div>
              {canManage && (
                <Button size="sm" variant="outline" onClick={() => void handleRemove(r.user_login)}>
                  <UserMinus className="size-4" />
                  {t('repo.access.removeButton')}
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
