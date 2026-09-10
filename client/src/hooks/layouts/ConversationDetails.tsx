import { useRef, useState, useEffect } from 'react'
import { Button, Tabs } from '../../components'
import { useAuth } from '../../auth/useAuth'
import { formatTime } from '../../conversations/types'
import type { ConversationRecord } from '../../conversations/types'
import type { OverlayLayoutProps } from '../overlayRegistry'
import { useConversation } from '../useConversation'

import { refreshData } from '../useDataRevision'
import { useConversationActions } from '../useConversationActions'
import { ConversationActions } from '../../conversations/ConversationActions'

const tabs = ['Details', 'Transcript', 'Actions', 'Evaluation'] as const
export function ConversationDetails({ data }: OverlayLayoutProps<ConversationRecord>) {
  const { session } = useAuth()
  const { snapshot, connection, error, retry } = useConversation(session!.practice.slug, data.id)
  const actions = useConversationActions(session!.practice.slug, data.id)
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisMessage, setAnalysisMessage] = useState('')
  const [analysisError, setAnalysisError] = useState('')
  const [cancelling, setCancelling] = useState(false)
  const [cancelMessage, setCancelMessage] = useState('')
  const [cancelError, setCancelError] = useState('')
  const [cancelled, setCancelled] = useState(false)
  const [tab, setTab] = useState<typeof tabs[number]>('Details')
  const feed = useRef<HTMLDivElement>(null)
  const follow = useRef(true)
  useEffect(() => {
    if (tab === 'Transcript' && follow.current && feed.current) feed.current.scrollTop = feed.current.scrollHeight
  }, [snapshot, tab])
  const record = snapshot?.record
  async function cancel() {
    setCancelling(true); setCancelError('')
    try {
      const response = await fetch(`/api/practices/${encodeURIComponent(session!.practice.slug)}/conversations/${data.id}/cancel`, { method: 'POST', credentials: 'include' })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Could not cancel the conversation.')
      setCancelled(true); setCancelMessage(body.message)
      refreshData(); retry(); actions.refresh()
    } catch (cause) { setCancelError(cause instanceof Error ? cause.message : 'Could not cancel the conversation.'); retry() }
    finally { setCancelling(false) }
  }
  async function rerunAnalysis() {
    setAnalyzing(true); setAnalysisMessage(''); setAnalysisError('')
    try {
      const response = await fetch(`/api/practices/${encodeURIComponent(session!.practice.slug)}/conversations/${data.id}/analyze`, { method: 'POST', credentials: 'include' })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Analysis failed. You can retry using this saved transcript.')
      setAnalysisMessage(body.dispatch?.status === 'pending' ? `Analysis saved. Follow-up pending: ${body.dispatch.detail}` : 'Analysis saved and chosen simulation actions processed.')
    } catch (cause) { setAnalysisError(cause instanceof Error ? cause.message : 'Could not analyze the transcript.') }
    finally { setAnalyzing(false); actions.refresh(); retry(); refreshData() }
  }
  const metadata = record ? [
    ['Conversation', record.name], ['Status', record.status], ['Practice', record.practice_name],
    ['Patient', record.patient_name], ['Provider', record.provider_name], ['Medication', record.medication_name],
    ['Started', formatTime(record.start_time)], ['Ended', formatTime(record.end_time)],
    ['Record ID', record.id], ['Source sample ID', record.source_conversation_id], ['Patient ID', record.patient_id],
    ['Provider ID', record.provider_id], ['Patient practice ID', record.patient_practice_id], ['Provider practice ID', record.provider_practice_id], ['Prescription ID', record.prescription_id],
  ] : []
  return <div className="conversation-modal">
    <div className="transcript-toolbar">
      <p className="conversation-modal-name">{record?.name ?? data.name}</p>
      {!cancelled && (record?.status ?? data.status) === 'live' && <Button variant="danger" size="sm" disabled={cancelling} onClick={cancel}>{cancelling ? 'Cancelling…' : 'Cancel simulation'}</Button>}
    </div>
    {cancelMessage && <p role="status" className="simulation-note">{cancelMessage}</p>}
    {cancelError && <p role="alert" className="error">{cancelError}</p>}
    {error && <div role="alert" className="error">{error} <Button size="sm" variant="outline" onClick={retry}>Retry</Button></div>}
    <Tabs value={tab} onValueChange={setTab} label="Conversation sections" className="conversation-content-tabs" panelClassName="conversation-panel"
      items={tabs.map(name => ({ value: name, label: name, content: <>
      {name === 'Details' && (record ? <dl className="conversation-metadata">{metadata.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value ?? '—'}</dd></div>)}</dl> : <p role="status">Loading metadata…</p>)}
      {name === 'Transcript' && <>
        <div className="transcript-toolbar"><span role="status">{connection}</span><Button size="sm" variant="ghost" onClick={() => { follow.current = true; if (feed.current) feed.current.scrollTop = feed.current.scrollHeight }}>Jump to latest</Button></div>
        <div className="conversation-transcript" ref={feed} onScroll={event => { const element = event.currentTarget; follow.current = element.scrollHeight - element.scrollTop - element.clientHeight < 60 }}>
          {!snapshot?.transcripts.length && <p className="simulation-note">{snapshot ? 'No transcript yet. New speech will appear here as it arrives.' : 'Loading transcript…'}</p>}
          {snapshot?.transcripts.map(turn => <article key={turn.transcript_id} className={`transcript-turn ${turn.speaker === 'ai_agent' ? 'transcript-turn--ai' : ''}`}>
            <header><strong>{turn.speaker.replaceAll('_', ' ')}</strong><time dateTime={turn.start_time}>{new Date(turn.start_time).toLocaleTimeString()}</time>{!turn.end_time && <span>Speaking</span>}</header>
            <p>{turn.transcript || '…'}</p>
          </article>)}
        </div>
      </>}
      {name === 'Actions' && <>{actions.error && <p role="alert" className="error">{actions.error}</p>}<ConversationActions data={actions.data} /></>}
      {name === 'Evaluation' && <div className="ui-stack">
        <div><Button onClick={rerunAnalysis} disabled={analyzing || !record?.end_time || actions.data?.status === 'processing'}>{analyzing ? 'Analyzing transcript…' : 'Rerun analysis'}</Button></div>
        {analysisMessage && <p role="status">{analysisMessage}</p>}
        {analysisError && <p role="alert" className="error">{analysisError}</p>}
        <p>{actions.data?.analysis?.summary ?? (actions.data?.status === 'failed' ? 'Conversation processing failed. Check the simulator and local model before retrying.' : 'Analysis will appear after the speakers finish.')}</p>
        {actions.data?.analysis?.metrics && <>
          <p>Sentiment: <strong>{actions.data.analysis.overall_sentiment ?? 'Not assessed'}</strong> · Decision: <strong>{actions.data.analysis.decision?.replaceAll('_', ' ')}</strong></p>
          <dl className="conversation-metadata">{Object.entries(actions.data.analysis.metrics ?? {}).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{Array.isArray(value) ? value.join(', ') || 'None' : String(value)}</dd></div>)}</dl>
          <p className="simulation-note">{actions.data.analysis.model && `Generated locally with ${actions.data.analysis.model}. `}Checklist completion reflects recorded simulation evidence.</p>
        </>}
      </div>}
    </> }))} />
  </div>
}
