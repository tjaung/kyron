import { useAuth } from '../auth/useAuth'
import type { TableColumn } from '../components'
import { DirectoryTable } from './DirectoryTable'

type Patient = { patient_id: string; first_name: string; last_name: string; date_of_birth: string; medical_record_number: string }
const columns: TableColumn<Patient>[] = [
  { id: 'name', name: 'Patient', data: row => `${row.first_name} ${row.last_name}` },
  { id: 'dob', name: 'Date of birth', data: 'date_of_birth', className: 'table-date' },
  { id: 'mrn', name: 'Medical record number', data: 'medical_record_number' },
]
export function PatientsPage() {
  const { session } = useAuth()
  return <div className="practice-page"><p className="eyebrow">{session?.practice.name}</p><h1>Patients</h1>
    <DirectoryTable<Patient> resource="patients" title="Patients" columns={columns} rowKey={row => row.patient_id} />
  </div>
}
