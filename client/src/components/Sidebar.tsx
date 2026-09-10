import { useId } from 'react'
import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { Button } from './Button'

export type SidebarLink = { label: string; to: string; icon: ReactNode }
export function Sidebar({ open, onOpenChange, links }: { open: boolean; onOpenChange: (open: boolean) => void; links: SidebarLink[] }) {
  const navigationId = useId()
  return <aside className="ui-sidebar" data-open={open}>
    <Button variant="ghost" className="ui-sidebar-toggle" onClick={() => onOpenChange(!open)}
      aria-expanded={open} aria-controls={navigationId} aria-label={open ? 'Collapse sidebar' : 'Expand sidebar'} title={open ? 'Collapse sidebar' : 'Expand sidebar'}>
      <span aria-hidden="true">{open ? '‹' : '›'}</span>
    </Button>
    <nav id={navigationId} aria-label="Practice navigation">
      {links.map(link => <NavLink key={link.to} to={link.to} title={link.label} aria-label={link.label}
        className={({ isActive }) => `ui-sidebar-link ${isActive ? 'is-active' : ''}`}>
        <span className="ui-sidebar-icon" aria-hidden="true">{link.icon}</span><span className="ui-sidebar-label">{link.label}</span>
      </NavLink>)}
    </nav>
  </aside>
}
