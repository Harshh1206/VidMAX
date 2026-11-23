export type Platform = 'youtube' | 'facebook' | 'local'

export type CapabilityStatus =
  | 'available'
  | 'configured_unverified'
  | 'not_configured'
  | 'unavailable'
  | 'not_implemented'

export type JobStatus =
  | 'queued'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'expired'

export interface CapabilityResponse {
  status: CapabilityStatus
  reason: string
}

export interface ProviderReadinessResponse {
  platform: Platform
  url_validation: CapabilityResponse
  metadata_inspection: CapabilityResponse
  authorized_download: CapabilityResponse
  fully_functional: boolean
}

export interface HealthResponse {
  status: string
  version: string
  environment: string
  database: string
  providers: ProviderReadinessResponse[]
}

export interface VideoFormatResponse {
  id: string
  label: string
  kind: string
  container: string
  codec: string
  width: number | null
  height: number | null
  bitrate_kbps: number | null
  fps: number | null
  filesize_bytes: number | null
}

export interface InspectRequest {
  url: string
}

export interface InspectResponse {
  platform: Platform
  canonical_url: string
  video_id: string | null
  title: string | null
  author: string | null
  thumbnail_url: string | null
  duration_seconds: number | null
  metadata_source: string
  metadata_available: boolean
  downloadable: boolean
  download_capability_status: CapabilityStatus
  download_capability_reason: string
  formats: VideoFormatResponse[]
  recommended_format_id: string | null
}

export interface DownloadAuthorizationRequest {
  authorized?: boolean
  basis?: string | null
  reference?: string | null
}

export interface CreateDownloadRequest {
  url: string
  target_format?: string | null
  format_id?: string | null
  authorization?: DownloadAuthorizationRequest
}

export interface JobResponse {
  id: string
  platform: Platform
  source_url: string
  status: JobStatus
  progress: number
  file_name: string | null
  created_at: string
  updated_at: string
  expires_at: string | null
  error_message: string | null
  download_url: string | null
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    details: Record<string, unknown> | null
  }
}
