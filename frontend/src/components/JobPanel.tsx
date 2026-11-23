import { CheckCircle2, Download, LoaderCircle, TriangleAlert } from 'lucide-react'
import type { JobResponse } from '../api/types'
import { jobStatusLabel } from '../lib/labels'

interface JobPanelProps {
  job: JobResponse
  fileUrl: string | null
  pollingError: string | null
}

export function JobPanel({ job, fileUrl, pollingError }: JobPanelProps) {
  const inProgress = job.status === 'queued' || job.status === 'processing'
  const failed = job.status === 'failed' || job.status === 'expired'
  const Icon = inProgress ? LoaderCircle : failed ? TriangleAlert : CheckCircle2

  return (
    <section className="border-t border-hairline pt-5" aria-live="polite">
      <div className="flex items-start gap-3">
        <Icon
          className={`mt-0.5 size-5 shrink-0 ${inProgress ? 'animate-spin text-accent-soft' : failed ? 'text-bad' : 'text-good'}`}
          aria-hidden="true"
        />
        <div className="min-w-0">
          <h2 className="text-base font-semibold tracking-[-0.01em]">
            {jobStatusLabel(job.status)}
          </h2>
          <p className="mt-1 break-words text-sm leading-6 text-muted">
            {inProgress
              ? 'VidMax is working on this job. You can leave this page open.'
              : job.status === 'completed'
                ? job.file_name
                  ? `Your file is ready: ${job.file_name}`
                  : 'Your file is ready.'
                : job.error_message || 'This job did not finish.'}
          </p>
        </div>
      </div>

      {inProgress && (
        <div className="mt-4">
          <div
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={job.progress}
            aria-label="Download progress"
            className="h-1.5 w-full overflow-hidden rounded-full bg-hairline"
          >
            <div
              className="h-full rounded-full bg-accent transition-[width] duration-300"
              style={{ width: `${Math.min(100, Math.max(0, job.progress))}%` }}
            />
          </div>
          <p className="mt-2 text-xs text-muted">{job.progress}% complete</p>
        </div>
      )}

      {job.status === 'completed' && fileUrl && (
        <a
          href={fileUrl}
          download
          className="mt-4 inline-flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-accent px-5 text-[15px] font-semibold text-ink transition-colors hover:bg-accent-soft sm:w-auto"
        >
          <Download className="size-[18px]" aria-hidden="true" />
          Download file
        </a>
      )}

      {job.status === 'completed' && !fileUrl && (
        <p role="alert" className="mt-3 text-sm leading-6 text-caution">
          The server didn’t return a file link. Check the job status again.
        </p>
      )}

      {pollingError && (
        <p role="alert" className="mt-3 text-sm leading-6 text-bad">
          {pollingError}
        </p>
      )}
    </section>
  )
}
