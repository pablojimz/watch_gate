import { cn } from '@/lib/utils'
import type { LucideIcon } from 'lucide-react'

export function DashboardTabs<T extends string>({
  tabs,
  active,
  onChange,
  orientation = 'auto',
}: {
  tabs: { id: T; label: string; icon?: LucideIcon }[]
  active: T
  onChange: (id: T) => void
  orientation?: 'auto' | 'horizontal' | 'vertical'
}) {
  const isHorizontal = orientation === 'horizontal'
  const isVertical = orientation === 'vertical'

  return (
    <div
      className={cn(
        'flex shrink-0 gap-1',
        isHorizontal && 'flex-row flex-wrap',
        isVertical && 'w-full flex-row flex-wrap md:w-52 md:flex-col',
        orientation === 'auto' && 'flex-row flex-wrap lg:w-44 lg:flex-col',
      )}
      role="tablist"
    >
      {tabs.map((tab) => {
        const Icon = tab.icon
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={tab.id === active}
            onClick={() => onChange(tab.id)}
            className={cn(
              'inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors',
              isHorizontal && 'whitespace-nowrap',
              isVertical && 'md:w-full md:text-left',
              orientation === 'auto' && 'lg:w-full lg:text-left',
              tab.id === active
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground',
            )}
          >
            {Icon ? <Icon className="size-4 shrink-0" strokeWidth={1.75} /> : null}
            <span>{tab.label}</span>
          </button>
        )
      })}
    </div>
  )
}
