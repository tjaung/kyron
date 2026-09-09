import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { BrowserRouter, Link, Navigate, Outlet, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import { AuthProvider } from './auth/AuthProvider'
import { useAuth } from './auth/useAuth'
import type { Practice } from './auth/types'
import './App.css'

function PracticePicker() {
  const [practices, setPractices] = useState<Practice[]>([])
  const [error, setError] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/practices', { signal: controller.signal })
      .then(response => {
        if (!response.ok) throw new Error('Could not load practices. Please reload to try again.')
        return response.json() as Promise<Practice[]>
      })
      .then(setPractices)
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Could not load practices.')
      })
    return () => controller.abort()
  }, [])

  return <section className="auth-card">
    <p className="eyebrow">PROVIDER PORTAL</p>
    <h1>Choose your practice</h1>
    <p className="muted">Select the practice you’re signing in to.</p>
    <label htmlFor="practice">Practice</label>
    <select id="practice" defaultValue="" disabled={!practices.length}
      onChange={event => navigate(`/${event.target.value}/auth`)}>
      <option value="" disabled>{practices.length ? 'Select a practice' : 'Loading practices…'}</option>
      {practices.map(practice => <option key={practice.practice_id} value={practice.slug}>{practice.name}</option>)}
    </select>
    {error && <p className="error" role="alert">{error}</p>}
  </section>
}

function TenantLayout() {
  const { practice = '' } = useParams()
  return <AuthProvider key={practice} slug={practice}><TenantContent /></AuthProvider>
}

function TenantContent() {
  const { loading, error } = useAuth()
  if (loading) return <section className="auth-card" role="status">Checking your session…</section>
  if (error) return <section className="auth-card"><p role="alert">{error}</p><Link to="/">Choose a practice</Link></section>
  return <Outlet />
}

function LoginPage() {
  const { practice, session, login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  if (session && practice) return <Navigate to={`/${practice.slug}`} replace />

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try { await login(username, password) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Sign-in failed.') }
    finally { setSubmitting(false) }
  }

  return <section className="auth-card">
    <Link className="back-link" to="/">← Change practice</Link>
    <p className="eyebrow">{practice?.name}</p>
    <h1>Welcome back</h1>
    <p className="muted">Sign in with your practitioner details.</p>
    <form onSubmit={submit}>
      <label htmlFor="username">Username</label>
      <input id="username" name="username" autoComplete="username" autoCapitalize="none" spellCheck={false}
        placeholder="firstname.lastname" required value={username} onChange={event => setUsername(event.target.value)} />
      <label htmlFor="password">Password</label>
      <input id="password" name="password" type="password" autoComplete="current-password" required
        value={password} onChange={event => setPassword(event.target.value)} />
      {error && <p className="error" role="alert">{error}</p>}
      <button type="submit" disabled={submitting}>{submitting ? 'Signing in…' : 'Sign in'}</button>
    </form>
  </section>
}

function PracticeHome() {
  const { session, practice, logout } = useAuth()
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  if (!session) return <Navigate to={`/${practice?.slug}/auth`} replace />

  async function signOut() {
    setSubmitting(true)
    try { await logout() }
    catch { setError('Could not sign out. Please try again.') }
    finally { setSubmitting(false) }
  }

  return <section className="auth-card">
    <p className="eyebrow">{session.practice.name}</p>
    <h1>You’re signed in</h1>
    <p className="muted">Welcome, {session.provider.first_name} {session.provider.last_name}.</p>
    <dl className="session-details">
      <div><dt>Practice</dt><dd>{session.practice.name}</dd></div>
      <div><dt>Username</dt><dd>{session.provider.username}</dd></div>
    </dl>
    {error && <p className="error" role="alert">{error}</p>}
    <button onClick={signOut} disabled={submitting}>{submitting ? 'Signing out…' : 'Sign out'}</button>
    <Link className="back-link" to="/">Choose another practice</Link>
  </section>
}

export default function App() {
  return <BrowserRouter>
    <header className="app-header"><Link to="/">kyron<span>provider portal</span></Link></header>
    <main className="auth-shell"><Routes>
      <Route path="/" element={<PracticePicker />} />
      <Route path="/auth" element={<PracticePicker />} />
      <Route path="/:practice" element={<TenantLayout />}>
        <Route index element={<PracticeHome />} />
        <Route path="auth" element={<LoginPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes></main>
  </BrowserRouter>
}
