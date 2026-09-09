import type { ComponentProps } from 'react'

export function List({ variant = 'divided', className = '', ...props }: ComponentProps<'ul'> & { variant?: 'plain' | 'divided' | 'bordered' }) {
  return <ul className={`ui-list ui-list--${variant} ${className}`} {...props} />
}
export function ListItem({ className = '', ...props }: ComponentProps<'li'>) {
  return <li className={`ui-list-item ${className}`} {...props} />
}
