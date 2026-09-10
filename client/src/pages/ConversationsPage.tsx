import { useAuth } from '../auth/useAuth'
import { SimulationControls } from '../conversations/SimulationControls'
import { ConversationTable } from '../conversations/ConversationTable'
export function ConversationsPage() {
  const { session } = useAuth()
  if (!session) return null
  return <div className="practice-page"><p className="eyebrow">{session.practice.name}</p><h1>Conversations</h1>
    <SimulationControls practice={session.practice.slug} />
    <ConversationTable key={session.practice.slug} practice={session.practice.slug} />
  </div>
}
