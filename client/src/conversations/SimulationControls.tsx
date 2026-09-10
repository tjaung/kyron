import { useEffect, useRef, useState } from 'react'
import { Button, Dropdown } from '../components'
import { refreshData, useDataRevision } from '../hooks/useDataRevision'

type Sample = { conversation_id: string; name: string; is_used: boolean }
export function SimulationControls({ practice }: { practice: string }) {
  const lastStatus = useRef('loading')
  const [samples, setSamples] = useState<Sample[]>([])
  const [selected, setSelected] = useState('random')
  const [status, setStatus] = useState('loading')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [pollError, setPollError] = useState('')
  const [message, setMessage] = useState('')
  const revision = useDataRevision()
  const base = `/api/practices/${encodeURIComponent(practice)}`
  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {
        const [listResponse, stateResponse] = await Promise.all([
          fetch(`${base}/simulations`, { credentials: 'include', signal: controller.signal }),
          fetch(`${base}/simulations/status`, { credentials: 'include', signal: controller.signal }),
        ])
        if (!listResponse.ok || !stateResponse.ok) throw new Error('Could not load simulation status. Retrying…')
        const [list, state] = await Promise.all([listResponse.json() as Promise<Sample[]>, stateResponse.json() as Promise<{ status: string }>])
        if (controller.signal.aborted) return
        setSamples(list.filter(row => !row.is_used))
        if (lastStatus.current === 'running' && state.status !== 'running') setMessage(state.status === 'failed' ? 'Simulation failed. Check the simulator logs, then retry an unused sample.' : 'Simulation finished.')
        lastStatus.current = state.status
        setStatus(state.status)
        setPollError('')
      } catch (cause) {
        if (!controller.signal.aborted) { setStatus('unavailable'); setPollError(cause instanceof Error ? cause.message : 'Simulator unavailable.') }
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(poll, 2000)
      }
    }
    void poll()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [base, revision])
  // Refresh the records while the simulator streams and once it finishes.
  useEffect(() => {
    if (status !== 'running' && status !== 'completed' && status !== 'failed') return
    refreshData()
    if (status !== 'running') return
    const timer = setInterval(refreshData, 5000)
    return () => clearInterval(timer)
  }, [status])
  const busy = pending || ['loading', 'running', 'busy', 'maintenance', 'unavailable'].includes(status)
  const value = selected === 'random' || samples.some(row => row.conversation_id === selected) ? selected : 'random'
  async function perform(action: 'run' | 'clear') {
    setPending(true); setMessage(''); setError('')
    try {
      const path = action === 'clear' ? '/demo/clear' : value === 'random' ? '/simulations/random' : `/simulations/${value}/run`
      const response = await fetch(base + path, { method: 'POST', credentials: 'include' })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'The request could not be completed.')
      setMessage(action === 'clear' ? body.message : 'Local-model simulation started. Calls, analysis, and any follow-ups will appear here.')
      if (action === 'run') setStatus('running')
      else setSelected('random')
      refreshData()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Request failed.') }
    finally { setPending(false) }
  }
  return <section className="simulation-controls" aria-label="Simulation controls">
    <div className="simulation-run">
      <Dropdown label="Simulation scenario" value={value} disabled={busy || !samples.length} onChange={event => setSelected(event.target.value)}>
        <option value="random">Select random scenario</option>
        {samples.map(sample => <option key={sample.conversation_id} value={sample.conversation_id}>{sample.name}</option>)}
      </Dropdown>
      <Button disabled={busy || !samples.length} onClick={() => perform('run')}>{status === 'running' ? 'Simulation running…' : 'Run simulation'}</Button>
    </div>
    <Button variant="outline" size="sm" disabled={busy} onClick={() => perform('clear')}>Clear simulated data</Button>
    <p className="simulation-note">Clear removes conversation history across all practices and resets every sample to unused.</p>
    {!samples.length && !busy && <p className="simulation-note">No unused samples. Clear simulated data to run them again.</p>}
    {status === 'maintenance' && <p role="status">Demo data maintenance is in progress.</p>}
    {message && <p role="status" className="simulation-note">{message}</p>}
    {(error || pollError) && <p role="alert" className="error">{error || pollError}</p>}
  </section>
}
