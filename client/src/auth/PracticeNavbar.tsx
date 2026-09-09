import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../components'
import { useModal } from '../hooks/useModal'
import { overlayRegistry } from '../hooks/registry'
import { useAuth } from './useAuth'
export function PracticeNavbar() {
  const { session, logout } = useAuth()
  const { openModal } = useModal()
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
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
      <Button variant="ghost" className="profile-badge" aria-label="View profile" onClick={() => openModal(overlayRegistry.providerDetails, session)}>
        <span className="profile-avatar" aria-hidden="true">{session.provider.first_name[0]}{session.provider.last_name[0]}</span>
        <span className="profile-label"><strong>{session.provider.first_name} {session.provider.last_name}</strong><small>{session.practice.name}</small></span>
      </Button>
      <Link className="practice-switch" to="/">Change practice</Link>
      <Button variant="outline" size="sm" disabled={submitting} onClick={signOut}>{submitting ? 'Signing out…' : 'Sign out'}</Button>
      {error && <p role="alert" className="error">{error}</p>}
    </nav>}
  </header>
}
