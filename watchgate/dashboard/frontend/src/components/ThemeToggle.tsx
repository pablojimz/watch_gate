import { Monitor, Moon, Sun } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { useTheme, type ThemeMode } from '@/lib/theme'

const ICONS: Record<ThemeMode, typeof Sun> = {
  light: Sun,
  dark: Moon,
  system: Monitor,
}

export function ThemeToggle() {
  const { t } = useTranslation()
  const { mode, cycleMode } = useTheme()
  const Icon = ICONS[mode]

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={cycleMode}
      aria-label={t(`theme.${mode}`)}
      title={t(`theme.${mode}`)}
    >
      <Icon className="size-4" />
    </Button>
  )
}
