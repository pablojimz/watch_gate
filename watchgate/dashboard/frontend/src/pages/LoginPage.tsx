import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { GitBranch, LogIn, Shield } from 'lucide-react'
import { toast } from 'sonner'
import { api } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ThemeToggle } from '@/components/ThemeToggle'

export default function LoginPage() {
  const { t } = useTranslation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    try {
      password ? await api.login(username, password) : await api.devLogin(username, "admin_organizacion")
      window.location.href = '/repos'
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Error de login')
      setLoading(false)
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-background p-6">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_color-mix(in_oklab,var(--primary)_18%,transparent),_transparent_55%)]" />
      <div className="absolute right-4 top-4 z-10">
        <ThemeToggle />
      </div>
      <div className="relative z-10 w-full max-w-md rounded-2xl border bg-card p-8 shadow-sm">
        <div className="mb-6 flex items-center gap-3">
          <Shield className="size-8 text-primary" strokeWidth={1.75} />
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{t('brand')}</h1>
            <p className="text-sm text-muted-foreground">{t('login.title')}</p>
          </div>
        </div>
        <p className="mb-6 text-sm text-muted-foreground">{t('login.subtitle')}</p>

        <form className="mb-6 flex flex-col gap-3" onSubmit={(e) => void onSubmit(e)}>
          <label className="text-sm">
            <span className="mb-1 block text-muted-foreground">{t('login.username')}</span>
            <Input
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-muted-foreground">{t('login.password')} (Opcional en entorno de Desarrollo local)</span>
            <Input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <Button type="submit" size="lg" disabled={loading} className="w-full gap-2">
            <LogIn className="size-4" strokeWidth={1.75} />
            {t('login.submit')}
          </Button>
        </form>

        <div className="relative mb-4 text-center text-xs text-muted-foreground">
          <span className="bg-card px-2">{t('login.or')}</span>
        </div>

        <Button
          variant="outline"
          className="w-full gap-2"
          onClick={() => {
            window.location.href = '/api/auth/github/login'
          }}
        >
          <GitBranch className="size-4" strokeWidth={1.75} />
          {t('login.github')}
        </Button>
      </div>
    </div>
  )
}
