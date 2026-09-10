import { useEffect, useState } from 'react'
import { Button, Table } from '../components'
import type { TableColumn } from '../components'
import { useDataRevision } from '../hooks/useDataRevision'
import { useModal } from '../hooks/useModal'
import { overlayRegistry } from '../hooks/registry'
import { formatTime } from './types'
import type { ConversationRecord, ConversationPage } from './types'

function StatusLight({ status }: { status: string }) {
  const normalized = status.toLowerCase().replaceAll(' ', '_')
  const state = ['completed', 'complete', 'continued'].includes(normalized) ? 'complete'
    : ['live', 'running', 'ongoing'].includes(normalized) ? 'ongoing'
    : ['needs_review', 'failed', 'failure', 'incorrect', 'error', 'done_incorrectly'].includes(normalized) ? 'failed'
    : 'processing'
  const label = state === 'failed' ? 'Failed or incorrect' : state === 'complete' ? 'Complete' : state === 'ongoing' ? 'Ongoing' : 'Processing'
  return <span className={`conversation-status-light conversation-status-light--${state}`} role="img" aria-label={label} title={label} />
}

const columns: TableColumn<ConversationRecord>[] = [
  { id: 'status', name: <span className="ui-sr-only">Status</span>, data: row => <StatusLight status={row.status} />, className: 'conversation-status-cell', headerClassName: 'conversation-status-cell', align: 'center', style: { width: 48 } },
  { id: 'name', name: 'Conversation', data: 'name', className: 'conversation-name' },
  { id: 'start', name: 'Started', data: row => formatTime(row.start_time), className: 'table-date' },
  { id: 'end', name: 'Ended', data: row => formatTime(row.end_time), className: 'table-date' },
]
const pageSize = 20
export function ConversationTable({ practice }: { practice: string }) {
  const { openModal } = useModal()
  const externalRevision = useDataRevision()
  const [offset, setOffset] = useState(0)
  const [revision, setRevision] = useState(0)
  const [result, setResult] = useState<{ key: string; page?: ConversationPage; error?: string } | null>(null)
  const key = `${practice}:${offset}:${revision}:${externalRevision}`
  const loading = result?.key !== key
  const page = loading ? undefined : result?.page
  const error = loading ? undefined : result?.error
  useEffect(() => {
    const controller = new AbortController()
    fetch(`/api/practices/${encodeURIComponent(practice)}/conversations?limit=${pageSize}&offset=${offset}`, { credentials: 'include', signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ? 'Your session is no longer valid for this practice. Sign out and sign in again.' : 'Could not load conversations. Please try again.')
        return response.json() as Promise<ConversationPage>
      })
      .then(page => {
        if (offset > 0 && offset >= page.total) setOffset(0)
        else setResult({ key, page })
      })
      .catch((cause: unknown) => { if (!controller.signal.aborted) setResult({ key, error: cause instanceof Error ? cause.message : 'Could not load conversations.' }) })
    return () => controller.abort()
  }, [practice, offset, key])
  return <div>
    {error && <p className="error table-error" role="alert">{error}</p>}
    <Table data={page?.items ?? []} columns={columns} rowKey={row => row.id}
      caption="Practice conversation records" loading={loading} rowActionColumn="name"
      emptyMessage={error ? 'Records are currently unavailable.' : 'No conversations yet. Completed simulator runs will appear here.'}
      onRowClick={row => openModal(overlayRegistry.conversationDetails, row)} rowLabel={row => `View ${row.name}`}
      header={{ title: 'Conversations', subtitle: 'Call records for your practice. Select a row to view its details.', actions: <Button variant="outline" size="sm" disabled={loading} onClick={() => setRevision(value => value + 1)}>Refresh</Button> }}
      footer={{ subtitle: page ? `${page.items.length ? offset + 1 : 0}–${offset + page.items.length} of ${page.total} conversations` : loading ? 'Loading…' : 'Unable to load records', actions: <>
        <Button variant="ghost" size="sm" disabled={loading || offset === 0} onClick={() => setOffset(value => Math.max(0, value - pageSize))}>Previous</Button>
        <Button variant="outline" size="sm" disabled={loading || !page || offset + pageSize >= page.total} onClick={() => setOffset(value => value + pageSize)}>Next</Button>
      </> }} />
  </div>
}
