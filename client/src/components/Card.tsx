import type { ComponentProps } from 'react'

type Props = ComponentProps<'section'> & { variant?: 'outlined' | 'elevated' | 'muted' }
export function Card({ variant = 'outlined', className = '', ...props }: Props) {
  return <section className={`ui-card ui-card--${variant} ${className}`} {...props} />
}
