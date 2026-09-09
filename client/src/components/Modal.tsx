import { Overlay } from './Overlay'
import type { OverlayProps } from './Overlay'
export function Modal(props: OverlayProps) { return <Overlay {...props} kind="modal" /> }
