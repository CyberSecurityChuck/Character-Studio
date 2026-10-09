// Hash routes (#/characters/<id>, #/groups/<id>, #/settings) keep the current view across a
// browser refresh. replaceState adds no history entries, so Back behaves as before.
export function routeParts(): string[] {
  const hash = window.location.hash
  return hash.startsWith('#/') ? hash.slice(2).split('/').filter(Boolean).map(decodeURIComponent) : []
}

export function replaceRoute(path: string) {
  const next = path ? `#/${path}` : ''
  if (window.location.hash !== next) window.history.replaceState(null, '', next || window.location.pathname + window.location.search)
}
