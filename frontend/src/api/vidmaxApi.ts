import { apiRequest, resolveApiUrl } from './client'
import type {
  CreateDownloadRequest,
  HealthResponse,
  InspectResponse,
  JobResponse,
} from './types'

export const vidmaxApi = {
  getHealth(signal?: AbortSignal): Promise<HealthResponse> {
    return apiRequest<HealthResponse>('/api/v1/health', { signal })
  },

  inspectVideo(url: string, signal?: AbortSignal): Promise<InspectResponse> {
    return apiRequest<InspectResponse>('/api/v1/inspect', {
      method: 'POST',
      body: JSON.stringify({ url }),
      signal,
    })
  },

  createDownload(payload: CreateDownloadRequest, signal?: AbortSignal): Promise<JobResponse> {
    return apiRequest<JobResponse>('/api/v1/downloads', {
      method: 'POST',
      body: JSON.stringify(payload),
      signal,
    })
  },

  getJob(jobId: string, signal?: AbortSignal): Promise<JobResponse> {
    return apiRequest<JobResponse>(`/api/v1/downloads/${encodeURIComponent(jobId)}`, { signal })
  },

  getFileUrl(job: JobResponse): string | null {
    return job.download_url ? resolveApiUrl(job.download_url) : null
  },
}
