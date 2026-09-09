import { ConversationDetails } from './layouts/ConversationDetails'
import type { ConversationRecord } from '../conversations/types'
import type { AuthSession } from '../auth/types'
import { defineOverlay } from './overlayRegistry'
import { ProviderDetails } from './layouts/ProviderDetails'

export const overlayRegistry = {
  conversationDetails: defineOverlay<ConversationRecord>({ title: 'Conversation details', component: ConversationDetails }),
  providerDetails: defineOverlay<AuthSession>({
    title: 'Provider details',
    description: 'Your current practice and practitioner account.',
    component: ProviderDetails,
    size: 'sm',
  }),
}
