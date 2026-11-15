import { Link } from 'react-router'

export default function NotFoundPage() {
  return (
    <main className="page">
      <h1>ページが見つかりません</h1>
      <p>
        カテゴリの名前が変わったか、URL が間違っている可能性があります。<Link to="/">トップ</Link>から探してください。
      </p>
    </main>
  )
}
