import { forwardRef } from 'react'
import { Link } from 'react-router'
import type { Service } from '../api.ts'
import { PhoneIcon } from './icons.tsx'

type Props = { service: Service; highlighted?: boolean; showCategory?: boolean }

// A service with all its details (F-SITE-03). Highlighted when the URL names it (F-SITE-08).
const ServiceCard = forwardRef<HTMLElement, Props>(function ServiceCard({ service, highlighted, showCategory }, ref) {
  return (
    <article ref={ref} className={`service-card${highlighted ? ' is-highlighted' : ''}`} aria-current={highlighted || undefined}>
      {showCategory && (
        <Link to={service.pageUrl} className="service-category">
          {service.categoryPath.join(' › ')}
        </Link>
      )}
      <div className="service-title">
        <h3>{service.name}</h3>
        {highlighted && <span className="ai-badge">AI がご案内</span>}
      </div>
      {service.description && <p className="service-description">{service.description}</p>}
      {service.address && <p className="service-address">{service.address}</p>}
      <div className="service-links">
        {service.phone && (
          <a href={`tel:${service.phone}`} className="pill-link is-primary">
            <PhoneIcon />
            {service.phone}
          </a>
        )}
        {service.url && (
          <a href={service.url} className="pill-link" target="_blank" rel="noopener noreferrer">
            ホームページ
          </a>
        )}
      </div>
    </article>
  )
})

export default ServiceCard
