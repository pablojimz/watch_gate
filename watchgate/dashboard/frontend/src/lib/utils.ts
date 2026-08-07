import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import type { UiSettings } from '@/api/client'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

const DEFAULT_RISK_COLORS = {
  verde: '#3d9b5f',
  amarillo: '#d4a017',
  rojo: '#c23b3b',
}

const RADIUS_MAP = {
  none: '0px',
  sm: '0.375rem',
  md: '0.625rem',
  lg: '1rem',
} as const

export function applyRiskColors(colors?: Record<string, string> | null) {
  const root = document.documentElement
  const merged = { ...DEFAULT_RISK_COLORS, ...(colors ?? {}) }
  root.style.setProperty('--semaforo-verde', merged.verde)
  root.style.setProperty('--semaforo-amarillo', merged.amarillo)
  root.style.setProperty('--semaforo-rojo', merged.rojo)
}

export function applyUiTheme(settings?: UiSettings | null) {
  const root = document.documentElement
  if (!settings) return
  root.style.setProperty('--primary', settings.primary_color)
  root.style.setProperty('--ring', settings.primary_color)
  root.style.setProperty('--accent', settings.accent_color)
  root.style.setProperty('--radius', RADIUS_MAP[settings.radius] ?? RADIUS_MAP.md)
  root.dataset.fontScale = settings.font_scale
  root.dataset.density = settings.density
  applyFavicon(settings.logo_data_url)
}

// Actualiza la pestaña del navegador con el logo subido en Apariencia. Sin
// logo, vuelve al placeholder vacío de index.html (no hay favicon propio de
// WatchGate como fichero estático, así que "sin logo" es "sin icono", no un
// icono roto).
export function applyFavicon(logoDataUrl?: string | null) {
  const link = document.getElementById('app-favicon') as HTMLLinkElement | null
  if (!link) return
  link.href = logoDataUrl || 'data:,'
}

export function semaforoColor(semaforo: string): string {
  if (semaforo === 'verde') return 'var(--semaforo-verde)'
  if (semaforo === 'amarillo') return 'var(--semaforo-amarillo)'
  return 'var(--semaforo-rojo)'
}
