import { useEffect, useRef } from 'react'
import { Link } from 'react-router'
import { fetchTop } from '../api.ts'
import { useChat } from '../chat/ChatContext.tsx'
import { CategoryIcon, ChatIcon } from '../components/icons.tsx'
import { useFetch } from '../useFetch.ts'

export default function TopPage() {
  const chat = useChat()
  const top = useFetch('top', fetchTop)
  const cta = useRef<HTMLButtonElement>(null)
  const { setHeroCtaVisible } = chat

  useEffect(() => {
    const element = cta.current
    if (!element) return
    const observer = new IntersectionObserver(([entry]) => setHeroCtaVisible(entry.isIntersecting))
    observer.observe(element)
    return () => {
      observer.disconnect()
      setHeroCtaVisible(false)
    }
  }, [setHeroCtaVisible])

  return (
    <main className="page top-page">
      <section className="hero">
        <div className="hero-text">
          <span className="hero-badge">AI の案内係がいるサービス案内</span>
          <h1>
            お困りごとを話すだけで、
            <br />
            合う窓口が見つかります。
          </h1>
          <p className="hero-lead">
            子育て、健康、福祉、住まいなど、出茂市の住民向けサービスを、AI の案内係がお話を伺いながら一緒に探して、このサイトの中でご案内します。カテゴリやことばで、ご自分で探すこともできます。
          </p>
          <div className="hero-actions">
            <button ref={cta} type="button" className="hero-cta" onClick={chat.show}>
              <ChatIcon />
              {chat.started ? 'AI 相談を続ける' : 'AI に相談する'}
            </button>
            <p className="hero-note">
              生成 AI を使っています。
              <br />
              最適な窓口をご案内できない場合があります。
            </p>
          </div>
        </div>
        <HeroIllustration />
      </section>

      <section className="top-categories" aria-labelledby="top-categories-title">
        <h2 id="top-categories-title">カテゴリから探す</h2>
        {top.status === 'error' && <p className="load-error">読み込めませんでした。時間をおいて再読み込みしてください。</p>}
        <div className="category-grid">
          {top.status === 'done' &&
            top.data.categories.map((c) => (
              <Link key={c.name} to={c.url} className="category-tile">
                <span className="category-tile-icon">
                  <CategoryIcon name={c.name} />
                </span>
                <span className="category-tile-text">
                  <span className="category-tile-name">{c.name}</span>
                  <span className="category-tile-sub">{c.children.slice(0, 3).join('、')}</span>
                </span>
              </Link>
            ))}
        </div>
      </section>
    </main>
  )
}

// Decorative only: no text or buttons, so it cannot be mistaken for the real chat UI.
function HeroIllustration() {
  return (
    <div className="hero-illustration" aria-hidden="true">
      <svg viewBox="0 0 480 400" width="100%">
        <circle cx="250" cy="200" r="178" fill="var(--soft)" />
        <circle cx="96" cy="92" r="9" fill="var(--primary)" opacity=".3" />
        <circle cx="440" cy="196" r="7" fill="var(--accent)" opacity=".45" />
        <circle cx="132" cy="336" r="12" fill="var(--hl-ring)" opacity=".45" />
        <path d="M402 330l6 14 14 6-14 6-6 14-6-14-14-6 14-6z" fill="var(--hl-ring)" opacity=".7" />
        <g transform="translate(70 70) scale(12)" fill="var(--surface)" stroke="var(--accent)" strokeWidth=".5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 11a8 7 0 1 1 3.2 5.6L4 18l1-3.2A7 7 0 0 1 4 11Z" />
          <path d="M9 10.5v.5M15 10.5v.5" strokeWidth=".8" />
          <path d="M9.5 13.5c1.4 1 3.6 1 5 0" fill="none" />
        </g>
        <path d="M316 64h72a36 36 0 0 1 0 72h-34l-22 18 4-18h-20a36 36 0 0 1 0-72z" fill="var(--accent)" />
        <circle cx="322" cy="100" r="7" fill="#fff" />
        <circle cx="352" cy="100" r="7" fill="#fff" />
        <circle cx="382" cy="100" r="7" fill="#fff" />
        <circle cx="358" cy="272" r="38" fill="var(--surface)" stroke="var(--primary)" strokeWidth="10" />
        <path d="M386 300l34 34" stroke="var(--primary)" strokeWidth="13" strokeLinecap="round" />
      </svg>
    </div>
  )
}
