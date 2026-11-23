import type { ApiErrorBody } from './types'

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').trim().replace(/\/+$/, '')

export class ApiRequestError extends Error {
  readonly code: string
  readonly status: number
  readonly details: Record<string, unknown> | null

  constructor(
    code: string,
    message: string,
    status: number,
    details: Record<string, unknown> | null = null,
  ) {
    super(message)
    this.name = 'ApiRequestError'
    this.code = code
    this.status = status
    this.details = details
  }
}

export class ApiNetworkError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ApiNetworkError'
  }
}

interface RequestOptions extends Omit<RequestInit, 'signal'> {
  signal?: AbortSignal
  timeoutMs?: number
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function readErrorBody(value: unknown): ApiErrorBody['error'] {
  const body = asRecord(value)
  const error = asRecord(body?.error)
  const code = typeof error?.code === 'string' && error.code ? error.code : 'UNEXPECTED_RESPONSE'
  const message =
    typeof error?.message === 'string' && error.message
      ? error.message
      : 'VidMax returned an unexpected response.'
  const details = asRecord(error?.details)
  return { code, message, details }
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { timeoutMs = 15000, signal: externalSignal, ...requestInit } = options
  const controller = new AbortController()
  let timedOut = false

  const abortFromCaller = () => controller.abort()
  externalSignal?.addEventListener('abort', abortFromCaller, { once: true })

  const timeout = window.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)

  try {
    const headers = new Headers(requestInit.headers)
    if (!headers.has('Accept')) headers.set('Accept', 'application/json')
    if (requestInit.body && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json')
    }

    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...requestInit,
      headers,
      signal: controller.signal,
    })

    if (!response.ok) {
      let payload: unknown = null
      try {
        payload = await response.json()
      } catch {
        payload = null
      }
      const error = readErrorBody(payload)
      throw new ApiRequestError(error.code, error.message, response.status, error.details)
    }

    return (await response.json()) as T
  } catch (error) {
    if (externalSignal?.aborted) throw error
    if (timedOut) throw new ApiNetworkError('The server took too long to respond. Try again.')
    if (error instanceof ApiRequestError) throw error
    throw new ApiNetworkError('Can’t reach VidMax. Check that the local server is running.')
  } finally {
    window.clearTimeout(timeout)
    externalSignal?.removeEventListener('abort', abortFromCaller)
  }
}

export function resolveApiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path
  const base = API_BASE_URL || window.location.origin
  try {
    return new URL(path, base).toString()
  } catch {
    return path
  }
}
