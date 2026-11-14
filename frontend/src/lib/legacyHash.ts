// Maps old hash-router links (`/#/article/5`) to the real paths that replaced them.

/** The path a legacy hash link points to, or null when the hash is not one of the old routes. */
export function legacyHashPath(hash: string): string | null {
  const m = hash.match(/^#\/(article|story)\/(\d+)$/)
  if (m) return `/${m[1]}/${m[2]}`
  if (hash === '#/welcome') return '/welcome'
  return null
}
