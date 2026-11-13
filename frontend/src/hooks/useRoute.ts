import { useEffect, useState } from 'react'

export type Route = { name: 'home' } | { name: 'article'; id: number }

function parse(): Route {
  const m = location.hash.match(/^#\/article\/(\d+)$/)
  return m ? { name: 'article', id: Number(m[1]) } : { name: 'home' }
}

/** Hash routing keeps existing `/#/article/:id` links working with no server rewrite. */
export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(parse)
  useEffect(() => {
    const on = () => setRoute(parse())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return route
}

export function goHome() {
  location.hash = '#/'
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
