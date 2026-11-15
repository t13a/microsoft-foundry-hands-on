import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { parseParts, searchUrl } from '../urls.ts'
import Emblem from './Emblem.tsx'
import { SearchIcon } from './icons.tsx'

// Site name and search only; no global menu (F-SITE-11).
export default function Header() {
  const location = useLocation()
  const navigate = useNavigate()
  const current = parseParts(location.pathname, location.search, location.hash)
  const initial = current?.kind === 'search' ? current.query : ''
  const [query, setQuery] = useState(initial)
  const [searchOpen, setSearchOpen] = useState(false)
  const [lastInitial, setLastInitial] = useState(initial)
  if (initial !== lastInitial) {
    // Follow the URL when it changes elsewhere (back button, a link to search results).
    setLastInitial(initial)
    setQuery(initial)
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!query.trim()) return
    setSearchOpen(false)
    navigate(searchUrl(query.trim()))
  }

  return (
    <header className="site-header">
      <div className="site-header-row">
        <Link to="/" className="site-name">
          <Emblem size={40} />
          <span>出茂市 くらしのサービス案内</span>
        </Link>
        <form role="search" className={`header-search${searchOpen ? ' is-open' : ''}`} onSubmit={submit}>
          <label htmlFor="site-search" className="visually-hidden">
            サービスを検索
          </label>
          <input id="site-search" type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="ことばで検索 (例: 児童手当)" />
          <button type="submit" className="button-primary">
            検索
          </button>
        </form>
        <button type="button" className="icon-button header-search-toggle" aria-label="検索" aria-expanded={searchOpen} onClick={() => setSearchOpen(!searchOpen)}>
          <SearchIcon size={22} />
        </button>
      </div>
    </header>
  )
}
