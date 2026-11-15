// The destination card's summary, built from the URL alone (F-UI-05), so the chat history
// says where each card leads even without opening it.
import { parseUrl } from '../urls.ts'

export type Summary = { kind: 'category' | 'search'; label: string; title: string; detail: string }

export function summarize(url: string, count: number): Summary | null {
  const location = parseUrl(url)
  if (!location) return null
  if (location.kind === 'search') {
    return { kind: 'search', label: '検索結果', title: `「${location.query}」`, detail: `${count} 件` }
  }
  const [first, ...rest] = location.highlights
  const detail = first ? `「${first}」${rest.length ? `ほか ${rest.length} 件` : ''}を強調表示` : `${count} 件のサービス`
  return { kind: 'category', label: 'カテゴリ', title: location.path.join(' › '), detail }
}
