import { Film, LoaderCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { InspectResponse } from '../api/types'
import { formatDuration } from '../lib/format'
import { platformLabel } from '../lib/labels'

interface PreviewStageProps {
  inspection: InspectResponse | null
  loading: boolean
}

export function PreviewStage({ inspection, loading }: PreviewStageProps) {
  const [imageFailed, setImageFailed] = useState(false)

  useEffect(() => {
    setImageFailed(false)
  }, [inspection?.thumbnail_url])

  const thumbnail = inspection?.thumbnail_url && !imageFailed ? inspection.thumbnail_url : null
  const duration = inspection ? formatDuration(inspection.duration_seconds) : null

  return (
    <div className="relative aspect-video w-full overflow-hidden rounded-frame border border-hairline/70 bg-ink">
      <span className="pointer-events-none absolute left-3 top-3 size-5 border-l-2 border-t-2 border-accent/70" aria-hidden="true" />
      <span className="pointer-events-none absolute right-3 top-3 size-5 border-r-2 border-t-2 border-accent/70" aria-hidden="true" />
      <span className="pointer-events-none absolute bottom-3 left-3 size-5 border-b-2 border-l-2 border-accent/70" aria-hidden="true" />
      <span className="pointer-events-none absolute bottom-3 right-3 size-5 border-b-2 border-r-2 border-accent/70" aria-hidden="true" />

      {loading ? (
        <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
          <LoaderCircle className="size-6 animate-spin text-accent-soft" aria-hidden="true" />
          <p className="text-sm text-muted">Checking the link…</p>
        </div>
      ) : !inspection ? (
        <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
          <Film className="size-7 text-muted/60" aria-hidden="true" />
          <p className="max-w-[28ch] text-sm leading-6 text-muted">
            Paste a video link to see its details here.
          </p>
        </div>
      ) : thumbnail ? (
        <>
          <img
            src={thumbnail}
            alt={inspection.title ? `Thumbnail for ${inspection.title}` : 'Video thumbnail'}
            onError={() => setImageFailed(true)}
            className="absolute inset-0 size-full object-cover"
          />
          <div className="absolute inset-x-0 bottom-0 border-t border-hairline/60 bg-ink/92 px-4 py-3 sm:px-5">
            <p className="line-clamp-2 break-words text-sm font-medium leading-5 text-copy">
              {inspection.title ?? 'Video found'}
            </p>
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
              <span>{platformLabel(inspection.platform)}</span>
              {duration && <span>{duration}</span>}
            </div>
          </div>
        </>
      ) : (
        <div className="flex h-full flex-col justify-end px-5 pb-5 sm:px-6 sm:pb-6">
          <div className="min-w-0" aria-live="polite">
            <p className="line-clamp-3 break-words text-lg font-medium leading-snug tracking-[-0.02em] sm:text-xl">
              {inspection.title ?? 'Video found'}
            </p>
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-sm text-muted">
              {inspection.author && <span>{inspection.author}</span>}
              <span>{platformLabel(inspection.platform)}</span>
              {duration && <span>{duration}</span>}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
