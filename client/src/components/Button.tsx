import type { ComponentProps } from 'react'

type Props = ComponentProps<'button'> & {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  fullWidth?: boolean
}
export function Button({ variant = 'primary', size = 'md', fullWidth, className = '', type = 'button', ...props }: Props) {
  return <button type={type} className={`ui-button ui-button--${variant} ui-button--${size} ${fullWidth ? 'ui-full-width' : ''} ${className}`} {...props} />
}
