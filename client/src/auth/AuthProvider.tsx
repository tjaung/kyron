import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { AuthContext } from './context'
import type { AuthSession, Practice } from './types'

export function AuthProvider({ slug, children }: { slug: string; children: ReactNode }) {
  const [practice, setPractice] = useState<Practice | null>(null)
  const [session, setSession] = useState<AuthSession | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const base = `/api/practices/${encodeURIComponent(slug)}`

  useEffect(() => {
    const controller = new AbortController()
    async function restore() {
      try {
        const details = await fetch(base, { signal: controller.signal })
        if (!details.ok) throw new Error(details.status === 404 ? 'Practice not found.' : 'Could not load practice.')
        const tenant: Practice = await details.json()
        const response = await fetch(`${base}/auth/me`, { credentials: 'include', signal: controller.signal })
        if (!response.ok && response.status !== 401 && response.status !== 403) {
          throw new Error('Could not verify your session. Please reload to try again.')
        }
        const restored: AuthSession | null = response.ok ? await response.json() : null
        if (!controller.signal.aborted) {
          setPractice(tenant)
          setSession(restored)
          setLoading(false)
        }
      } catch (cause) {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : 'Could not connect to the server.')
          setLoading(false)
        }
      }
    }
    void restore()
    return () => controller.abort()
  }, [base])

  async function login(username: string, password: string) {
    const response = await fetch(`${base}/auth/login`, {
      method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    if (!response.ok) {
      throw new Error(response.status === 401 ? 'Invalid username or password for this practice.' : 'Sign-in failed. Please try again.')
    }
    setSession(await response.json() as AuthSession)
  }

  async function logout() {
    const response = await fetch(`${base}/auth/logout`, { method: 'POST', credentials: 'include' })
    if (!response.ok) throw new Error('Could not sign out. Please try again.')
    setSession(null)
  }

  return <AuthContext.Provider value={{ practice, session, loading, error, login, logout }}>
    {children}
  </AuthContext.Provider>
}
