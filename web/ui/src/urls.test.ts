import { describe, expect, it } from 'vitest'
import { categoryUrl, parseUrl, searchUrl } from './urls.ts'

describe('urls', () => {
  it('builds the same encoded form as packages/catalog', () => {
    expect(categoryUrl(['A'], ['x y', 'z&w'])).toBe('/c/A#svc=x%20y&svc=z%26w')
    expect(searchUrl('予防 接種')).toBe('/search?q=%E4%BA%88%E9%98%B2%20%E6%8E%A5%E7%A8%AE')
  })

  it('parses encoded and decoded category urls', () => {
    const expected = { kind: 'category', path: ['子育て・教育', '健診・予防接種', '予防接種'], highlights: ['予防接種相談窓口'] }
    expect(parseUrl('/c/子育て・教育/健診・予防接種/予防接種#svc=予防接種相談窓口')).toEqual(expected)
    expect(parseUrl(categoryUrl(expected.path, expected.highlights))).toEqual(expected)
  })

  it('round-trips search queries with symbols', () => {
    expect(parseUrl(searchUrl('a&b c'))).toEqual({ kind: 'search', query: 'a&b c' })
  })

  it('rejects other urls', () => {
    for (const url of ['/', '/c/', '/search?q=', '/other', 'https://example.com/c/A']) {
      expect(parseUrl(url)).toBeNull()
    }
  })
})
