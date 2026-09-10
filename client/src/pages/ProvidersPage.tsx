import { useAuth } from '../auth/useAuth'
import type { TableColumn } from '../components'
import { DirectoryTable } from './DirectoryTable'

type Provider = { provider_id: string; first_name: string; last_name: string; npi: string | null }
const columns: TableColumn<Provider>[] = [
  { id: 'name', name: 'Provider', data: row => `${row.first_name} ${row.last_name}` },
  { id: 'npi', name: 'NPI', data: 'npi' },
  { id: 'id', name: 'Provider ID', data: 'provider_id', className: 'table-date' },
]
export function ProvidersPage() {
  const { session } = useAuth()
  return <div className="practice-page"><p className="eyebrow">{session?.practice.name}</p><h1>Providers</h1>
    <DirectoryTable<Provider> resource="providers" title="Providers" columns={columns} rowKey={row => row.provider_id} />
  </div>
}
