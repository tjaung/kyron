export type ConversationRecord = {
  id: string
  name: string
  status: string
  start_time: string
  end_time: string | null
  patient_id: string | null
  provider_id: string | null
  provider_practice_id: string | null
  practice_id: string
  patient_practice_id: string | null
  prescription_id: string | null
}
export type ConversationPage = { items: ConversationRecord[]; total: number }
export function formatTime(value: string | null) {
  return value ? new Date(value).toLocaleString() : '—'
}
