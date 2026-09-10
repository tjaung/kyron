import { useId } from 'react'
import type { CSSProperties, Key, ReactNode } from 'react'

export type TableColumn<Row> = {
  id: string
  name: ReactNode
  /** Read a property, or derive/render a value from the whole row. */
  data: keyof Row | ((row: Row) => ReactNode)
  className?: string
  headerClassName?: string
  style?: CSSProperties
  align?: 'left' | 'center' | 'right'
}
export type TableSection = {
  title?: string
  subtitle?: string
  content?: ReactNode
  actions?: ReactNode
}
export type TableProps<Row> = {
  data: Row[]
  columns: TableColumn<Row>[]
  rowKey: (row: Row) => Key
  onRowClick?: (row: Row) => void
  rowLabel?: (row: Row) => string
  rowActionColumn?: string
  header?: TableSection
  footer?: TableSection
  caption?: string
  loading?: boolean
  emptyMessage?: string
  className?: string
  variant?: 'default' | 'striped' | 'compact'
}
function Section({ data, titleId }: { data: TableSection; titleId?: string }) {
  return <><div>{data.title && <h2 id={titleId}>{data.title}</h2>}{data.subtitle && <p>{data.subtitle}</p>}{data.content}</div>{data.actions && <div className="ui-table-actions">{data.actions}</div>}</>
}
export function Table<Row>({ data, columns, rowKey, onRowClick, rowLabel, rowActionColumn, header, footer, caption = 'Records', loading = false, emptyMessage = 'No records yet.', className = '', variant = 'default' }: TableProps<Row>) {
  const titleId = useId()
  return <section className={`ui-table ui-table--${variant} ${className}`} aria-busy={loading}>
    {header && <header className="ui-table-header"><Section data={header} titleId={titleId} /></header>}
    <div className="ui-table-scroll" role="region" aria-label={header?.title ?? caption} tabIndex={0}>
      <table aria-labelledby={header?.title ? titleId : undefined}>
        <caption className="ui-sr-only">{caption}</caption>
        <thead><tr>{columns.map(column => <th key={column.id} scope="col" className={column.headerClassName} style={{ ...column.style, textAlign: column.align }}>{column.name}</th>)}</tr></thead>
        <tbody>
          {loading ? <tr><td colSpan={columns.length}><div className="ui-table-empty" role="status">Loading records…</div></td></tr>
            : data.length === 0 ? <tr><td colSpan={columns.length}><div className="ui-table-empty">{emptyMessage}</div></td></tr>
              : data.map(row => <tr key={rowKey(row)} className={onRowClick ? 'ui-table-clickable' : undefined}
                onClick={onRowClick ? event => {
                  if (!(event.target as HTMLElement).closest('button, a, input, select, textarea, [role="button"]')) onRowClick(row)
                } : undefined}>
                {columns.map((column, index) => {
                  const value = typeof column.data === 'function' ? column.data(row) : row[column.data]
                  const content = typeof column.data === 'function' ? value as ReactNode : value == null ? '—' : String(value)
                  return <td key={column.id} className={column.className} style={{ ...column.style, textAlign: column.align }}>
                    {(rowActionColumn ? column.id === rowActionColumn : index === 0) && onRowClick ? <button type="button" className="ui-table-row-button" aria-label={rowLabel?.(row)} onClick={() => onRowClick(row)}>{content}</button> : content}
                  </td>
                })}
              </tr>)}
        </tbody>
      </table>
    </div>
    {footer && <footer className="ui-table-footer"><Section data={footer} /></footer>}
  </section>
}
