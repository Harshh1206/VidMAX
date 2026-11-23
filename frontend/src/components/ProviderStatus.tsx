import { Check, CircleHelp, LockKeyhole } from 'lucide-react'
import type { CapabilityStatus, HealthResponse, InspectResponse } from '../api/types'
import { capabilityLabel, platformLabel, savingMessage } from '../lib/labels'

interface StatusRowProps {
  label: string
  status: CapabilityStatus | null
}

function StatusRow({ label, status }: StatusRowProps) {
  const tone =
    status === 'available'
      ? 'text-good'
      : status === 'not_implemented' || status === 'not_configured'
        ? 'text-caution'
        : 'text-muted'
  const Icon =
    status === 'available'
      ? Check
      : status === 'not_implemented' || status === 'not_configured'
        ? LockKeyhole
        : CircleHelp

  return (
    <div className="flex items-center justify-between gap-4 py-2.5">
      <span className="text-sm text-muted">{label}</span>
      <span className={`inline-flex items-center gap-2 text-sm ${tone}`}>
        <Icon className="size-4 shrink-0" aria-hidden="true" />
        {status ? capabilityLabel(status) : 'Checking server'}
      </span>
    </div>
  )
}

interface ProviderStatusProps {
  inspection: InspectResponse
  health: HealthResponse | null
}

export function ProviderStatus({ inspection, health }: ProviderStatusProps) {
  const provider = health?.providers.find((item) => item.platform === inspection.platform)

  return (
    <section className="border-t border-hairline pt-5">
      <h2 className="text-base font-semibold tracking-[-0.01em]">
        Availability for {platformLabel(inspection.platform)}
      </h2>

      <div className="mt-3 divide-y divide-hairline/60">
        <StatusRow label="Link check" status={provider?.url_validation.status ?? null} />
        <StatusRow label="Video details" status={provider?.metadata_inspection.status ?? null} />
        <StatusRow
          label="Saving videos"
          status={inspection.download_capability_status}
        />
      </div>

      <p className="mt-3 text-sm leading-6 text-muted">
        {savingMessage(inspection.platform, inspection.download_capability_status)}
      </p>
    </section>
  )
}
