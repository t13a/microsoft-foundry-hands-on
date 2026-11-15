import { useEffect, useRef } from 'react'
import Markdown from 'react-markdown'
import { Link } from 'react-router'
import { fetchCategory, NotFoundError } from '../api.ts'
import { CategoryIcon } from '../components/icons.tsx'
import ServiceCard from '../components/ServiceCard.tsx'
import { useFetch } from '../useFetch.ts'
import NotFoundPage from './NotFoundPage.tsx'

export default function CategoryPage({ path, highlights }: { path: string[]; highlights: string[] }) {
  const page = useFetch(path.join('/'), () => fetchCategory(path))
  const firstHighlight = useRef<HTMLElement>(null)
  const highlightKey = highlights.join('&')

  useEffect(() => {
    // Scroll to the highlighted service once it is on screen (F-SITE-08).
    if (page.status === 'done') firstHighlight.current?.scrollIntoView({ block: 'center' })
  }, [page.status, highlightKey])

  if (page.status === 'error') {
    return page.error instanceof NotFoundError ? <NotFoundPage /> : <main className="page"><p className="load-error">読み込めませんでした。</p></main>
  }
  if (page.status === 'loading') return <main className="page" aria-busy="true" />

  const category = page.data
  const firstName = category.services.find((s) => highlights.includes(s.name))?.name
  return (
    <main className="page category-page">
      <nav aria-label="パンくずリスト" className="breadcrumbs">
        <Link to="/">トップ</Link>
        {category.breadcrumbs.map((b) => (
          <span key={b.url}>
            <span aria-hidden="true">›</span>
            <Link to={b.url}>{b.name}</Link>
          </span>
        ))}
        <span>
          <span aria-hidden="true">›</span>
          <span aria-current="page">{category.name}</span>
        </span>
      </nav>
      <h1>{category.name}</h1>
      {category.description && (
        <div className="prose">
          <Markdown>{category.description}</Markdown>
        </div>
      )}

      {category.children.length > 0 && (
        <section aria-labelledby="children-title">
          <h2 id="children-title">このカテゴリの分類</h2>
          <div className="child-list">
            {category.children.map((c) => (
              <Link key={c.name} to={c.url} className="category-tile">
                <span className="category-tile-icon">
                  <CategoryIcon name={c.name} size={22} />
                </span>
                <span className="category-tile-text">
                  <span className="category-tile-name">{c.name}</span>
                  {c.children.length > 0 && <span className="category-tile-sub">{c.children.slice(0, 3).join('、')}</span>}
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}

      {category.services.length > 0 && (
        <section aria-labelledby="services-title">
          <h2 id="services-title">このカテゴリのサービス ({category.services.length})</h2>
          <div className="service-list">
            {category.services.map((s) => (
              <ServiceCard key={s.name} ref={s.name === firstName ? firstHighlight : undefined} service={s} highlighted={highlights.includes(s.name)} />
            ))}
          </div>
        </section>
      )}
    </main>
  )
}
