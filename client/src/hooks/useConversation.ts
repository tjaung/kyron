import { useEffect, useState } from 'react'
import type { ConversationRecord } from '../conversations/types'

type Turn = { transcript_id: string; speaker: string; transcript: string; turn_index: number; start_time: string; end_time: string | null }
type Detail = ConversationRecord & { last_sequence: number; source_conversation_id: string; practice_name: string; patient_name: string | null; provider_name: string | null; medication_name: string | null }
type Snapshot = { record: Detail; transcripts: Turn[]; cursor: number }
type Event = { conversation_id: string; sequence: number; type: string; transcript_id?: string; speaker?: string; turn_index?: number; occurred_at: string; status?: string; delta?: string }

export function useConversation(practice: string, id: string) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [connection, setConnection] = useState('Loading conversation…')
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    let stream: EventSource | undefined
    const base = `/api/practices/${encodeURIComponent(practice)}`
    async function start() {
      try {
        const response = await fetch(`${base}/conversations/${id}`, { credentials: 'include', signal: controller.signal })
        if (!response.ok) throw new Error(response.status === 404 ? 'This conversation is no longer available.' : 'Could not load this conversation. Check your session and try again.')
        const initial = await response.json() as Snapshot
        if (controller.signal.aborted) return
        setSnapshot(initial); setError('')
        if (['completed', 'continued', 'needs_review', 'failed'].includes(initial.record.status)) { setConnection('Recorded transcript'); return }
        setConnection('Connecting to live transcript…')
        stream = new EventSource(`${base}/events?conversation_id=${id}&after=${initial.cursor}`, { withCredentials: true })
        stream.onopen = () => setConnection('Live updates connected')
        stream.onerror = () => setConnection('Connection interrupted. Reconnecting…')
        stream.onmessage = message => {
          const event = JSON.parse(message.data) as Event
          if (event.conversation_id !== id) return
          setSnapshot(previous => {
            if (!previous || event.sequence <= previous.record.last_sequence) return previous
            let transcripts = previous.transcripts
            if (event.type === 'transcript.started') transcripts = [...transcripts, {
              transcript_id: event.transcript_id!, speaker: event.speaker!, transcript: '',
              turn_index: event.turn_index!, start_time: event.occurred_at, end_time: null,
            }]
            if (event.type === 'transcript.word') transcripts = transcripts.map(turn => turn.transcript_id === event.transcript_id ? { ...turn, transcript: turn.transcript + event.delta } : turn)
            if (event.type === 'transcript.completed') transcripts = transcripts.map(turn => turn.transcript_id === event.transcript_id ? { ...turn, end_time: event.occurred_at } : turn)
            const record = { ...previous.record, last_sequence: event.sequence }
            if (event.type === 'conversation.ended') { record.status = 'ended'; record.end_time = event.occurred_at }
            if (event.type === 'replay.completed') record.status = 'completed'
            if (event.type === 'conversation.finalized' && event.status) {
              record.status = event.status
              if (event.status === 'failed') {
                record.end_time = record.end_time ?? event.occurred_at
                transcripts = transcripts.map(turn => turn.end_time ? turn : { ...turn, end_time: event.occurred_at })
              }
            }
            return { ...previous, record, transcripts }
          })
          if (event.type === 'replay.completed' || (event.type === 'conversation.finalized' && ['completed','continued','needs_review','failed'].includes(event.status ?? ''))) { stream?.close(); setConnection('Recorded transcript') }
        }
      } catch (cause) {
        if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Could not load conversation.')
      }
    }
    void start()
    return () => { controller.abort(); stream?.close() }
  }, [practice, id, attempt])
  return { snapshot, connection, error, retry: () => setAttempt(value => value + 1) }
}
