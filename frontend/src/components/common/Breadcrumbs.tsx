import { Link } from 'react-router-dom'

export type Crumb = {
  label: string
  to?: string
}

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav className="crumbs" aria-label="パンくず">
      {items.map((item, index) => (
        <span key={`${item.label}-${index}`} className="crumbs__item">
          {index > 0 ? (
            <span className="crumbs__sep" aria-hidden="true">
              ›
            </span>
          ) : null}
          {item.to ? (
            <Link to={item.to}>{item.label}</Link>
          ) : (
            <span aria-current="page">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  )
}
