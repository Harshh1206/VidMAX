import { ApiNetworkError, ApiRequestError } from '../api/client'
import type { CapabilityStatus, JobStatus, Platform } from '../api/types'

export function describeError(error: unknown): string {
  if (error instanceof ApiNetworkError) return error.message

  if (error instanceof ApiRequestError) {
    switch (error.code) {
      case 'INVALID_URL':
        return 'That link doesn’t look right. Paste a full https:// link from YouTube or Facebook.'
      case 'UNSUPPORTED_PLATFORM':
        return 'VidMax currently recognizes YouTube and Facebook links.'
      case 'METADATA_UNAVAILABLE':
        return 'Details for that link aren’t available right now. Check the link and try again.'
      case 'DOWNLOAD_NOT_AUTHORIZED':
        return 'Saving from this provider isn’t available on this server yet.'
      case 'VALIDATION_ERROR':
        return 'That link is too long or incomplete. Check it and try again.'
      case 'JOB_EXPIRED':
        return 'That saved file has expired. Inspect the link again to start fresh.'
      case 'JOB_NOT_FOUND':
        return 'That job is no longer on this server. Inspect the link again.'
      default:
        return error.message || 'VidMax couldn’t complete that request.'
    }
  }

  return 'Something went wrong. Try again.'
}

export function platformLabel(platform: Platform): string {
  if (platform === 'youtube') return 'YouTube'
  if (platform === 'facebook') return 'Facebook'
  return 'Local file'
}

export function capabilityLabel(status: CapabilityStatus): string {
  switch (status) {
    case 'available':
      return 'Ready'
    case 'configured_unverified':
      return 'Set up, not verified'
    case 'not_configured':
      return 'Not set up'
    case 'unavailable':
      return 'Unavailable'
    case 'not_implemented':
      return 'Not available yet'
  }
}

export function jobStatusLabel(status: JobStatus): string {
  switch (status) {
    case 'queued':
      return 'Waiting to start'
    case 'processing':
      return 'Saving your video'
    case 'completed':
      return 'Ready to download'
    case 'failed':
      return 'Couldn’t finish'
    case 'cancelled':
      return 'Cancelled'
    case 'expired':
      return 'Expired'
  }
}

export function savingMessage(platform: Platform, status: CapabilityStatus): string {
  const name = platformLabel(platform)
  switch (status) {
    case 'available':
      return `${name} videos can be saved on this server.`
    case 'configured_unverified':
      return `Saving from ${name} is set up, but hasn’t been verified yet.`
    case 'not_configured':
      return `Saving from ${name} isn’t configured on this server.`
    case 'unavailable':
      return `Saving from ${name} is currently unavailable.`
    case 'not_implemented':
      return `Direct saving from ${name} is still being set up. Nothing will be downloaded yet.`
  }
}
