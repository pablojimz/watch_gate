import { useTranslation } from 'react-i18next'
import type { ThreatNature } from '@/api/client'
import { cn } from '@/lib/utils'

// Mismo icono por naturaleza que ya usan el comentario de PR y la salida de
// consola (ver comment_template.py / formatters/console.py) -- 🚨 malicioso,
// ⚠️ vulnerabilidad, ❓ incertidumbre -- para que el dashboard hable el mismo
// idioma visual que el resto de superficies de WatchGate.
const THREAT_ICON: Record<ThreatNature, string> = {
  malicioso: '🚨',
  vulnerabilidad: '⚠️',
  incertidumbre: '❓',
}

// Reutiliza los tokens de color del tema (--destructive/--warning, ya
// probados en claro y oscuro vía index.css) en vez de colores fijos --
// "malicioso" es tan grave como cualquier otro estado destructivo del
// dashboard, "vulnerabilidad" comparte tono con el semáforo amarillo.
const THREAT_TONE: Record<ThreatNature, string> = {
  malicioso: 'border-destructive/40 bg-destructive/10 text-destructive',
  vulnerabilidad: 'border-warning/40 bg-warning/10 text-warning',
  incertidumbre: 'border-border text-muted-foreground',
}

const THREAT_ORDER: ThreatNature[] = ['malicioso', 'vulnerabilidad', 'incertidumbre']

/** Desglose de hallazgos de una PR por naturaleza (solo las naturalezas
 * con conteo > 0), p. ej. "🚨 1 Malicioso · ⚠️ 3 Vulnerabilidad". */
export function ThreatSummaryBadges({
  summary,
  className,
}: {
  summary: Record<string, number>
  className?: string
}) {
  const { t } = useTranslation()
  const entries = THREAT_ORDER.map((nature) => [nature, summary[nature] ?? 0] as const).filter(
    ([, count]) => count > 0,
  )

  if (entries.length === 0) return null

  return (
    <div className={cn('flex flex-wrap gap-1.5', className)}>
      {entries.map(([nature, count]) => (
        <span
          key={nature}
          className={cn(
            'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium',
            THREAT_TONE[nature],
          )}
        >
          <span aria-hidden="true">{THREAT_ICON[nature]}</span>
          {count} {t(`threat.${nature}`)}
        </span>
      ))}
    </div>
  )
}

/** Etiqueta compacta con la naturaleza dominante de una única capa (p. ej.
 * dentro de la tarjeta expandida de la capa "static"). */
export function ThreatNatureTag({ nature }: { nature: ThreatNature }) {
  const { t } = useTranslation()
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[11px] font-medium',
        THREAT_TONE[nature],
      )}
    >
      <span aria-hidden="true">{THREAT_ICON[nature]}</span>
      {t(`threat.${nature}`)}
    </span>
  )
}
