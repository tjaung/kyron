import type { Key } from 'react'
import { Button, Table } from '../components'
import type { TableColumn } from '../components'
import { usePracticeRecords } from '../hooks/usePracticeRecords'

export function DirectoryTable<Row>({ resource, title, columns, rowKey }: {
  resource: 'patients' | 'providers'; title: string; columns: TableColumn<Row>[]; rowKey: (row: Row) => Key
}) {
  const { data, total, error, loading, offset, limit, setOffset, refresh } = usePracticeRecords<Row>(resource)
  return <>
    {error && <p role="alert" className="error table-error">{error}</p>}
    <Table data={data} columns={columns} rowKey={rowKey} loading={loading} caption={`Practice ${resource}`}
      emptyMessage={error ? 'Records are currently unavailable.' : `No ${resource} are linked to this practice yet.`}
      header={{ title, subtitle: `${title} linked to your current practice.`, actions: <Button variant="outline" size="sm" disabled={loading} onClick={refresh}>Refresh</Button> }}
      footer={{ subtitle: loading ? 'Loading…' : error ? 'Unable to load records' : `${data.length ? offset + 1 : 0}–${offset + data.length} of ${total} ${resource}`, actions: <>
        <Button variant="ghost" size="sm" disabled={loading || offset === 0} onClick={() => setOffset(value => Math.max(0, value - limit))}>Previous</Button>
        <Button variant="outline" size="sm" disabled={loading || !!error || offset + limit >= total} onClick={() => setOffset(value => value + limit)}>Next</Button>
      </> }} />
  </>
}
