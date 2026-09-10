import { useCallback, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { Modal } from '../components/Modal'
import { Drawer } from '../components/Drawer'
import type { OverlayProps } from '../components/Overlay'
import { OverlayContext } from './overlayContext'
import type { OpenOverlay } from './overlayRegistry'

type ActiveOverlay = Omit<OverlayProps, 'open' | 'onClose' | 'children'> & {
  kind: 'modal' | 'drawer'
  side?: 'left' | 'right'
  render: (close: () => void) => ReactNode
  key: number
  open: boolean
}
// One active overlay keeps focus and dismissal predictable. Opening another replaces it.
export function OverlayProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState<ActiveOverlay | null>(null)
  const close = useCallback(() => setActive(previous => previous ? { ...previous, open: false } : null), [])
  const openModal = useCallback<OpenOverlay>((entry, data) => {
    const Content = entry.component
    setActive(previous => ({ ...entry, kind: 'modal', open: true, key: (previous?.key ?? 0) + 1, render: dismiss => <Content data={data} close={dismiss} /> }))
  }, [])
  const openDrawer = useCallback<OpenOverlay>((entry, data) => {
    const Content = entry.component
    setActive(previous => ({ ...entry, kind: 'drawer', open: true, key: (previous?.key ?? 0) + 1, render: dismiss => <Content data={data} close={dismiss} /> }))
  }, [])
  const closeModal = useCallback(() => setActive(previous => previous?.kind === 'modal' ? { ...previous, open: false } : previous), [])
  const closeDrawer = useCallback(() => setActive(previous => previous?.kind === 'drawer' ? { ...previous, open: false } : previous), [])
  const value = useMemo(() => ({ openModal, openDrawer, closeModal, closeDrawer }), [openModal, openDrawer, closeModal, closeDrawer])
  const Shell = active?.kind === 'drawer' ? Drawer : Modal
  return <OverlayContext.Provider value={value}>
    {children}
    {active && <Shell key={active.key} open={active.open} onClose={close}
      onExited={() => setActive(previous => previous?.key === active.key && !previous.open ? null : previous)} title={active.title} description={active.description}
      size={active.size} variant={active.variant} {...(active.kind === 'drawer' ? { side: active.side } : {})}>
      {active.render(close)}
    </Shell>}
  </OverlayContext.Provider>
}
