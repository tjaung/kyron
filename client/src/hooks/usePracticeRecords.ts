import { useEffect, useState } from 'react'
import { useAuth } from '../auth/useAuth'

export function usePracticeRecords<Row>(resource: 'patients' | 'providers') {
  const { session } = useAuth()
  const practice = session?.practice.slug
  const [offset, setOffset] = useState(0)
  const [revision, setRevision] = useState(0)
  const [result, setResult] = useState<{ key: string; items?: Row[]; total?: number; error?: string } | null>(null)
  const limit = 20
  const key = `${practice}:${resource}:${offset}:${revision}`
  const loading = result?.key !== key
  useEffect(() => {
    if (!practice) return
    const controller = new AbortController()
    fetch(`/api/practices/${encodeURIComponent(practice)}/${resource}?limit=${limit}&offset=${offset}`, { credentials: 'include', signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ? 'Your session is no longer valid. Sign out and sign in again.' : `Could not load ${resource}. Please try again.`)
        return response.json() as Promise<{ items: Row[]; total: number }>
      })
      .then(page => setResult({ key, ...page }))
      .catch((cause: unknown) => { if (!controller.signal.aborted) setResult({ key, error: cause instanceof Error ? cause.message : 'Could not load records.' }) })
    return () => controller.abort()
  }, [practice, resource, offset, key])
  return { data: loading ? [] : result?.items ?? [], total: loading ? 0 : result?.total ?? 0,
    error: loading ? undefined : result?.error, loading, offset, limit, setOffset,
    refresh: () => setRevision(value => value + 1) }
}
