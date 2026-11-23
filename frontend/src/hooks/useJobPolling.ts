import { useCallback, useEffect, useState } from 'react'
import { vidmaxApi } from '../api/vidmaxApi'
import type { JobResponse, JobStatus } from '../api/types'
import { describeError } from '../lib/labels'

const terminalStatuses: JobStatus[] = ['completed', 'failed', 'cancelled', 'expired']
const pollIntervalMs = 1200
const maxFailures = 3

export function useJobPolling() {
  const [job, setJob] = useState<JobResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const startJob = useCallback((next: JobResponse) => {
    setJob(next)
    setError(null)
  }, [])

  const clearJob = useCallback(() => {
    setJob(null)
    setError(null)
  }, [])

  const jobId = job?.id ?? null
  const status = job?.status ?? null

  useEffect(() => {
    if (!jobId || !status || terminalStatuses.includes(status)) return

    let cancelled = false
    let timer: number | undefined
    let controller: AbortController | null = null
    let failures = 0

    const poll = async () => {
      controller = new AbortController()
      try {
        const next = await vidmaxApi.getJob(jobId, controller.signal)
        if (cancelled) return
        failures = 0
        setError(null)
        setJob(next)
        if (!terminalStatuses.includes(next.status)) {
          timer = window.setTimeout(poll, pollIntervalMs)
        }
      } catch (cause: unknown) {
        if (cancelled) return
        failures += 1
        setError(describeError(cause))
        if (failures < maxFailures) {
          timer = window.setTimeout(poll, pollIntervalMs * 1.5)
        }
      }
    }

    timer = window.setTimeout(poll, pollIntervalMs)
    return () => {
      cancelled = true
      if (timer !== undefined) window.clearTimeout(timer)
      controller?.abort()
    }
  }, [jobId, status])

  return { job, error, startJob, clearJob }
}
