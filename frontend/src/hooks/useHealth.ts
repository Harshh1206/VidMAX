import { useCallback, useEffect, useState } from 'react'
import { vidmaxApi } from '../api/vidmaxApi'
import type { HealthResponse } from '../api/types'
import { describeError } from '../lib/labels'

export function useHealth() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback((signal?: AbortSignal) => {
    return vidmaxApi
      .getHealth(signal)
      .then((result) => {
        setHealth(result)
        setError(null)
      })
      .catch((cause: unknown) => {
        if (!signal?.aborted) setError(describeError(cause))
      })
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    void reload(controller.signal)
    return () => controller.abort()
  }, [reload])

  return { health, error }
}
