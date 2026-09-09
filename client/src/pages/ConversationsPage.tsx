import { useAuth } from '../auth/useAuth'
import { ConversationTable } from '../conversations/ConversationTable'
export function ConversationsPage() {
  const { session } = useAuth()
  if (!session) return null
  return <div className="practice-page"><p className="eyebrow">{session.practice.name}</p><h1>Conversations</h1>
    <ConversationTable key={session.practice.slug} practice={session.practice.slug} />
  </div>
}
