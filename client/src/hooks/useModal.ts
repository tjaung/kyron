import { useContext } from 'react'
import { OverlayContext } from './overlayContext'
export function useModal() {
  const context = useContext(OverlayContext)
  if (!context) throw new Error('useModal must be used inside OverlayProvider')
  return { openModal: context.openModal, closeModal: context.closeModal }
}
