import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError, getBootstrap, request, savePreferences, type Bootstrap } from './api'

import Engines from './Engines'
import Library from './Library'
import { replaceRoute, routeParts } from './route'
import ResultsGallery, { ResultCard, type Result } from './Results'
import Scenes, { StageChip, type SceneSummary } from './Scenes'

type Page = 'overview' | 'settings' | 'characters' | 'scenes' | 'results'
const pageRoutes: Record<string, Page> = { characters: 'characters', groups: 'characters', settings: 'settings', scenes: 'scenes', results: 'results' }
const titles: Record<Page, [string, string]> = {
  overview: ['Overview', 'A little structure for a world of possibilities.'],
  characters: ['Your character library', 'Familiar faces, ready for the stories ahead.'],
  scenes: ['Your scenes', 'A reference. A new possibility.'],
  results: ['Your results', 'Every version has a home.'],
  settings: ['Studio settings', 'Make this space yours. Keep your work close.'],
}

const upcoming = [
  { name: 'Batch processing', phase: '5.5', text: 'Many scenes, one calm queue.', detail: 'Analyse or generate several approved scenes in a row, pausing when a plan limit is reached.' },
  { name: 'Quality and refinements', phase: '06', text: 'Closer, one detail at a time.', detail: 'Optional extras such as region-based editing, fidelity checks and saved presets.' },
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
  const [scenes, setScenes] = useState<SceneSummary[]>([])
  const [latest, setLatest] = useState<Result[]>([])
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
  useEffect(() => {
    if (page === 'overview' && data) {
      request<SceneSummary[]>('/api/scenes').then(setScenes, () => setScenes([]))
      request<Result[]>('/api/results').then(list => setLatest(list.slice(0, 4)), () => setLatest([]))
    }
  }, [page, data])

  const dirty = !!data && name !== data.preferences.studio_name
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault() }
    if (dirty || libraryDirty || libraryBusy) window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty, libraryDirty, libraryBusy])

  function navigate(next: Page, path?: string) {
    if ((next === page && !path) || libraryBusy) return
    if (libraryDirty && !window.confirm('Leave this page and discard unsaved edits?')) return
    replaceRoute(path ?? (next === 'overview' ? '' : next))
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

  const recent = [...scenes].sort((a, b) => (b.last_opened_at ?? b.updated_at).localeCompare(a.last_opened_at ?? a.updated_at)).slice(0, 4)
  const resume = recent[0]

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
          <button disabled={libraryBusy} aria-current={page === 'scenes' ? 'page' : undefined} className={page === 'scenes' ? 'nav-item active' : 'nav-item'} onClick={() => navigate('scenes')}>
            <svg className="nav-symbol" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="8.5" cy="9.5" r="1.5" /><path d="M3 17l5-5 5 5 3-3 5 5" /></svg> Scenes
          </button>
          <button disabled={libraryBusy} aria-current={page === 'results' ? 'page' : undefined} className={page === 'results' ? 'nav-item active' : 'nav-item'} onClick={() => navigate('results')}>
            <svg className="nav-symbol" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"><rect x="7" y="7" width="14" height="14" rx="2" /><path d="M17 7V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h2" /><path d="M14 10.5l.9 2 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9z" /></svg> Results
          </button>
          <button disabled={libraryBusy} aria-current={page === 'settings' ? 'page' : undefined} className={page === 'settings' ? 'nav-item active' : 'nav-item'} onClick={() => navigate('settings')}>
            <svg className="nav-symbol" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3 7h18M3 17h18" /><circle cx="8" cy="7" r="3" fill="var(--surface)" /><circle cx="16" cy="17" r="3" fill="var(--surface)" /></svg> Studio settings
          </button>
        </nav>
        <div className="sidebar-note"><span className="tiny-label">BUILT AROUND YOU</span><p>Your characters.<br />Your scenes.<br />Your computer.</p><span className="version">Generation & Results · Phase 5</span></div>
      </aside>

      <div className="workspace">
        <header className="topbar"><span>Workspace <span className="crumb">/</span> {page === 'overview' ? 'Overview' : page === 'characters' ? 'Characters' : page === 'scenes' ? 'Scenes' : page === 'results' ? 'Results' : 'Settings'}</span>
          <span className={`connection ${data && !error ? 'online' : ''}`}><span aria-hidden="true" />{loading ? 'Connecting…' : error ? 'Needs attention' : 'Local studio connected'}</span>
        </header>
        <main id="main" tabIndex={-1}>
          <div className="page-heading"><div><p className="eyebrow">CHARACTER STUDIO / PHASE 05</p>
            <h1 ref={heading} tabIndex={-1}>{page === 'overview' ? (data?.preferences.studio_name || 'Your studio') : titles[page][0]}</h1>
            <p className="intro">{titles[page][1]}</p></div>
            <span className="phase-badge">Local & private</span>
          </div>

          {error && <div className="error" role="alert"><strong>Something needs your attention.</strong><p>{error}</p>
            {(!data || conflict) && <button className="secondary" onClick={() => void load()}>{conflict ? 'Discard local edit and reload' : 'Try again'}</button>}
          </div>}

          {loading ? <div className="loading" role="status">Opening your local workspace…</div> : data && <>
            {page === 'characters' ? <Library data={data} onDirty={setLibraryDirty} onBusy={setLibraryBusy} onSession={setData} /> : page === 'scenes' ? <Scenes data={data} onDirty={setLibraryDirty} onBusy={setLibraryBusy} /> : page === 'results' ? <ResultsGallery data={data} onOpenScene={id => navigate('scenes', `scenes/${id}/generate`)} /> : page === 'overview' ? <>
              <section className="welcome-panel" aria-labelledby="welcome-title">
                <div className="welcome-copy"><span className="tiny-label">THE START OF SOMETHING PERSONAL</span>
                  <h2 id="welcome-title">Same characters.<br /><em>New stories.</em></h2>
                  <p>Save your characters and their reference photos, then add scenes. The studio analyses each Base Image, you choose who appears where and approve the exact prompt and photos, then generate with Codex or any app you like.</p>
                  {resume ? <button onClick={() => navigate('scenes', `scenes/${resume.id}`)}>Resume “{resume.title}” <span aria-hidden="true">↗</span></button>
                    : <button onClick={() => navigate('scenes')}>Create your first scene <span aria-hidden="true">↗</span></button>}
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
                <div><span className="status-dot" /><div><strong>No paid API connected</strong><p>Analysis, polishing and generation run on your own Claude or ChatGPT sign-in, only when you click</p></div></div>
              </section>

              {scenes.length > 0 && <><div className="section-title"><h2>Recent scenes</h2><button className="link-button" onClick={() => navigate('scenes')}>All scenes</button></div>
                <section className="recent-scenes" aria-label="Recent scenes">{recent.map(s => <div key={s.id} className="scene-card"><button className="card-main" onClick={() => navigate('scenes', `scenes/${s.id}`)}>
                  <span className="scene-thumb"><img src={s.thumbnail_url} alt="" loading="lazy" /></span>
                  <span className="scene-card-copy"><strong>{s.title}</strong><span className="scene-card-meta"><StageChip state={s.workflow_state} /></span></span>
                </button></div>)}</section></>}

              {latest.length > 0 && <><div className="section-title"><h2>Latest results</h2><button className="link-button" onClick={() => navigate('results')}>All results</button></div>
                <section className="result-grid recent-results" aria-label="Latest results">{latest.map(r => <ResultCard key={r.id} result={r} title={r.scene_title} onOpen={() => navigate('scenes', `scenes/${r.scene_id}/generate`)} />)}</section></>}

              <div className="section-title"><h2>What’s taking shape</h2><span>WHAT COMES NEXT</span></div>
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
              <Engines token={data.session_token} />
            </div>}
          </>}
        </main>
        <footer><span>Character Studio</span><span>Local-first. Thoughtfully connected.</span></footer>
      </div>
    </div>
  )
}
