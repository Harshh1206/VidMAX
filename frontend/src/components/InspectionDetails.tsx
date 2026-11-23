import type { InspectResponse } from '../api/types'
import { formatDuration } from '../lib/format'
import { platformLabel } from '../lib/labels'

interface DetailProps {
  label: string
  value: string
}

function Detail({ label, value }: DetailProps) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-1 break-words text-sm text-copy">{value}</dd>
    </div>
  )
}

interface InspectionDetailsProps {
  inspection: InspectResponse
  formatLabel: string | null
}

export function InspectionDetails({ inspection, formatLabel }: InspectionDetailsProps) {
  const duration = formatDuration(inspection.duration_seconds)

  return (
    <section aria-label="Video details" className="border-t border-hairline pt-5">
      {inspection.author && <p className="break-words text-sm text-muted">{inspection.author}</p>}

      <dl className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Detail label="Platform" value={platformLabel(inspection.platform)} />
        <Detail label="Length" value={duration ?? 'Not shared'} />
        <Detail label="Quality and format" value={formatLabel ?? 'No options shared by this provider'} />
      </dl>

      <p className="mt-5 break-all text-xs leading-5 text-muted/75">
        {inspection.canonical_url}
      </p>
    </section>
  )
}
