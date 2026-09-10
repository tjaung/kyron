import { createContext } from 'react'
import type { OpenOverlay } from './overlayRegistry'
export const OverlayContext = createContext<{
  openModal: OpenOverlay
  openDrawer: OpenOverlay
  closeModal: () => void
  closeDrawer: () => void
} | null>(null)
