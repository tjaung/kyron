import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { BrowserRouter, Link, Navigate, Outlet, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import { AuthProvider } from './auth/AuthProvider'
import { useAuth } from './auth/useAuth'
import type { Practice } from './auth/types'
import { Button, Card, Form, TextInput, Dropdown, Sidebar } from './components'
import { OverlayProvider } from './hooks/OverlayProvider'
import { PracticeNavbar } from './auth/PracticeNavbar'
import { ConversationsPage } from './pages/ConversationsPage'
import { PatientsPage } from './pages/PatientsPage'
import { ProvidersPage } from './pages/ProvidersPage'
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

  return <Card variant="elevated" className="auth-card">
    <p className="eyebrow">PROVIDER PORTAL</p>
    <h1>Choose your practice</h1>
    <p className="muted">Select the practice you’re signing in to.</p>
    <Dropdown label="Practice" id="practice" defaultValue="" disabled={!practices.length}
      onChange={event => navigate(`/${event.target.value}/auth`)}>
      <option value="" disabled>{practices.length ? 'Select a practice' : 'Loading practices…'}</option>
      {practices.map(practice => <option key={practice.practice_id} value={practice.slug}>{practice.name}</option>)}
    </Dropdown>
    {error && <p className="error" role="alert">{error}</p>}
  </Card>
}

function TenantLayout() {
  const { practice = '' } = useParams()
  return <AuthProvider key={practice} slug={practice}><TenantContent /></AuthProvider>
}

function TenantContent() {
  const { loading, error } = useAuth()
  if (loading) return <Card variant="elevated" className="auth-card" role="status">Checking your session…</Card>
  if (error) return <Card variant="elevated" className="auth-card"><p role="alert">{error}</p><Link to="/">Choose a practice</Link></Card>
  return <OverlayProvider><PracticeNavbar /><Outlet /></OverlayProvider>
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

  return <main className="auth-shell"><Card variant="elevated" className="auth-card">
    <Link className="back-link" to="/">← Change practice</Link>
    <p className="eyebrow">{practice?.name}</p>
    <h1>Welcome back</h1>
    <p className="muted">Sign in with your practitioner details.</p>
    <Form onSubmit={submit}>
      <TextInput label="Username" id="username" name="username" autoComplete="username" autoCapitalize="none" spellCheck={false}
        placeholder="firstname.lastname" required value={username} onChange={event => setUsername(event.target.value)} />
      <TextInput label="Password" id="password" name="password" type="password" autoComplete="current-password" required
        value={password} onChange={event => setPassword(event.target.value)} />
      {error && <p className="error" role="alert">{error}</p>}
      <Button fullWidth type="submit" disabled={submitting}>{submitting ? 'Signing in…' : 'Sign in'}</Button>
    </Form>
  </Card></main>
}

function PracticeLayout() {
  const { session, practice } = useAuth()
  const [sidebarOpen, setSidebarOpen] = useState(() => window.matchMedia('(min-width: 900px)').matches)
  if (!session) return <Navigate to={`/${practice?.slug}/auth`} replace />
  const base = `/${session.practice.slug}`
  return <div className="practice-workspace">
    <Sidebar open={sidebarOpen} onOpenChange={setSidebarOpen} links={[
      { label: 'Conversations', to: `${base}/conversations`, icon: <svg viewBox="0 0 24 24"><path d="M5 4h14a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H9l-5 4V5a1 1 0 0 1 1-1Z" /><path d="M8 8h8M8 12h6" /></svg> },
      { label: 'Patients', to: `${base}/patients`, icon: <svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="4" /><path d="M4 21v-2a8 8 0 0 1 16 0v2" /></svg> },
      { label: 'Providers', to: `${base}/providers`, icon: <svg viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="3" /><path d="M12 8v8M8 12h8" /></svg> },
    ]} />
    <main className="practice-shell"><Outlet /></main>
  </div>
}

function PublicLayout() {
  return <><header className="app-header"><Link className="app-brand" to="/">kyron<span>provider portal</span></Link></header><main className="auth-shell"><Outlet /></main></>
}
export default function App() {
  return <BrowserRouter><Routes>
    <Route element={<PublicLayout />}>
      <Route path="/" element={<PracticePicker />} />
      <Route path="/auth" element={<PracticePicker />} />
    </Route>
    <Route path="/:practice" element={<TenantLayout />}>
      <Route element={<PracticeLayout />}>
        <Route index element={<Navigate to="conversations" replace />} />
        <Route path="conversations" element={<ConversationsPage />} />
        <Route path="patients" element={<PatientsPage />} />
        <Route path="providers" element={<ProvidersPage />} />
      </Route>
      <Route path="auth" element={<LoginPage />} />
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></BrowserRouter>
}
