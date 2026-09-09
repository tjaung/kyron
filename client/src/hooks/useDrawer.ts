import { useContext } from 'react'
import { OverlayContext } from './overlayContext'
export function useDrawer() {
  const context = useContext(OverlayContext)
  if (!context) throw new Error('useDrawer must be used inside OverlayProvider')
  return { openDrawer: context.openDrawer, closeDrawer: context.closeDrawer }
}
