import { useId } from 'react'
import type { ReactNode } from 'react'
export type TabItem<Value extends string> = { value: Value; label: ReactNode; content: ReactNode; disabled?: boolean }
export function Tabs<Value extends string>({ items, value, onValueChange, label, variant = 'underline', className = '', panelClassName = '', keepMounted = true }: {
  items: TabItem<Value>[]; value: Value; onValueChange: (value: Value) => void; label: string
  variant?: 'underline' | 'pills'; className?: string; panelClassName?: string; keepMounted?: boolean
}) {
  const id = useId()
  const enabled = items.filter(item => !item.disabled)
  return <div className={`ui-tabs ui-tabs--${variant} ${className}`}>
    <div role="tablist" aria-label={label} className="ui-tablist">
      {items.map((item, index) => <button key={item.value} type="button" role="tab" disabled={item.disabled}
        id={`${id}-tab-${index}`} aria-controls={`${id}-panel-${index}`} aria-selected={value === item.value}
        tabIndex={value === item.value ? 0 : -1} onClick={() => onValueChange(item.value)}
        onKeyDown={event => {
          const current = enabled.findIndex(tab => tab.value === item.value)
          const next = event.key === 'ArrowRight' ? (current + 1) % enabled.length : event.key === 'ArrowLeft' ? (current + enabled.length - 1) % enabled.length : event.key === 'Home' ? 0 : event.key === 'End' ? enabled.length - 1 : null
          if (next !== null && enabled[next]) {
            event.preventDefault(); onValueChange(enabled[next].value)
            document.getElementById(`${id}-tab-${items.findIndex(tab => tab.value === enabled[next].value)}`)?.focus()
          }
        }}>{item.label}</button>)}
    </div>
    {items.map((item, index) => <section key={item.value} role="tabpanel" id={`${id}-panel-${index}`} aria-labelledby={`${id}-tab-${index}`}
      hidden={value !== item.value} tabIndex={0} className={`ui-tabpanel ${panelClassName}`}>
      {(keepMounted || value === item.value) && item.content}
    </section>)}
  </div>
}
