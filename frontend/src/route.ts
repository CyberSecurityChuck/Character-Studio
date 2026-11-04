// Hash routes (#/characters/<id>, #/groups/<id>, #/settings) keep the current view across a
// browser refresh. replaceState adds no history entries, so Back behaves as before.
// A list's filters ride after "?" (#/scenes?stage=approved&set=<id>).
export function routeParts(): string[] {
  const hash = window.location.hash.split('?')[0]
  return hash.startsWith('#/') ? hash.slice(2).split('/').filter(Boolean).map(decodeURIComponent) : []
}

export function routeQuery(): URLSearchParams {
  const at = window.location.hash.indexOf('?')
  return new URLSearchParams(at < 0 ? '' : window.location.hash.slice(at + 1))
}

export function replaceRoute(path: string) {
  const next = path ? `#/${path}` : ''
  if (window.location.hash !== next) window.history.replaceState(null, '', next || window.location.pathname + window.location.search)
}
