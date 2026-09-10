import type { AuthSession } from '../../auth/types'
import { Button, List, ListItem } from '../../components'
import type { OverlayLayoutProps } from '../overlayRegistry'

export function ProviderDetails({ data, close }: OverlayLayoutProps<AuthSession>) {
  return <div className="ui-stack">
    <List variant="divided">
      <ListItem><strong>Provider</strong><span>{data.provider.first_name} {data.provider.last_name}</span></ListItem>
      <ListItem><strong>Username</strong><span>{data.provider.username}</span></ListItem>
      <ListItem><strong>Practice</strong><span>{data.practice.name}</span></ListItem>
    </List>
    <Button variant="secondary" onClick={close}>Done</Button>
  </div>
}
