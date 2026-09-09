import { useEffect, useState } from 'react'
import { Button, Table } from '../components'
import type { TableColumn } from '../components'
import { useDrawer } from '../hooks/useDrawer'
import { overlayRegistry } from '../hooks/registry'
import { formatTime } from './types'
import type { ConversationRecord, ConversationPage } from './types'

const columns: TableColumn<ConversationRecord>[] = [
  { id: 'name', name: 'Conversation', data: 'name', className: 'conversation-name' },
  { id: 'status', name: 'Status', data: row => <span className={`status-badge ${row.status === 'live' ? 'status-badge--live' : ''}`}>{row.status}</span> },
  { id: 'start', name: 'Started', data: row => formatTime(row.start_time), className: 'table-date' },
  { id: 'end', name: 'Ended', data: row => formatTime(row.end_time), className: 'table-date' },
]
const pageSize = 20
export function ConversationTable({ practice }: { practice: string }) {
  const { openDrawer } = useDrawer()
  const [offset, setOffset] = useState(0)
  const [revision, setRevision] = useState(0)
  const [result, setResult] = useState<{ key: string; page?: ConversationPage; error?: string } | null>(null)
  const key = `${practice}:${offset}:${revision}`
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
      .then(page => setResult({ key, page }))
      .catch((cause: unknown) => { if (!controller.signal.aborted) setResult({ key, error: cause instanceof Error ? cause.message : 'Could not load conversations.' }) })
    return () => controller.abort()
  }, [practice, offset, key])
  return <div>
    {error && <p className="error table-error" role="alert">{error}</p>}
    <Table data={page?.items ?? []} columns={columns} rowKey={row => row.id}
      caption="Practice conversation records" loading={loading}
      emptyMessage={error ? 'Records are currently unavailable.' : 'No conversations yet. Completed simulator runs will appear here.'}
      onRowClick={row => openDrawer(overlayRegistry.conversationDetails, row)} rowLabel={row => `View ${row.name}`}
      header={{ title: 'Conversations', subtitle: 'Call records for your practice. Select a row to view its details.', actions: <Button variant="outline" size="sm" disabled={loading} onClick={() => setRevision(value => value + 1)}>Refresh</Button> }}
      footer={{ subtitle: page ? `${page.items.length ? offset + 1 : 0}–${offset + page.items.length} of ${page.total} conversations` : loading ? 'Loading…' : 'Unable to load records', actions: <>
        <Button variant="ghost" size="sm" disabled={loading || offset === 0} onClick={() => setOffset(value => Math.max(0, value - pageSize))}>Previous</Button>
        <Button variant="outline" size="sm" disabled={loading || !page || offset + pageSize >= page.total} onClick={() => setOffset(value => value + pageSize)}>Next</Button>
      </> }} />
  </div>
}
