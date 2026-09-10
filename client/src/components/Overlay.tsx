import { useEffect, useEffectEvent, useId, useRef } from 'react'
import type { ReactNode } from 'react'
import { Button } from './Button'

export type OverlayProps = {
  open: boolean
  onClose: () => void
  onExited?: () => void
  title: string
  description?: string
  children: ReactNode
  footer?: ReactNode
  size?: 'sm' | 'md' | 'lg' | 'screen'
  variant?: 'default' | 'muted'
}
export function Overlay({ open, onClose, onExited, title, description, children, footer, size = 'md', variant = 'default', kind, side = 'right' }: OverlayProps & { kind: 'modal' | 'drawer'; side?: 'left' | 'right' }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  const descriptionId = useId()
  const release = useRef<(() => void) | null>(null)
  const exited = useEffectEvent(() => onExited?.())
  useEffect(() => {
    const element = dialog.current
    if (!element) return
    if (open) {
      if (!element.open) {
        const previouslyFocused = document.activeElement
        const overflow = document.body.style.overflow
        element.showModal()
        document.body.style.overflow = 'hidden'
        release.current = () => {
          element.close()
          document.body.style.overflow = overflow
          if (previouslyFocused instanceof HTMLElement && previouslyFocused.isConnected) previouslyFocused.focus()
          release.current = null
        }
      }
      return
    }
    if (!element.open) return
    // Keep the dialog modal and scroll locked until its exit motion finishes.
    const finish = () => { release.current?.(); exited() }
    const duration = Number.parseFloat(getComputedStyle(element).animationDuration) * 1000
    const timer = window.setTimeout(finish, duration > 0 ? duration + 32 : 0)
    return () => window.clearTimeout(timer)
  }, [open])
  useEffect(() => () => release.current?.(), [])
  return <dialog ref={dialog} data-state={open ? 'open' : 'closing'} className={`ui-overlay ui-${kind} ui-overlay--${size} ui-overlay--${variant} ui-drawer--${side}`}
    aria-labelledby={titleId} aria-describedby={description ? descriptionId : undefined}
    onKeyDown={event => {
      if (event.key !== 'Tab') return
      const focusable = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(
        'button, a[href], input, select, textarea, [tabindex], [contenteditable="true"]',
      )).filter(element => element.tabIndex >= 0 && !element.matches(':disabled') && !element.closest('[inert]') && element.getClientRects().length > 0)
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last?.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first?.focus()
      }
    }}
    onCancel={event => { event.preventDefault(); onClose() }}
    onClick={event => { if (event.target === event.currentTarget) {
      const rect = event.currentTarget.getBoundingClientRect()
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose()
    } }}>
    <header className="ui-overlay-header"><div><h2 id={titleId}>{title}</h2>{description && <p id={descriptionId}>{description}</p>}</div>
      <Button variant="ghost" size="sm" aria-label="Close" onClick={onClose}>✕</Button>
    </header>
    <div className="ui-overlay-body">{children}</div>
    {footer && <footer className="ui-overlay-footer">{footer}</footer>}
  </dialog>
}
