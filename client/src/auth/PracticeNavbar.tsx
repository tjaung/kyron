import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../components'
import { useModal } from '../hooks/useModal'
import { overlayRegistry } from '../hooks/registry'
import { refreshData } from '../hooks/useDataRevision'
import { useAuth } from './useAuth'
export function PracticeNavbar() {
  const { session, logout } = useAuth()
  const { openModal } = useModal()
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [seeding, setSeeding] = useState(false)
  const [message, setMessage] = useState('')
  async function seedData() {
    if (!session) return
    setSeeding(true); setError(''); setMessage('')
    try {
      const response = await fetch(`/api/practices/${session.practice.slug}/demo/seed`, { method: 'POST', credentials: 'include' })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Could not seed data.')
      setMessage(body.message); refreshData()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not seed data.') }
    finally { setSeeding(false) }
  }
  async function signOut() {
    setError('')
    setSubmitting(true)
    try { await logout() }
    catch { setError('Could not sign out. Please try again.') }
    finally { setSubmitting(false) }
  }
  return <header className="app-header">
    <Link className="app-brand" to="/">kyron<span>provider portal</span></Link>
    {session && <nav className="profile-nav" aria-label="Account">
      <Button variant="secondary" size="sm" disabled={seeding} onClick={seedData}>{seeding ? 'Seeding data…' : 'Seed data'}</Button>
      <Button variant="ghost" className="profile-badge" aria-label="View profile" onClick={() => openModal(overlayRegistry.providerDetails, session)}>
        <span className="profile-avatar" aria-hidden="true">{session.provider.first_name[0]}{session.provider.last_name[0]}</span>
        <span className="profile-label"><strong>{session.provider.first_name} {session.provider.last_name}</strong><small>{session.practice.name}</small></span>
      </Button>
      <Link className="practice-switch" to="/">Change practice</Link>
      <Button variant="outline" size="sm" disabled={submitting} onClick={signOut}>{submitting ? 'Signing out…' : 'Sign out'}</Button>
      {message && <p role="status" className="navbar-message">{message}</p>}
      {error && <p role="alert" className="error">{error}</p>}
    </nav>}
  </header>
}
