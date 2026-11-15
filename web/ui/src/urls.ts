// Screen URLs, following the same rules as packages/catalog (docs/design.md 7.3).
// Built URLs encode each part; parsing accepts both encoded and decoded forms.

export type Location =
  | { kind: 'category'; path: string[]; highlights: string[] }
  | { kind: 'search'; query: string }

const CATEGORY_PREFIX = '/c/'

export function categoryUrl(path: string[], highlights: string[] = []): string {
  const url = CATEGORY_PREFIX + path.map(encodeURIComponent).join('/')
  return highlights.length ? `${url}#${highlights.map((h) => `svc=${encodeURIComponent(h)}`).join('&')}` : url
}

export function searchUrl(query: string): string {
  return `/search?q=${encodeURIComponent(query)}`
}

function decode(part: string): string {
  try {
    return decodeURIComponent(part)
  } catch {
    return part
  }
}

function params(text: string): [string, string][] {
  return text
    .replace(/^[?#]/, '')
    .split('&')
    .filter(Boolean)
    .map((pair) => {
      const [key, ...rest] = pair.split('=')
      return [decode(key), decode(rest.join('=').replace(/\+/g, ' '))]
    })
}

export function parseUrl(url: string): Location | null {
  const parsed = new URL(url, 'http://local')
  if (parsed.origin !== 'http://local' && /^[a-z]+:/i.test(url)) return null
  return parseParts(parsed.pathname, parsed.search, parsed.hash)
}

export function parseParts(pathname: string, search: string, hash: string): Location | null {
  if (pathname.startsWith(CATEGORY_PREFIX)) {
    const path = pathname.slice(CATEGORY_PREFIX.length).split('/').filter(Boolean).map(decode)
    if (!path.length) return null
    const highlights = params(hash)
      .filter(([k, v]) => k === 'svc' && v)
      .map(([, v]) => v)
    return { kind: 'category', path, highlights }
  }
  if (pathname === '/search') {
    const query = params(search).find(([k]) => k === 'q')?.[1] ?? ''
    return query.trim() ? { kind: 'search', query } : null
  }
  return null
}
