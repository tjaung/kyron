import { RuleDetails } from './layouts/RuleDetails'
import type { RuleDetailsData } from './layouts/RuleDetails'
import { ConversationDetails } from './layouts/ConversationDetails'
import type { ConversationRecord } from '../conversations/types'
import type { AuthSession } from '../auth/types'
import { defineOverlay } from './overlayRegistry'
import { ProviderDetails } from './layouts/ProviderDetails'

export const overlayRegistry = {
  ruleDetails: defineOverlay<RuleDetailsData>({ title: 'Rule details', component: RuleDetails, size: 'lg' }),
  conversationDetails: defineOverlay<ConversationRecord>({ title: 'Conversation', component: ConversationDetails, size: 'screen' }),
  providerDetails: defineOverlay<AuthSession>({
    title: 'Provider details',
    description: 'Your current practice and practitioner account.',
    component: ProviderDetails,
    size: 'sm',
  }),
}
