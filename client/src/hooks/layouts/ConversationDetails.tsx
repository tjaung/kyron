import { List, ListItem } from '../../components'
import { formatTime } from '../../conversations/types'
import type { ConversationRecord } from '../../conversations/types'
import type { OverlayLayoutProps } from '../overlayRegistry'
export function ConversationDetails({ data }: OverlayLayoutProps<ConversationRecord>) {
  return <List>
    <ListItem><strong>Conversation</strong>{data.name}</ListItem>
    <ListItem><strong>Record ID</strong>{data.id}</ListItem>
    <ListItem><strong>Status</strong>{data.status}</ListItem>
    <ListItem><strong>Started</strong>{formatTime(data.start_time)}</ListItem>
    <ListItem><strong>Ended</strong>{formatTime(data.end_time)}</ListItem>
    <ListItem><strong>Patient practice ID</strong>{data.patient_practice_id ?? '—'}</ListItem>
    <ListItem><strong>Prescription ID</strong>{data.prescription_id ?? '—'}</ListItem>
  </List>
}
