import type { ComponentType } from 'react'
import type { OverlayProps } from '../components/Overlay'

export type OverlayLayoutProps<Data> = { data: Data; close: () => void }
export type OverlayRegistryEntry<Data> = {
  title: string
  description?: string
  component: ComponentType<OverlayLayoutProps<Data>>
  size?: OverlayProps['size']
  variant?: OverlayProps['variant']
  side?: 'left' | 'right'
}
export function defineOverlay<Data>(entry: OverlayRegistryEntry<Data>): OverlayRegistryEntry<Data> {
  return entry
}
export type OpenOverlay = <Data>(entry: OverlayRegistryEntry<Data>, data: NoInfer<Data>) => void
