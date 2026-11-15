import { fetchSearch } from '../api.ts'
import ServiceCard from '../components/ServiceCard.tsx'
import { useFetch } from '../useFetch.ts'

export default function SearchPage({ query }: { query: string }) {
  const result = useFetch(query, () => fetchSearch(query))
  return (
    <main className="page search-page">
      <h1>「{query}」の検索結果</h1>
      {result.status === 'error' && <p className="load-error">読み込めませんでした。</p>}
      {result.status === 'done' && (
        <>
          <p className="search-count">{result.data.count > 0 ? `${result.data.count} 件見つかりました` : '見つかりませんでした。ことばを変えて検索するか、AI に相談してみてください。'}</p>
          <div className="service-list">
            {result.data.services.map((s) => (
              <ServiceCard key={s.pageUrl} service={s} showCategory />
            ))}
          </div>
        </>
      )}
    </main>
  )
}
