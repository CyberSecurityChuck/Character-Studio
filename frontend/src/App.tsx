import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError, getBootstrap, savePreferences, type Bootstrap } from './api'

import Library from './Library'
import { replaceRoute, routeParts } from './route'

type Page = 'overview' | 'settings' | 'characters'
const pageRoutes: Record<string, Page> = { characters: 'characters', groups: 'characters', settings: 'settings' }

const upcoming = [
  { name: 'Scenes', phase: '03–04', text: 'A reference. A new possibility.', detail: 'Prepare scenes, map people and review prompts.' },
  { name: 'Results', phase: '05', text: 'Every version has a home.', detail: 'Exchange approved packages and keep your results.' },
]

export default function App() {
  const [libraryBusy, setLibraryBusy] = useState(false)
  const [libraryDirty, setLibraryDirty] = useState(false)
  const [page, setPage] = useState<Page>(() => pageRoutes[routeParts()[0]] ?? 'overview')
  const [data, setData] = useState<Bootstrap | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [conflict, setConflict] = useState(false)
  const heading = useRef<HTMLHeadingElement>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await getBootstrap()
      setData(result)
      setName(result.preferences.studio_name)
      setConflict(false)
      setSaved(false)
    } catch (error) {
      setError(error instanceof Error ? error.message : 'The studio could not be loaded.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const dirty = !!data && name !== data.preferences.studio_name
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault() }
    if (dirty || libraryDirty || libraryBusy) window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty, libraryDirty, libraryBusy])

  function navigate(next: Page) {
    if (next === page || libraryBusy) return
    if (libraryDirty && !window.confirm('Leave the library and discard unsaved edits?')) return
    replaceRoute(next === 'overview' ? '' : next)
    setPage(next)
    requestAnimationFrame(() => heading.current?.focus())
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!data || saving) return
    setSaving(true)
    setSaved(false)
    setError('')
    try {
      const preferences = await savePreferences(
        { studio_name: name.trim(), revision: data.preferences.revision }, data.session_token,
      )
      setData({ ...data, preferences })
      setName(preferences.studio_name)
      setSaved(true)
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Your change could not be saved.')
      setConflict(error instanceof ApiError && [403, 409].includes(error.status))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="studio-layout">
      <a className="skip-link" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById('main')?.focus() }}>Skip to content</a>
      <aside className="sidebar">
        <a href="#" className="brand" onClick={(e) => { e.preventDefault(); navigate('overview') }} aria-label="Character Studio overview">
          <span className="brand-mark" aria-hidden="true">cs<span>.</span></span>
          <span>Character<br />Studio</span>
        </a>
        <div className="nav-label">YOUR WORKSPACE</div>
        <nav aria-label="Studio navigation">
          <button disabled={libraryBusy} aria-current={page === 'overview' ? 'page' : undefined} className={page === 'overview' ? 'nav-item active' : 'nav-item'} onClick={() => navigate('overview')}>
            <svg className="nav-symbol" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></svg> Overview
          </button>
          <button disabled={libraryBusy} aria-current={page === 'characters' ? 'page' : undefined} className={page === 'characters' ? 'nav-item active' : 'nav-item'} onClick={() => navigate('characters')}>
            <svg className="nav-symbol" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20c.8-3.6 3.3-5.5 6.5-5.5s5.7 1.9 6.5 5.5" /><circle cx="17" cy="9" r="2.5" /><path d="M17 14.5c2.4.3 4 2 4.6 4.5" /></svg> Characters
          </button>
          <div className="future-nav" aria-label="Planned features">
            <span><span className="future-item"><svg className="nav-symbol" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="8.5" cy="9.5" r="1.5" /><path d="M3 17l5-5 5 5 3-3 5 5" /></svg> Scenes</span> <small>Phase 3</small></span>
            <span><span className="future-item"><svg className="nav-symbol" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"><rect x="7" y="7" width="14" height="14" rx="2" /><path d="M17 7V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h2" /><path d="M14 10.5l.9 2 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9z" /></svg> Results</span> <small>Phase 5</small></span>
          </div>
          <button disabled={libraryBusy} aria-current={page === 'settings' ? 'page' : undefined} className={page === 'settings' ? 'nav-item active' : 'nav-item'} onClick={() => navigate('settings')}>
            <svg className="nav-symbol" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3 7h18M3 17h18" /><circle cx="8" cy="7" r="3" fill="var(--surface)" /><circle cx="16" cy="17" r="3" fill="var(--surface)" /></svg> Studio settings
          </button>
        </nav>
        <div className="sidebar-note"><span className="tiny-label">BUILT AROUND YOU</span><p>Your characters.<br />Your scenes.<br />Your computer.</p><span className="version">Character Library · Phase 2</span></div>
      </aside>

      <div className="workspace">
        <header className="topbar"><span>Workspace <span className="crumb">/</span> {page === 'overview' ? 'Overview' : page === 'characters' ? 'Characters' : 'Settings'}</span>
          <span className={`connection ${data && !error ? 'online' : ''}`}><span aria-hidden="true" />{loading ? 'Connecting…' : error ? 'Needs attention' : 'Local studio connected'}</span>
        </header>
        <main id="main" tabIndex={-1}>
          <div className="page-heading"><div><p className="eyebrow">CHARACTER STUDIO / PHASE 02</p>
            <h1 ref={heading} tabIndex={-1}>{page === 'overview' ? (data?.preferences.studio_name || 'Your studio') : page === 'characters' ? 'Your character library' : 'Studio settings'}</h1>
            <p className="intro">{page === 'overview' ? 'A little structure for a world of possibilities.' : page === 'characters' ? 'Familiar faces, ready for the stories ahead.' : 'Make this space yours. Keep your work close.'}</p></div>
            <span className="phase-badge">Local & private</span>
          </div>

          {error && <div className="error" role="alert"><strong>Something needs your attention.</strong><p>{error}</p>
            {(!data || conflict) && <button className="secondary" onClick={() => void load()}>{conflict ? 'Discard local edit and reload' : 'Try again'}</button>}
          </div>}

          {loading ? <div className="loading" role="status">Opening your local workspace…</div> : data && <>
            {page === 'characters' ? <Library data={data} onDirty={setLibraryDirty} onBusy={setLibraryBusy} onSession={setData} /> : page === 'overview' ? <>
              <section className="welcome-panel" aria-labelledby="welcome-title">
                <div className="welcome-copy"><span className="tiny-label">THE START OF SOMETHING PERSONAL</span>
                  <h2 id="welcome-title">Same characters.<br /><em>New stories.</em></h2>
                  <p>Save your characters, collect their reference photos and organize them into groups. Scene creation comes next.</p>
                  <button onClick={() => navigate('characters')}>Open character library <span aria-hidden="true">↗</span></button>
                </div>
                <div className="composition" aria-hidden="true">
                  <div className="composition-grid" />
                  <div className="frame back"><div className="landscape"><span /><span /></div><small>THE SCENE</small></div>
                  <div className="frame front"><div className="portrait"><span className="head" /><span className="body" /></div><small>THE CHARACTER</small></div>
                  <span className="composition-caption">WHO YOU SAVE. WHERE YOU IMAGINE.</span>
                </div>
              </section>

              <section className="readiness" aria-label="Foundation status">
                <div><span className="status-dot" /><div><strong>Saved on this computer</strong><p>Local database and separate file storage</p></div></div>
                <div><span className="status-dot" /><div><strong>No paid API connected</strong><p>Manual bridge planned for the MVP</p></div></div>
              </section>

              <div className="section-title"><h2>What’s taking shape</h2><span>THE ROAD TO YOUR FIRST SCENE</span></div>
              <section className="roadmap" aria-label="Upcoming phases">{upcoming.map((item, index) => (
                <article key={item.name} className="roadmap-card"><div className="card-top"><span className="step-number">0{index + 1}</span><span>Phase {item.phase}</span></div>
                  <h3>{item.name}</h3><p className="card-lead">{item.text}</p><p>{item.detail}</p><span className="planned">Coming in a later phase</span>
                </article>
              ))}</section>
              <p className="footnote">Start small. Save often. Keep every step connected.</p>
            </> : <div className="settings-grid">
              <section className="panel" aria-labelledby="preferences-title"><span className="tiny-label">YOUR SPACE</span><h2 id="preferences-title">A name for your studio</h2><p>This preference is saved locally and stays after you restart.</p>
                <form onSubmit={(e) => void save(e)}>
                  <label htmlFor="studio-name">Studio name</label>
                  <input id="studio-name" name="studio-name" value={name} maxLength={60} required disabled={saving} aria-describedby="name-hint save-status" onChange={(e) => { setName(e.target.value); setSaved(false) }} />
                  <p className="hint" id="name-hint">Up to 60 characters. Use a nickname if you prefer.</p>
                  <div className="save-row"><button disabled={!dirty || !name.trim() || saving || conflict}>{saving ? 'Saving…' : 'Save changes'}</button>
                    <span id="save-status" role="status">{saving ? 'Saving to this computer…' : saved ? 'Saved to this computer' : dirty ? 'Unsaved changes' : 'All changes saved'}</span></div>
                </form>
              </section>
              <section className="panel storage-panel" aria-labelledby="storage-title"><span className="tiny-label">LOCAL BY DEFAULT</span><h2 id="storage-title">Your files stay with you</h2><p>Application data lives separately from the source code.</p><label>Data folder</label><code>{data.data_directory}</code><p className="hint">Changing this location is a setup task. Moving files and backup controls will be added in a later phase.</p></section>
              <section className="panel provider-panel" aria-labelledby="providers-title"><div className="section-title"><h2 id="providers-title">Image workflow</h2><span>No API charges enabled</span></div>
                {data.providers.map((provider) => <div className="provider" key={provider.id}><div><h3>{provider.name}</h3><p>{provider.description}</p><small>{provider.pricing}</small></div><span className="provider-status">{provider.status === 'planned' ? 'Planned' : provider.status === 'unverified' ? 'Not verified' : provider.status === 'disabled' ? 'Disabled' : 'Available'}</span></div>)}
              </section>
            </div>}
          </>}
        </main>
        <footer><span>Character Studio</span><span>Local-first. Thoughtfully connected.</span></footer>
      </div>
    </div>
  )
}
