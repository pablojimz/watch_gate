import { useTranslation } from 'react-i18next'
import type { Semaforo } from '@/api/client'
import { cn, semaforoColor } from '@/lib/utils'

export function RiskBadge({
  semaforo,
  className,
}: {
  semaforo: Semaforo
  className?: string
}) {
  const { t } = useTranslation()

  return (
    <span
      className={cn(
        'inline-flex size-14 shrink-0 flex-col items-center justify-center rounded-md text-[11px] font-semibold leading-tight text-white shadow-sm',
        className,
      )}
      style={{ background: semaforoColor(semaforo) }}
    >
      {t(`risk.${semaforo}`)}
    </span>
  )
}
