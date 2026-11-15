// Client for the BFF catalog API (web/api).

export type CategorySummary = { name: string; url: string; children: string[]; serviceCount: number }

export type Service = {
  name: string
  categoryPath: string[]
  description: string
  address: string
  phone: string
  url: string
  pageUrl: string
}

export type CategoryPage = {
  name: string
  path: string[]
  url: string
  description: string
  breadcrumbs: { name: string; url: string }[]
  children: CategorySummary[]
  services: Service[]
}

export type SearchResult = { query: string; count: number; services: Service[] }

export class NotFoundError extends Error {}

async function get<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (response.status === 404) throw new NotFoundError(url)
  if (!response.ok) throw new Error(`${response.status} ${url}`)
  return response.json() as Promise<T>
}

export function fetchTop(): Promise<{ categories: CategorySummary[] }> {
  return get('/api/categories')
}

export function fetchCategory(path: string[]): Promise<CategoryPage> {
  return get(`/api/categories/${path.map(encodeURIComponent).join('/')}`)
}

export function fetchSearch(query: string): Promise<SearchResult> {
  return get(`/api/search?q=${encodeURIComponent(query)}`)
}
