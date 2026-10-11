import { useCallback, useEffect, useState } from 'react'
import { request, send } from './api'
import { Glyph } from './Controls'

type Counts = { characters: number; photos: number; scenes: number; results: number }
type Item = { name: string; size: number; created_at: string | null; counts: Counts | null; problem?: string }
type State = { running: boolean; error: string | null; last: string | null; folder: string; items: Item[] }
type Check = { ok: boolean; files?: number; problem?: string }

const size = (bytes: number) => bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`
const when = (value: string | null) => value ? new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : 'Unknown date'

/** Studio settings: make, check, download and delete backups; restore runs while stopped. */
export default function Backups({ token }: { token: string }) {
  const [state, setState] = useState<State | null>(null)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [checks, setChecks] = useState<Record<string, Check | 'checking'>>({})
  const load = useCallback(() => request<State>('/api/backups').then(setState, e => setError(e.message)), [])
  useEffect(() => { void load() }, [load])
  // Poll only while a backup is being made; it runs on the server.
  useEffect(() => {
    if (!state?.running) return
    const timer = window.setInterval(() => void load(), 1000)
    return () => window.clearInterval(timer)
  }, [state?.running, load])
  useEffect(() => { if (state && !state.running && state.last && note === 'Making a backup…') setNote('Backup saved. Download it or copy it to another drive to keep it safe.') }, [state, note])

  async function create() {
    setError(''); setNote('Making a backup…')
    try { setState(await send<State>('/api/backups', 'POST', token)) } catch (e) { setNote(''); setError(e instanceof Error ? e.message : 'The backup could not be started.') }
  }
  async function check(name: string) {
    setChecks(c => ({ ...c, [name]: 'checking' }))
    try { const result = await send<Check>(`/api/backups/${name}/verify`, 'POST', token); setChecks(c => ({ ...c, [name]: result })) }
    catch (e) { setChecks(c => ({ ...c, [name]: { ok: false, problem: e instanceof Error ? e.message : 'The check could not be finished.' } })) }
  }
  async function remove(item: Item) {
    if (!window.confirm(`Delete the backup from ${when(item.created_at)}? This removes the file from your data folder. Copies you downloaded are not affected.`)) return
    try { setState(await send<State>(`/api/backups/${item.name}`, 'DELETE', token)); setNote('Backup deleted.') } catch (e) { setError(e instanceof Error ? e.message : 'The backup could not be deleted.') }
  }
  const copy = (text: string) => navigator.clipboard.writeText(text).then(() => setNote('Folder path copied.'), () => setNote('Copy failed. Select the path and copy it yourself.'))

  return <section className="panel backups-panel" aria-labelledby="backups-title">
    <div className="panel-head"><div><span className="tiny-label">YOUR SAFETY NET</span><h2 id="backups-title">Backups</h2></div>
      <button type="button" disabled={!state || state.running} onClick={() => void create()}>{state?.running ? 'Making a backup…' : 'Create backup'}</button></div>
    <p>One file with your database, characters and photos, scenes, results and run folders, with a fingerprint of every file so it can be checked. The studio keeps working while it is made.</p>
    {state?.error && <p className="frame-error" role="alert">The last backup failed: {state.error}</p>}
    {error && <p className="frame-error" role="alert">{error}</p>}
    <p className="library-status" role="status">{note}</p>
    {state && (!state.items.length ? <p className="hint">No backups yet.</p> : <ul className="backup-list">{state.items.map(item => {
      const result = checks[item.name]
      return <li key={item.name}>
        <div className="backup-copy"><strong>{when(item.created_at)}</strong>
          <span className="hint">{size(item.size)}{item.counts ? ` · ${plural(item.counts.characters, 'character')}, ${plural(item.counts.photos, 'photo')}, ${plural(item.counts.scenes, 'scene')}, ${plural(item.counts.results, 'result')}` : ''}</span>
          {item.problem && <span className="frame-error">{item.problem}</span>}
          {result === 'checking' ? <span className="hint">Checking every file…</span> : result ? <span className={result.ok ? 'check-ok' : 'frame-error'}>{result.ok ? `Checked: all ${result.files} files match.` : result.problem}</span> : null}</div>
        <span className="backup-actions">
          <a className="button-link compact" href={`/api/backups/${item.name}/download`} download><Glyph name="download" />Download</a>
          <button type="button" className="secondary compact" disabled={result === 'checking'} onClick={() => void check(item.name)}><Glyph name="check" />{result === 'checking' ? 'Checking…' : 'Check'}</button>
          <button type="button" className="danger secondary compact" onClick={() => void remove(item)}><Glyph name="trash" />Delete</button>
        </span>
      </li>
    })}</ul>)}
    {state && <div className="backup-folder"><span className="hint">Saved in</span> <code>{state.folder}</code> <button type="button" className="secondary compact" onClick={() => void copy(state.folder)}><Glyph name="folder" />Copy path</button></div>}
    <div className="privacy-note"><strong>Keep a copy elsewhere, and restoring</strong><p>Backups sit in your data folder, so copy or download them to another drive as well. To restore, stop the studio with Stop-Studio.cmd, then double-click Restore-Studio.cmd (or drop a backup file onto it). It checks the backup first and keeps your current data folder, renamed, so nothing is lost.</p></div>
  </section>
}
