import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { request, send } from './api'
import { Glyph } from './Controls'
import { StatusNote, notify } from './Toast'

type Counts = { characters: number; photos: number; scenes: number; results: number }
type Item = { name: string; size: number; created_at: string | null; counts: Counts | null; encrypted?: boolean; problem?: string }
type State = { running: boolean; error: string | null; last: string | null; folder: string; items: Item[] }
type Check = { ok: boolean; files?: number; counts?: Counts; problem?: string }

const MIN_PASSWORD = 10
function passwordProblem(password: string) {
  if (password.length < MIN_PASSWORD) return `At least ${MIN_PASSWORD} characters; a few words work well.`
  if (password.trim() !== password) return 'Remove the space at the start or end.'
  return ''
}

/** Phase 6D: plain or password-protected backup. The password is never saved anywhere. */
function CreateDialog({ onClose, onCreate }: { onClose: () => void; onCreate: (password: string | null) => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const [protect, setProtect] = useState(true)
  const [password, setPassword] = useState('')
  const [again, setAgain] = useState('')
  const [show, setShow] = useState(false)
  useEffect(() => { ref.current?.showModal() }, [])
  const problem = protect ? passwordProblem(password) || (again && again !== password ? 'The two passwords differ.' : '') : ''
  const ready = !protect || (!problem && again === password)
  function submit(e: FormEvent) { e.preventDefault(); if (ready) { onCreate(protect ? password : null); onClose() } }
  return <dialog ref={ref} className="image-dialog text-dialog backup-dialog" aria-labelledby="backup-create-title" onClose={onClose}>
    <form className="text-dialog-form" onSubmit={submit}>
      <h2 id="backup-create-title">Create backup</h2>
      <div className="engine-cards backup-kinds" role="radiogroup" aria-label="Kind of backup">
        <label className={`engine-card ${protect ? 'selected' : ''}`}><input type="radio" name="backup-kind" checked={protect} onChange={() => setProtect(true)} />
          <span className="engine-card-body"><span className="engine-card-top"><strong>Protect with a password</strong><span className="engine-tag">Recommended for copies</span></span>
            <span className="engine-card-line">Encrypted (AES-256). Safe to keep on a USB drive or in cloud storage.</span></span></label>
        <label className={`engine-card ${protect ? '' : 'selected'}`}><input type="radio" name="backup-kind" checked={!protect} onChange={() => setProtect(false)} />
          <span className="engine-card-body"><span className="engine-card-top"><strong>Plain backup</strong></span>
            <span className="engine-card-line">No password. Anyone with the file can open it; fine on this computer.</span></span></label>
      </div>
      {protect && <>
        {/* Lets a password manager file the password under a clear name. */}
        <input type="text" name="username" autoComplete="username" value="Character Studio backup" readOnly hidden />
        <label htmlFor="backup-password">Password</label>
        <input id="backup-password" type={show ? 'text' : 'password'} autoComplete="new-password" autoFocus value={password} onChange={e => setPassword(e.target.value)} />
        <label htmlFor="backup-password-again">Type it again</label>
        <input id="backup-password-again" type={show ? 'text' : 'password'} autoComplete="new-password" value={again} onChange={e => setAgain(e.target.value)} />
        <label className="checkbox-label"><input type="checkbox" checked={show} onChange={e => setShow(e.target.checked)} /><span>Show the password</span></label>
        <p className={problem && (password || again) ? 'frame-error' : 'hint'} role="status">{problem && (password || again) ? problem : `At least ${MIN_PASSWORD} characters.`}</p>
        <div className="check-box warning"><strong>Keep this password safe</strong><p>The studio never saves it. If it is forgotten, nobody can open this backup, not even you. A password manager is a good place for it.</p></div>
      </>}
      <div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Cancel</button>
        <button disabled={!ready}>{protect ? 'Create protected backup' : 'Create backup'}</button></div>
    </form>
  </dialog>
}

/** Ask for a protected backup's password to check it. Nothing is saved. */
function PasswordDialog({ item, onClose, onCheck }: { item: Item; onClose: () => void; onCheck: (password: string) => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const [password, setPassword] = useState('')
  useEffect(() => { ref.current?.showModal() }, [])
  return <dialog ref={ref} className="image-dialog text-dialog backup-dialog" aria-labelledby="backup-password-title" onClose={onClose}>
    <form className="text-dialog-form" onSubmit={e => { e.preventDefault(); if (password) { onCheck(password); onClose() } }}>
      <h2 id="backup-password-title">Check protected backup</h2>
      <p className="hint">{item.name}. The password is used for this check only and is not saved.</p>
      <input type="text" name="username" autoComplete="username" value="Character Studio backup" readOnly hidden />
      <label htmlFor="check-password">Password</label>
      <input id="check-password" type="password" autoComplete="current-password" autoFocus value={password} onChange={e => setPassword(e.target.value)} />
      <div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Cancel</button><button disabled={!password}>Check</button></div>
    </form>
  </dialog>
}

const size = (bytes: number) => bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`
const when = (value: string | null) => value ? new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : 'Unknown date'

/** Studio settings: make, check, download and delete backups; restore runs while stopped. */
export default function Backups({ token }: { token: string }) {
  const [state, setState] = useState<State | null>(null)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [checks, setChecks] = useState<Record<string, Check | 'checking'>>({})
  const [creating, setCreating] = useState(false)
  const [asking, setAsking] = useState<Item | null>(null)
  const load = useCallback(() => request<State>('/api/backups').then(setState, e => setError(e.message)), [])
  useEffect(() => { void load() }, [load])
  // Poll only while a backup is being made; it runs on the server.
  useEffect(() => {
    if (!state?.running) return
    const timer = window.setInterval(() => void load(), 1000)
    return () => window.clearInterval(timer)
  }, [state?.running, load])
  useEffect(() => { if (state && !state.running && state.last && note === 'Making a backup…') setNote(state.last.endsWith('.csbackup') ? 'Protected backup saved. Download it or copy it to another drive; keep the password safe.' : 'Backup saved. Download it or copy it to another drive to keep it safe.') }, [state, note])

  async function create(password: string | null) {
    setError(''); setNote('Making a backup…')
    try { setState(await send<State>('/api/backups', 'POST', token, password ? { password } : undefined)) } catch (e) { setNote(''); setError(e instanceof Error ? e.message : 'The backup could not be started.') }
  }
  async function check(name: string, password?: string) {
    setChecks(c => ({ ...c, [name]: 'checking' }))
    try {
      const result = await send<Check>(`/api/backups/${name}/verify`, 'POST', token, password ? { password } : undefined)
      setChecks(c => ({ ...c, [name]: result }))
      if (result.ok) notify(`Backup checked. All ${result.files} files match.`)
    }
    catch (e) { setChecks(c => ({ ...c, [name]: { ok: false, problem: e instanceof Error ? e.message : 'The check could not be finished.' } })) }
  }
  async function remove(item: Item) {
    if (!window.confirm(`Delete the backup from ${when(item.created_at)}? This removes the file from your data folder. Copies you downloaded are not affected.`)) return
    try { setState(await send<State>(`/api/backups/${item.name}`, 'DELETE', token)); setNote('Backup deleted.') } catch (e) { setError(e instanceof Error ? e.message : 'The backup could not be deleted.') }
  }
  const copy = (text: string) => navigator.clipboard.writeText(text).then(() => setNote('Folder path copied.'), () => setNote('Copy failed. Select the path and copy it yourself.'))

  return <section className="panel backups-panel" aria-labelledby="backups-title">
    <div className="panel-head"><div><span className="tiny-label">YOUR SAFETY NET</span><h2 id="backups-title">Backups</h2></div>
      <button type="button" disabled={!state || state.running} onClick={() => setCreating(true)}>{state?.running ? 'Making a backup…' : 'Create backup'}</button></div>
    <p>One file with your database, characters and photos, scenes, results and run folders, with a fingerprint of every file so it can be checked. You can protect it with a password. The studio keeps working while it is made.</p>
    {state?.error && <p className="frame-error" role="alert">The last backup failed: {state.error}</p>}
    {error && <p className="frame-error" role="alert">{error}</p>}
    <StatusNote text={note} />
    {state && (!state.items.length ? <p className="hint">No backups yet.</p> : <ul className="backup-list">{state.items.map(item => {
      const result = checks[item.name]
      const counts = item.counts ?? (result && result !== 'checking' && result.ok ? result.counts ?? null : null)
      return <li key={item.name}>
        <div className="backup-copy"><strong>{when(item.created_at)}{item.encrypted && <span className="lock-chip"><Glyph name="lock" />Password protected</span>}</strong>
          <span className="hint">{size(item.size)}{counts ? ` · ${plural(counts.characters, 'character')}, ${plural(counts.photos, 'photo')}, ${plural(counts.scenes, 'scene')}, ${plural(counts.results, 'result')}` : item.encrypted ? ' · contents shown after a check with the password' : ''}</span>
          {item.problem && <span className="frame-error">{item.problem}</span>}
          {result === 'checking' ? <span className="hint">Checking every file…</span> : result ? <span className={result.ok ? 'check-ok' : 'frame-error'}>{result.ok ? `Checked: all ${result.files} files match.` : result.problem}</span> : null}</div>
        <span className="backup-actions">
          <a className="button-link compact" href={`/api/backups/${item.name}/download`} download><Glyph name="download" />Download</a>
          <button type="button" className="secondary compact" disabled={result === 'checking'} onClick={() => item.encrypted ? setAsking(item) : void check(item.name)}><Glyph name="check" />{result === 'checking' ? 'Checking…' : 'Check'}</button>
          <button type="button" className="danger secondary compact" onClick={() => void remove(item)}><Glyph name="trash" />Delete</button>
        </span>
      </li>
    })}</ul>)}
    {state && <div className="backup-folder"><span className="hint">Saved in</span> <code>{state.folder}</code> <button type="button" className="secondary compact" onClick={() => void copy(state.folder)}><Glyph name="folder" />Copy path</button></div>}
    <div className="privacy-note"><strong>Keep a copy elsewhere, and restoring</strong><p>Backups sit in your data folder, so copy or download them to another drive as well; protect those copies with a password. To restore, stop the studio with Stop-Studio.cmd, then double-click Restore-Studio.cmd (or drop a backup file onto it). It asks for the password of a protected backup, checks the backup first and keeps your current data folder, renamed, so nothing is lost. API keys are never in backups.</p></div>
    {creating && <CreateDialog onClose={() => setCreating(false)} onCreate={password => void create(password)} />}
    {asking && <PasswordDialog item={asking} onClose={() => setAsking(null)} onCheck={password => void check(asking.name, password)} />}
  </section>
}
