import { Download, LoaderCircle, LockKeyhole } from 'lucide-react'
import type { VideoFormatResponse } from '../api/types'
import { formatBytes } from '../lib/format'

interface DownloadActionProps {
  canSave: boolean
  formats: VideoFormatResponse[]
  selectedFormatId: string | null
  authorizationConfirmed: boolean
  starting: boolean
  error: string | null
  onSelectFormat: (formatId: string) => void
  onAuthorizationChange: (confirmed: boolean) => void
  onStart: () => void
}

function formatDetails(format: VideoFormatResponse): string {
  return [
    format.container.toUpperCase(),
    format.codec.toUpperCase(),
    format.bitrate_kbps ? `${format.bitrate_kbps} kbps` : null,
    formatBytes(format.filesize_bytes),
  ]
    .filter(Boolean)
    .join(' · ')
}

export function DownloadAction({
  canSave,
  formats,
  selectedFormatId,
  authorizationConfirmed,
  starting,
  error,
  onSelectFormat,
  onAuthorizationChange,
  onStart,
}: DownloadActionProps) {
  if (!canSave || formats.length === 0) {
    return (
      <section className="border-t border-hairline pt-5">
        <div className="flex items-start gap-3">
          <LockKeyhole className="mt-0.5 size-4 shrink-0 text-caution" aria-hidden="true" />
          <div>
            <h2 className="text-base font-semibold tracking-[-0.01em]">Downloads are unavailable</h2>
            <p className="mt-1 text-sm leading-6 text-muted">
              This server has no verified YouTube format options enabled. Ask the server owner to
              enable the Pytubefix download adapter.
            </p>
          </div>
        </div>
        {error && (
          <p role="alert" className="mt-3 text-sm leading-6 text-bad">
            {error}
          </p>
        )}
      </section>
    )
  }

  const ready = Boolean(selectedFormatId) && authorizationConfirmed && !starting

  return (
    <section className="border-t border-hairline pt-5">
      <h2 className="text-base font-semibold tracking-[-0.01em]">Save this video</h2>
      <p className="mt-1 text-sm leading-6 text-muted">
        These are the formats this server found. VidMax pairs the selected video with compatible AAC
        audio and saves the result as MP4 on this device.
      </p>

      <fieldset className="mt-4 space-y-2">
        <legend className="text-xs text-muted">Video format</legend>
        {formats.map((format) => (
          <label
            key={format.id}
            className="flex cursor-pointer items-start gap-3 rounded-xl border border-hairline bg-panel/40 px-3 py-3 transition-colors hover:border-accent/60 has-[:checked]:border-accent has-[:checked]:bg-accent/5"
          >
            <input
              type="radio"
              name="video-format"
              value={format.id}
              checked={selectedFormatId === format.id}
              onChange={() => onSelectFormat(format.id)}
              className="mt-1 size-4 shrink-0 accent-accent"
            />
            <span className="min-w-0">
              <span className="block text-sm font-medium text-copy">{format.label}</span>
              <span className="mt-0.5 block break-words text-xs text-muted">
                {formatDetails(format)}
              </span>
            </span>
          </label>
        ))}
      </fieldset>

      <label className="mt-4 flex cursor-pointer items-start gap-3 text-sm leading-6 text-muted">
        <input
          type="checkbox"
          checked={authorizationConfirmed}
          onChange={(event) => onAuthorizationChange(event.target.checked)}
          className="mt-1 size-4 shrink-0 accent-accent"
        />
        <span>I confirm I’m allowed to save this video for personal use.</span>
      </label>

      <button
        type="button"
        onClick={onStart}
        disabled={!ready}
        className="mt-4 inline-flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-accent px-5 text-[15px] font-semibold text-ink transition-colors hover:bg-accent-soft disabled:cursor-not-allowed disabled:bg-hairline disabled:text-muted sm:w-auto"
      >
        {starting ? (
          <>
            <LoaderCircle className="size-[18px] animate-spin" aria-hidden="true" />
            Starting
          </>
        ) : (
          <>
            <Download className="size-[18px]" aria-hidden="true" />
            Start download
          </>
        )}
      </button>
      {error && (
        <p role="alert" className="mt-3 text-sm leading-6 text-bad">
          {error}
        </p>
      )}
    </section>
  )
}
