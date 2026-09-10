import { useId } from 'react'
import type { ComponentProps, ReactNode } from 'react'

type Variant = 'outline' | 'filled'
type FieldProps = { label?: string; hint?: string; error?: string; variant?: Variant }
function Field({ id, label, hint, error, children }: FieldProps & { id: string; children: ReactNode }) {
  return <div className="ui-field">
    {label && <label htmlFor={id}>{label}</label>}
    {children}
    {hint && <p id={`${id}-hint`} className="ui-field-hint">{hint}</p>}
    {error && <p id={`${id}-error`} className="ui-field-error" role="alert">{error}</p>}
  </div>
}
function descriptions(id: string, hint?: string, error?: string, existing?: string) {
  return [existing, hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(' ') || undefined
}
export function Form({ variant = 'stacked', className = '', ...props }: ComponentProps<'form'> & { variant?: 'stacked' | 'inline' }) {
  return <form className={`ui-form ui-form--${variant} ${className}`} {...props} />
}
export function TextInput({ id: suppliedId, label, hint, error, variant = 'outline', className = '', ...props }: ComponentProps<'input'> & FieldProps) {
  const generatedId = useId()
  const id = suppliedId ?? generatedId
  return <Field {...{ id, label, hint, error }}><input {...props} id={id}
    aria-invalid={error ? true : props['aria-invalid']}
    aria-describedby={descriptions(id, hint, error, props['aria-describedby'])}
    className={`ui-control ui-control--${variant} ${className}`} /></Field>
}
export function NumberInput(props: Omit<ComponentProps<typeof TextInput>, 'type'>) {
  return <TextInput {...props} type="number" />
}
export function Dropdown({ id: suppliedId, label, hint, error, variant = 'outline', className = '', ...props }: ComponentProps<'select'> & FieldProps) {
  const generatedId = useId()
  const id = suppliedId ?? generatedId
  return <Field {...{ id, label, hint, error }}><select {...props} id={id}
    aria-invalid={error ? true : props['aria-invalid']}
    aria-describedby={descriptions(id, hint, error, props['aria-describedby'])}
    className={`ui-control ui-control--${variant} ${className}`} /></Field>
}
export function Textarea({ id: suppliedId, label, hint, error, variant = 'outline', className = '', ...props }: ComponentProps<'textarea'> & FieldProps) {
  const generatedId = useId()
  const id = suppliedId ?? generatedId
  return <Field {...{ id, label, hint, error }}><textarea rows={4} {...props} id={id}
    aria-invalid={error ? true : props['aria-invalid']}
    aria-describedby={descriptions(id, hint, error, props['aria-describedby'])}
    className={`ui-control ui-control--${variant} ${className}`} /></Field>
}
export function Checkbox({ label, variant = 'default', className = '', ...props }: Omit<ComponentProps<'input'>, 'type'> & { label: string; variant?: 'default' | 'panel' }) {
  return <label className={`ui-checkbox ui-checkbox--${variant} ${className}`}><input {...props} type="checkbox" /><span>{label}</span></label>
}
