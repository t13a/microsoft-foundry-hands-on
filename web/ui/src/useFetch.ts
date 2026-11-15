import { useEffect, useState } from 'react'

export type FetchState<T> = { status: 'loading' } | { status: 'done'; data: T } | { status: 'error'; error: unknown }

// Re-fetches whenever key changes; responses for an outdated key are dropped.
export function useFetch<T>(key: string, load: () => Promise<T>): FetchState<T> {
  const [state, setState] = useState<{ key: string; value: FetchState<T> }>({ key, value: { status: 'loading' } })

  useEffect(() => {
    let current = true
    load().then(
      (data) => current && setState({ key, value: { status: 'done', data } }),
      (error) => current && setState({ key, value: { status: 'error', error } }),
    )
    return () => {
      current = false
    }
    // load is recreated on every render; key identifies the request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  return state.key === key ? state.value : { status: 'loading' }
}
