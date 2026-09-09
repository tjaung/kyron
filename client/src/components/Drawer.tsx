import { Overlay } from './Overlay'
import type { OverlayProps } from './Overlay'
export function Drawer(props: OverlayProps & { side?: 'left' | 'right' }) { return <Overlay {...props} kind="drawer" /> }
