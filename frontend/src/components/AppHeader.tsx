import { Clapperboard } from 'lucide-react'
import type { HealthResponse } from '../api/types'

interface AppHeaderProps {
  health: HealthResponse | null
  healthError: string | null
}

export function AppHeader({ health, healthError }: AppHeaderProps) {
  const connected = health?.status === 'ok'
  const indicator = connected ? 'bg-good' : 'bg-caution'

  return (
    <header className="border-b border-hairline/70">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-5 py-4 sm:px-8">
        <div className="flex min-w-0 items-center gap-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-[10px] border border-accent/40 bg-accent/10 text-accent-soft">
            <Clapperboard className="size-[18px]" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="text-[15px] font-semibold tracking-[-0.02em]">VidMax</p>
            <p className="truncate text-xs text-muted">Runs on your machine</p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2 text-xs text-muted">
          <span className={`size-1.5 rounded-full ${indicator}`} aria-hidden="true" />
          <span>{connected ? 'Server connected' : healthError ? 'Server offline' : 'Checking server'}</span>
        </div>
      </div>
    </header>
  )
}
