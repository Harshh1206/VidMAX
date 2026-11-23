import { RotateCcw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { vidmaxApi } from './api/vidmaxApi'
import type { InspectResponse } from './api/types'
import { AppHeader } from './components/AppHeader'
import { DownloadAction } from './components/DownloadAction'
import { InspectionDetails } from './components/InspectionDetails'
import { JobPanel } from './components/JobPanel'
import { PreviewStage } from './components/PreviewStage'
import { ProviderStatus } from './components/ProviderStatus'
import { UrlForm } from './components/UrlForm'
import { useHealth } from './hooks/useHealth'
import { useJobPolling } from './hooks/useJobPolling'
import { describeError } from './lib/labels'
import { validateVideoUrl } from './lib/validation'

export default function App() {
  const [url, setUrl] = useState('')
  const [inspection, setInspection] = useState<InspectResponse | null>(null)
  const [inspecting, setInspecting] = useState(false)
  const [inspectError, setInspectError] = useState<string | null>(null)
  const [inspectionKey, setInspectionKey] = useState(0)
  const [starting, setStarting] = useState(false)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const [selectedFormatId, setSelectedFormatId] = useState<string | null>(null)
  const [authorizationConfirmed, setAuthorizationConfirmed] = useState(false)

  const inspectController = useRef<AbortController | null>(null)
  const downloadController = useRef<AbortController | null>(null)

  const { health, error: healthError } = useHealth()
  const { job, error: pollingError, startJob, clearJob } = useJobPolling()

  useEffect(() => {
    return () => {
      inspectController.current?.abort()
      downloadController.current?.abort()
    }
  }, [])

  const canSave =
    inspection?.downloadable === true &&
    inspection.download_capability_status === 'available' &&
    inspection.formats.length > 0

  const selectedFormat = inspection?.formats.find((format) => format.id === selectedFormatId) ?? null

  const handleInspect = async () => {
    const validationError = validateVideoUrl(url)
    if (validationError) {
      setInspectError(validationError)
      setInspection(null)
      clearJob()
      return
    }

    inspectController.current?.abort()
    const controller = new AbortController()
    inspectController.current = controller

    setInspecting(true)
    setInspectError(null)
      setInspection(null)
      setDownloadError(null)
      setSelectedFormatId(null)
      setAuthorizationConfirmed(false)
      clearJob()


    try {
      const result = await vidmaxApi.inspectVideo(url.trim(), controller.signal)
      if (controller.signal.aborted) return
      setInspection(result)
      setSelectedFormatId(result.recommended_format_id ?? result.formats[0]?.id ?? null)
      setAuthorizationConfirmed(false)
      setInspectionKey((value) => value + 1)
    } catch (error: unknown) {
      if (!controller.signal.aborted) setInspectError(describeError(error))
    } finally {
      if (!controller.signal.aborted) setInspecting(false)
    }
  }

  const handleStartDownload = async () => {
    if (!inspection || !canSave || !selectedFormatId || !authorizationConfirmed) return

    downloadController.current?.abort()
    const controller = new AbortController()
    downloadController.current = controller

    setStarting(true)
    setDownloadError(null)

    try {
      const created = await vidmaxApi.createDownload(
        {
          url: inspection.canonical_url,
          format_id: selectedFormatId,
          target_format: 'mp4',
          authorization: {
            authorized: true,
            basis: 'user_attestation',
            reference: inspection.video_id ?? inspection.canonical_url,
          },
        },
        controller.signal,
      )
      if (controller.signal.aborted) return
      startJob(created)
    } catch (error: unknown) {
      if (!controller.signal.aborted) setDownloadError(describeError(error))
    } finally {
      if (!controller.signal.aborted) setStarting(false)
    }
  }

  const handleReset = () => {
    inspectController.current?.abort()
    downloadController.current?.abort()
    setUrl('')
    setInspection(null)
    setInspectError(null)
    setDownloadError(null)
    setInspecting(false)
    setStarting(false)
    setSelectedFormatId(null)
    setAuthorizationConfirmed(false)
    clearJob()
  }

  const fileUrl = job ? vidmaxApi.getFileUrl(job) : null

  return (
    <div className="min-h-dvh">
      <AppHeader health={health} healthError={healthError} />

      <main className="mx-auto w-full max-w-6xl px-5 pb-16 pt-10 sm:px-8 sm:pt-14">
        <div className="grid items-start gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.02fr)] lg:gap-14">
          <section className="min-w-0">
            <h1 className="max-w-[13ch] text-[clamp(2.35rem,6.4vw,4.1rem)] font-semibold leading-[1.04] tracking-[-0.045em]">
              Save videos. Keep them yours.
            </h1>
            <p className="mt-5 max-w-[52ch] text-[15px] leading-7 text-muted sm:text-base">
              Paste a YouTube or Facebook link. VidMax checks the link and shows what this server
              can do. Files stay on this device when saving is available.
            </p>

            <UrlForm
              value={url}
              loading={inspecting}
              error={inspectError}
              onChange={setUrl}
              onSubmit={() => void handleInspect()}
            />
          </section>

          <section className="min-w-0">
            <div className="overflow-hidden rounded-2xl border border-hairline bg-panel/70 p-3 sm:p-4">
              <PreviewStage inspection={inspection} loading={inspecting} />

              <div className="px-2 pb-2 pt-5 sm:px-3 sm:pb-3">
                {inspection ? (
                  <div key={inspectionKey} className="frame-arrive space-y-5">
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={handleReset}
                        className="inline-flex min-h-11 items-center gap-2 rounded-lg px-3 text-sm text-muted transition-colors hover:bg-hairline/50 hover:text-copy"
                      >
                        <RotateCcw className="size-4" aria-hidden="true" />
                        Start over
                      </button>
                    </div>

                    <InspectionDetails
                      inspection={inspection}
                      formatLabel={selectedFormat?.label ?? null}
                    />
                    <ProviderStatus inspection={inspection} health={health} />
                    <DownloadAction
                      canSave={canSave}
                      formats={inspection.formats}
                      selectedFormatId={selectedFormatId}
                      authorizationConfirmed={authorizationConfirmed}
                      starting={starting}
                      error={downloadError}
                      onSelectFormat={setSelectedFormatId}
                      onAuthorizationChange={setAuthorizationConfirmed}
                      onStart={() => void handleStartDownload()}
                    />
                    {job && (
                      <JobPanel job={job} fileUrl={fileUrl} pollingError={pollingError} />
                    )}
                  </div>
                ) : (
                  <p className="px-1 pb-2 text-sm leading-6 text-muted">
                    Link details, availability, and download progress appear here.
                  </p>
                )}
              </div>
            </div>
          </section>
        </div>
      </main>
    </div>
  )
}
