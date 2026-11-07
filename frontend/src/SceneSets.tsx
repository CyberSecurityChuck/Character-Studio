import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { ApiError, request, send, type Bootstrap } from './api'
import { Dialog, plural } from './Batches'
import { CardMenu, Glyph } from './Controls'
import type { Character } from './Library'
import { StageChip, type SceneDetail, type SceneSummary } from './Scenes'

// Phase 7A: scene sets, the Scenes page stage filters and the free duplicate checks (D030, D031).

export type SceneSet = { id: string; name: string; revision: number; scene_count: number; created_at: string; updated_at: string }
export type StageFilter = 'all' | 'not_analysed' | 'needs_check' | 'ready_to_approve' | 'approved' | 'completed' | 'running' | 'problems'

export const stageFilters: { id: StageFilter; label: string }[] = [
  { id: 'all', label: 'All' }, { id: 'not_analysed', label: 'Not analysed' }, { id: 'needs_check', label: 'Needs your check' },
  { id: 'ready_to_approve', label: 'Prompt ready to approve' }, { id: 'approved', label: 'Approved, not generated' },
  { id: 'completed', label: 'Completed' }, { id: 'running', label: 'Running / waiting' }, { id: 'problems', label: 'Problems' },
]
export const inStage = (scene: SceneSummary, stage: StageFilter) => stage === 'all' || (stage === 'problems' ? !!scene.problem : scene.stage === stage)

const kindWords: Record<string, string> = { analysis: 'analysis', polish: 'polish', generation: 'generation', export: 'manual export', check: 'quality check', edit: 'region edit' }
export const problemLabel = (problem: NonNullable<SceneSummary['problem']>) => `Last ${kindWords[problem.kind] ?? 'run'} ${problem.status === 'interrupted' ? 'was interrupted' : 'failed'}`

/** The stages in workflow order as separate count cards (the set's dashboard); Problems comes last. */
export function StageFilters({ scenes, value, onChange, compact }: { scenes: SceneSummary[]; value: StageFilter; onChange: (stage: StageFilter) => void; compact?: boolean }) {
  const tile = (f: (typeof stageFilters)[number]) => {
    const count = scenes.filter(s => inStage(s, f.id)).length
    return <button key={f.id} type="button" className={`stage-tile tile-${f.id} ${count ? '' : 'empty'}`} aria-pressed={value === f.id} onClick={() => onChange(f.id)}>
      <strong>{f.id === 'running' && count > 0 && <span className="live-dot" aria-hidden="true" />}{count}</strong><span>{f.label}</span>
    </button>
  }
  return <div className={`stage-pipeline ${compact ? 'compact' : ''}`} role="group" aria-label="Filter by stage">
    {stageFilters.map(tile)}
  </div>
}

/** The chosen set's title area: name, size and date, with Rename and Delete in a ⋯ menu. */
export function SetHeader({ item, disabled, onRename, onDelete, onResults, actions }: { item: SceneSet; disabled: boolean; onRename: () => void; onDelete: () => void; onResults?: () => void; actions?: React.ReactNode }) {
  return <section className="set-header" aria-label={`Scene set ${item.name}`}>
    <span className="set-icon"><Glyph name="folder" /></span>
    <div className="set-title"><h2>{item.name}</h2><p>{plural(item.scene_count, 'scene')} · created {new Date(item.created_at).toLocaleDateString(undefined, { dateStyle: 'medium' })}</p></div>
    {actions}
    <CardMenu label={`scene set ${item.name}`} disabled={disabled} items={[...(onResults ? [{ label: 'View results', onSelect: onResults }] : []), { label: 'Rename set', onSelect: onRename }, { label: 'Delete set', danger: true, onSelect: onDelete }]} />
  </section>
}

/** Choose an existing set, no set, or name a new one; used at import and for Move to set. */
function SetPicker({ sets, value, newName, onChange, onName, disabled, id }: { sets: SceneSet[]; value: string; newName: string; onChange: (value: string) => void; onName: (name: string) => void; disabled?: boolean; id: string }) {
  return <div className="set-picker">
    <div><label htmlFor={id}>Scene set</label>
      <select id={id} value={value} disabled={disabled} onChange={e => onChange(e.target.value)}>
        <option value="">No set</option>
        {sets.map(s => <option key={s.id} value={s.id}>{s.name} ({s.scene_count})</option>)}
        <option value="new">New set…</option>
      </select></div>
    {value === 'new' && <div><label htmlFor={`${id}-name`}>New set name</label><input id={`${id}-name`} maxLength={80} value={newName} disabled={disabled} placeholder="For example: Beach shoot" onChange={e => onName(e.target.value)} /></div>}
  </div>
}

async function chosenSet(value: string, name: string, token: string): Promise<string | null> {
  if (value !== 'new') return value || null
  return (await send<SceneSet>('/api/scene-sets', 'POST', token, { name: name.trim() })).id
}

type Match = { id: string; title: string; thumbnail_url: string; created_at: string; distance?: number }
type Check = { content_hash: string; perceptual_hash: string; near_copy_bits: number; exact: Match[]; near: Match[] }
type Entry = { file: File; title: string; preview: string; check?: Check; error?: string; twin?: { index: number; exact: boolean }; include: boolean; character?: string }

const MAX_NEW_SCENES = 500
const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const isImage = (file: File) => IMAGE_TYPES.includes(file.type) || /\.(jpe?g|png|webp)$/i.test(file.name)
const titleFrom = (file: File) => file.name.replace(/\.[^.]+$/, '').trim().slice(0, 120) || 'Untitled scene'
const bits = (a: string, b: string) => { let x = BigInt(`0x${a}`) ^ BigInt(`0x${b}`), n = 0; while (x) { n += Number(x & 1n); x >>= 1n } return n }
// Shown instead of the browser's broken-image icon when a file cannot be previewed.
const NO_PREVIEW = `data:image/svg+xml,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 42"><rect width="64" height="42" fill="#8f8a8233"/><path d="M24 27l5-6 4 4 3-3 4 5z M27 17a2 2 0 1 0 0.1 0" fill="none" stroke="#8f8a82" stroke-width="1.5" stroke-linejoin="round"/></svg>')}`
const flagged = (e: Entry) => !!(e.check?.exact.length || e.check?.near.length || e.twin)

type CopyInfo = { kind: 'error' | 'checking' | 'clear' | 'copy'; text: string; picture?: { src: string; alt: string } }

/** Why a file is unticked: an exact or near copy in the studio or earlier in this selection. */
function copyInfo(entry: Entry, entries: Entry[]): CopyInfo {
  if (entry.error) return { kind: 'error', text: entry.error }
  if (!entry.check) return { kind: 'checking', text: 'Checking for copies…' }
  const { exact, near } = entry.check
  const twin = entry.twin ? entries[entry.twin.index] : null
  if (!exact.length && !near.length && !twin) return { kind: 'clear', text: 'No copies found' }
  const match = exact[0] ?? near[0]
  // A scene already in the studio is named first; the picture always shows what the text names.
  const text = exact.length ? `Exact copy of “${exact[0].title}”${exact.length > 1 ? ` and ${plural(exact.length - 1, 'other scene')}` : ''}`
    : near.length ? `Looks like “${near[0].title}” (re-saved, resized or another format)`
      : `${entry.twin!.exact ? 'Exact copy' : 'Looks like a copy'} of “${twin!.title || titleFrom(twin!.file)}” in this selection`
  return { kind: 'copy', text, picture: match ? { src: match.thumbnail_url, alt: `Matching image: ${match.title}` } : { src: twin!.preview, alt: `Matching image: ${twin!.file.name}` } }
}

/** The single-image layout has room to show the note in full. */
function CopyNote({ entry, entries }: { entry: Entry; entries: Entry[] }) {
  const info = copyInfo(entry, entries)
  return <span className={`copy-note is-${info.kind}`}>{info.picture && <img src={info.picture.src} alt={info.picture.alt} />}<small>{info.text}</small></span>
}

const statusIcons: Record<CopyInfo['kind'], React.ReactNode> = {
  copy: <><path d="M12 4.2 2.8 19.5h18.4z" /><path d="M12 10v4.4M12 17.2v.1" /></>,
  clear: <><circle cx="12" cy="12" r="8.6" /><path d="m8.2 12.2 2.6 2.6 5-5.4" /></>,
  error: <><circle cx="12" cy="12" r="8.6" /><path d="m9 9 6 6M15 9l-6 6" /></>,
  checking: <path d="M12 3.4a8.6 8.6 0 1 1-8.6 8.6" />,
}

/** A list row's copy result as one icon after the title; the message opens on hover, focus or a click. */
function CopyStatus({ entry, entries }: { entry: Entry; entries: Entry[] }) {
  const info = copyInfo(entry, entries)
  const [at, setAt] = useState<{ top: number; left: number } | null>(null)
  const button = useRef<HTMLButtonElement>(null)
  const id = useId()
  // Fixed position, so the scrolling list never clips the card; it closes when anything scrolls.
  const show = () => { const r = button.current?.getBoundingClientRect(); if (r) setAt({ top: r.top + r.height / 2, left: r.left - 10 }) }
  const hide = () => setAt(null)
  useEffect(() => {
    if (!at) return
    const key = (e: globalThis.KeyboardEvent) => { if (e.key === 'Escape') hide() }
    window.addEventListener('scroll', hide, true); window.addEventListener('keydown', key)
    return () => { window.removeEventListener('scroll', hide, true); window.removeEventListener('keydown', key) }
  }, [at])
  return <span className={`copy-status is-${info.kind}`} onMouseEnter={show} onMouseLeave={hide}>
    <button ref={button} type="button" className="status-icon" aria-label={info.text} aria-describedby={at ? id : undefined} onClick={() => at ? hide() : show()} onFocus={show} onBlur={hide}>
      <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{statusIcons[info.kind]}</svg>
    </button>
    {at && <span role="tooltip" id={id} className={`copy-pop is-${info.kind}`} style={{ top: at.top, left: at.left }}>
      {info.picture && <img src={info.picture.src} alt="" />}<span>{info.text}</span>
    </span>}
  </span>
}

/** Files dragged in from the computer; a dropped folder is read with its subfolders, like Choose a folder. */
async function droppedFiles(data: DataTransfer): Promise<File[]> {
  // Entries must be taken before the first await: the drop's data is cleared afterwards.
  const roots = [...data.items].map(item => item.webkitGetAsEntry?.()).filter((e): e is FileSystemEntry => !!e)
  if (!roots.length) return [...data.files]
  const found: { path: string; file: File }[] = []
  async function walk(entry: FileSystemEntry) {
    if (entry.isFile) found.push({ path: entry.fullPath, file: await new Promise<File>((ok, fail) => (entry as FileSystemFileEntry).file(ok, fail)) })
    else if (entry.isDirectory) {
      const reader = (entry as FileSystemDirectoryEntry).createReader()
      // readEntries returns a folder in parts; an empty part means the end.
      for (;;) {
        const part = await new Promise<FileSystemEntry[]>((ok, fail) => reader.readEntries(ok, fail))
        if (!part.length) break
        for (const child of part) await walk(child)
      }
    }
  }
  for (const root of roots) await walk(root)
  return found.sort((a, b) => a.path.localeCompare(b.path, undefined, { numeric: true })).map(f => f.file)
}

/** Add scenes from files or a whole folder, after free local copy checks (Phase 7A). */
export function ImportForm({ data, sets, defaultSet, onCreated, onCreatedMany, onCancel }: { data: Bootstrap; sets: SceneSet[]; defaultSet: string; onCreated: (scene: SceneDetail) => void; onCreatedMany: (created: SceneDetail[], failed: string[], setId: string | null) => void; onCancel: () => void }) {
  const token = data.session_token
  const [entries, setEntries] = useState<Entry[]>([])
  const [ignored, setIgnored] = useState(0)
  const [checking, setChecking] = useState(false)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(0)
  const [error, setError] = useState('')
  const [setValue, setSetValue] = useState(defaultSet)
  const [setName, setSetName] = useState('')
  const [dragging, setDragging] = useState(false)
  const [characters, setCharacters] = useState<Character[]>([])
  const [allCharacter, setAllCharacter] = useState('')
  const run = useRef(0)
  const previews = useRef<string[]>([])
  const limitMb = Math.floor(data.max_upload_bytes / 1048576)
  // Stop checking and free the previews when the dialog closes.
  useEffect(() => () => { run.current += 1; previews.current.forEach(url => URL.revokeObjectURL(url)) }, [])
  useEffect(() => { request<Character[]>('/api/characters').then(list => setCharacters(list.filter(c => !c.archived && c.photos.length > 0)), () => undefined) }, [])

  async function checkAll(list: Entry[], token_: number) {
    setChecking(true)
    const next = [...list]
    for (const [index, entry] of next.entries()) {
      if (run.current !== token_) return
      if (entry.file.size > data.max_upload_bytes) { next[index] = { ...entry, error: `Larger than ${limitMb} MB`, include: false }; setEntries([...next]); continue }
      try {
        const check = await request<Check>('/api/scene-imports/check', { method: 'POST', headers: { 'X-Studio-Token': token, 'Content-Type': 'application/octet-stream' }, body: entry.file }, 'This image could not be checked.')
        // Also compare with the files before it, so a folder with two copies imports one.
        const earlier = next.slice(0, index).map((e, i) => ({ e, i })).filter(({ e }) => e.check)
        const same = earlier.find(({ e }) => e.check!.content_hash === check.content_hash)
        const alike = same ?? earlier.find(({ e }) => bits(e.check!.perceptual_hash, check.perceptual_hash) <= check.near_copy_bits)
        const twin = alike ? { index: alike.i, exact: !!same } : undefined
        const item = { ...entry, check, twin }
        next[index] = { ...item, include: !flagged(item) }
      } catch (e) {
        next[index] = { ...entry, error: e instanceof Error ? e.message : 'This image could not be checked.', include: false }
      }
      if (run.current !== token_) return
      setEntries([...next])
    }
    setChecking(false)
  }

  function choose(list: FileList | File[] | null) {
    const all = [...(list ?? [])]
    if (!all.length) return
    const images = all.filter(isImage)
    setIgnored(all.length - images.length)
    setError(images.length > MAX_NEW_SCENES ? `You chose ${images.length} images. Up to ${MAX_NEW_SCENES} are added at a time, so the first ${MAX_NEW_SCENES} are listed.` : images.length ? '' : 'No JPEG, PNG or WebP images were found there.')
    const kept = images.slice(0, MAX_NEW_SCENES).map(file => ({ file, title: images.length === 1 ? '' : titleFrom(file), preview: URL.createObjectURL(file), include: false, character: allCharacter }))
    previews.current.forEach(url => URL.revokeObjectURL(url))
    previews.current = kept.map(e => e.preview)
    setEntries(kept)
    run.current += 1
    if (kept.length) void checkAll(kept, run.current)
  }
  // Dropping anywhere while the dialog is open adds the files (and never opens them in the browser).
  const chooseRef = useRef(choose)
  chooseRef.current = choose
  useEffect(() => {
    const hasFiles = (e: DragEvent) => !!e.dataTransfer && [...e.dataTransfer.types].includes('Files')
    const over = (e: DragEvent) => { if (!hasFiles(e)) return; e.preventDefault(); e.dataTransfer!.dropEffect = busy ? 'none' : 'copy'; if (!busy) setDragging(true) }
    const leave = (e: DragEvent) => { if (!e.relatedTarget) setDragging(false) }
    const drop = (e: DragEvent) => {
      if (!hasFiles(e)) return
      e.preventDefault(); setDragging(false)
      if (busy) return
      droppedFiles(e.dataTransfer!).then(files => chooseRef.current(files), () => setError('Those files could not be read. Use Choose images or Choose a folder instead.'))
    }
    window.addEventListener('dragover', over); window.addEventListener('dragleave', leave); window.addEventListener('drop', drop)
    return () => { window.removeEventListener('dragover', over); window.removeEventListener('dragleave', leave); window.removeEventListener('drop', drop) }
  }, [busy])
  const update = (index: number, change: Partial<Entry>) => setEntries(list => list.map((e, i) => i === index ? { ...e, ...change } : e))
  const remove = (index: number) => setEntries(list => list.filter((_, i) => i !== index).map(e => e.twin && e.twin.index >= index ? (e.twin.index === index ? { ...e, twin: undefined } : { ...e, twin: { ...e.twin, index: e.twin.index - 1 } }) : e))

  const chosen = entries.filter(e => e.include)
  const exactCount = entries.filter(e => e.check?.exact.length || e.twin?.exact).length
  const nearCount = entries.filter(e => flagged(e) && !(e.check?.exact.length || e.twin?.exact)).length
  const failedCount = entries.filter(e => e.error).length
  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!chosen.length || busy || checking) return
    if (setValue === 'new' && !setName.trim()) { setError('Name the new scene set, or choose No set.'); return }
    setBusy(true); setError(''); setDone(0)
    let setId: string | null
    try { setId = await chosenSet(setValue, setName, token) }
    catch (err) { setError(err instanceof Error ? err.message : 'The scene set could not be created.'); setBusy(false); return }
    const create = (entry: Entry) => {
      // Exact copies are refused by the server too, unless the user ticked Import anyway.
      const anyway = !!(entry.check?.exact.length || entry.twin?.exact)
      const query = new URLSearchParams({ title: entry.title.trim() || titleFrom(entry.file), ...(anyway ? { allow_duplicate: 'true' } : {}), ...(setId ? { scene_set_id: setId } : {}), ...(entry.character ? { import_character_id: entry.character } : {}) })
      return request<SceneDetail>(`/api/scenes?${query}`, { method: 'POST', headers: { 'X-Studio-Token': token, 'Content-Type': 'application/octet-stream' }, body: entry.file }, 'Check the title and image, then try again.')
    }
    if (entries.length === 1) {
      try { onCreated(await create(chosen[0])) }
      catch (err) { setError(err instanceof ApiError ? err.message : 'The scene could not be created.'); setBusy(false) }
      return
    }
    // One at a time, like single uploads, so every file passes the same checks.
    const created: SceneDetail[] = [], failed: string[] = []
    for (const [index, entry] of chosen.entries()) {
      try { created.push(await create(entry)) } catch (err) { failed.push(`${entry.file.name} (${err instanceof Error ? err.message : 'not added'})`) }
      setDone(index + 1)
    }
    setBusy(false)
    onCreatedMany(created, failed, setId)
  }

  const many = entries.length > 1
  const single = entries.length === 1 ? entries[0] : null
  const pickers = <div className="import-pickers">
    <label className="picker-button">Choose images<input className="visually-hidden" type="file" multiple accept="image/jpeg,image/png,image/webp" onChange={e => { choose(e.target.files); e.target.value = '' }} /></label>
    <label className="picker-button">Choose a folder<input className="visually-hidden" type="file" {...{ webkitdirectory: '', directory: '' }} onChange={e => { choose(e.target.files); e.target.value = '' }} /></label>
  </div>
  return <form className={`new-scene ${dragging ? 'dragging' : ''}`} onSubmit={e => void submit(e)}>
    {dragging && <div className="drop-overlay" aria-hidden="true"><Glyph name="import" /><strong>Drop images or a folder</strong><small>{entries.length ? 'They replace the list below' : 'Subfolders are included'}</small></div>}
    <h2 id="new-scene-title">{many ? `${entries.length} new scenes` : 'Add scenes'}</h2>
    <p className="hint">Drag images or a folder here, or choose them (subfolders included; other files are ignored). The studio checks each image against your scenes for exact and near copies on this computer, at no cost. Nothing is analysed until you choose to.</p>
    <fieldset disabled={busy}>
      {!entries.length ? <div className="import-start">
        <span className="drop-zone"><span><Glyph name="import" /><strong>Drag Base Images or a folder here</strong><small>or use the buttons below · JPEG, PNG or WebP · up to {limitMb} MB each · up to {MAX_NEW_SCENES} at a time</small></span></span>
        {pickers}
      </div> : single ? <div className="new-scene-body">
        <span className="drop-zone has-image"><img src={single.preview} alt="Selected Base Image" /></span>
        <div><label htmlFor="scene-title">Scene title</label><input id="scene-title" maxLength={120} value={single.title} placeholder={titleFrom(single.file)} onChange={e => update(0, { title: e.target.value })} />
          <p className="hint">Optional. The file name is used if you leave it empty.</p>
          <div className={`import-check ${flagged(single) || single.error ? 'flagged' : ''}`}><CopyNote entry={single} entries={entries} />
            {flagged(single) && <label className="checkbox-label"><input type="checkbox" checked={single.include} onChange={e => update(0, { include: e.target.checked })} /><span>Import anyway</span></label>}
          </div>
          {characters.length > 0 && <div className="import-character"><label htmlFor="scene-character">Character (optional)</label>
            <select id="scene-character" value={single.character ?? ''} onChange={e => { update(0, { character: e.target.value }); setAllCharacter(e.target.value) }}><option value="">Decide later</option>{characters.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
            <p className="hint">Given to the largest person in the picture once it is analysed.</p></div>}
          {pickers}</div>
      </div> : <div className="new-scenes">
        <p className="import-summary" role="status">{checking ? `Checking for copies… ${entries.filter(e => e.check || e.error).length} of ${entries.length}` : `${plural(chosen.length, 'image')} ticked to import`}
          {exactCount > 0 && <span className="tag warn">{exactCount} exact {exactCount === 1 ? 'copy' : 'copies'}</span>}
          {nearCount > 0 && <span className="tag warn">{nearCount} near {nearCount === 1 ? 'copy' : 'copies'}</span>}
          {failedCount > 0 && <span className="tag bad">{failedCount} cannot be imported</span>}
          {ignored > 0 && <span className="tag">{ignored} other {ignored === 1 ? 'file' : 'files'} ignored</span>}</p>
        {characters.length > 0 && <div className="import-character-all"><label htmlFor="all-character">Character for every image (optional)</label>
          <select id="all-character" value={allCharacter} onChange={e => { setAllCharacter(e.target.value); setEntries(list => list.map(x => ({ ...x, character: e.target.value }))) }}><option value="">Decide later</option>{characters.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
          <span className="hint">Given to the largest person once the image is analysed. You can change any row, or assign in the table later.</span></div>}
        {(exactCount > 0 || nearCount > 0) && <p className="hint">Copies are unticked and marked with <b className="hint-warn">⚠</b>; point at the mark to see what it matches. Tick <b>Import anyway</b> to add one regardless. Heavily cropped or mirrored copies may not be found.</p>}
        <ol className="new-scene-list">{entries.map((entry, index) => <li key={`${entry.file.webkitRelativePath || entry.file.name}-${index}`} className={entry.error ? 'too-large' : flagged(entry) ? 'flagged' : ''}>
          {/* One line per image: thumbnail, title, copy status (message on hover), tick. */}
          <img className="row-thumb" src={entry.preview} alt="" loading="lazy" onError={e => { e.currentTarget.src = NO_PREVIEW }} />
          <div className="row-title"><label htmlFor={`new-title-${index}`} className="visually-hidden">Title for {entry.file.name}</label>
            <input id={`new-title-${index}`} maxLength={120} value={entry.title} placeholder={titleFrom(entry.file)} onChange={e => update(index, { title: e.target.value })} /></div>
          {characters.length > 0 && <select className="row-character" aria-label={`Character for ${entry.file.name}`} value={entry.character ?? ''} onChange={e => update(index, { character: e.target.value })}><option value="">Character: later</option>{characters.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>}
          <CopyStatus entry={entry} entries={entries} />
          <span className="row-actions">
            {!entry.error && <label className="checkbox-label"><input type="checkbox" checked={entry.include} disabled={!entry.check} onChange={e => update(index, { include: e.target.checked })} /><span>{flagged(entry) ? 'Import anyway' : 'Import'}</span></label>}
            <button type="button" className="secondary compact icon-only" aria-label={`Remove ${entry.file.name}`} onClick={() => remove(index)}>×</button></span>
        </li>)}</ol>
        {pickers}
      </div>}
      {entries.length > 0 && <SetPicker id="import-set" sets={sets} value={setValue} newName={setName} onChange={setSetValue} onName={setSetName} />}
    </fieldset>
    {error && <p className="frame-error" role="alert">{error}</p>}
    <div className="dialog-actions">{busy && many && <span className="spacer hint" role="status">Adding {Math.min(done + 1, chosen.length)} of {chosen.length}…</span>}
      <button type="button" className="secondary" disabled={busy} onClick={onCancel}>Cancel</button>
      <button disabled={!chosen.length || busy || checking}>{busy ? 'Adding…' : checking ? 'Checking…' : many ? `Add ${plural(chosen.length, 'scene')}` : 'Create scene'}</button></div>
  </form>
}

/** Move the selected scenes into a set, or take them out of their set. */
export function MoveDialog({ scenes, sets, token, onClose, onMoved }: { scenes: SceneSummary[]; sets: SceneSet[]; token: string; onClose: () => void; onMoved: (setId: string | null, count: number) => void }) {
  const [value, setValue] = useState(sets[0]?.id ?? 'new')
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit(e: FormEvent) {
    e.preventDefault()
    if (value === 'new' && !name.trim()) { setError('Name the new scene set.'); return }
    setBusy(true); setError('')
    try {
      const setId = await chosenSet(value, name, token)
      const moved = await send<{ moved: number }>('/api/scene-set-members', 'PUT', token, { scene_ids: scenes.map(s => s.id), scene_set_id: setId })
      onMoved(setId, moved.moved)
    } catch (err) { setError(err instanceof Error ? err.message : 'The scenes could not be moved.'); setBusy(false) }
  }
  return <Dialog label="move-title" onClose={onClose}>
    <form className="text-dialog-form" onSubmit={e => void submit(e)}>
      <h2 id="move-title">Move {scenes.length === 1 ? `“${scenes[0].title}”` : plural(scenes.length, 'scene')}</h2>
      <p className="hint">A scene belongs to at most one set. Moving only organises your scenes: analyses, prompts and approvals stay as they are.</p>
      <SetPicker id="move-set" sets={sets} value={value} newName={name} onChange={setValue} onName={setName} disabled={busy} />
      {value === '' && <p className="hint">The scenes are taken out of their set and stay in your studio.</p>}
      {error && <p className="frame-error" role="alert">{error}</p>}
      <div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Cancel</button><button disabled={busy}>{busy ? 'Moving…' : 'Move'}</button></div>
    </form>
  </Dialog>
}

type Duplicates = { checked: number; near_copy_bits: number; exact: SceneSummary[][]; near: SceneSummary[][] }

/** Exact and near copies among the scenes already in the studio; deleting stays explicit. */
export function DuplicatesDialog({ onClose, onOpen, onDelete }: { onClose: () => void; onOpen: (id: string) => void; onDelete: (scene: SceneSummary) => Promise<boolean> }) {
  const [found, setFound] = useState<Duplicates | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const load = () => request<Duplicates>('/api/scene-duplicates').then(setFound, e => setError(e.message))
  useEffect(() => { void load() }, [])
  async function remove(scene: SceneSummary) {
    setBusy(true)
    if (await onDelete(scene)) await load()
    setBusy(false)
  }
  const section = (title: string, note: string, list: SceneSummary[][]) => !!list.length && <section className="duplicate-section">
    <h3>{title} <span className="tag">{plural(list.length, 'group')}</span></h3><p className="hint">{note}</p>
    {list.map(group => <ul key={group.map(s => s.id).join()} className="duplicate-group">{group.map(s => <li key={s.id}>
      <img src={s.thumbnail_url} alt="" loading="lazy" />
      <span className="duplicate-copy"><strong>{s.title}</strong><span><StageChip state={s.workflow_state} /> <small>Added {new Date(s.created_at).toLocaleDateString()}{s.result_count ? ` · ${plural(s.result_count, 'result')}` : ''}</small></span></span>
      <span className="row-actions"><button type="button" className="secondary compact" onClick={() => onOpen(s.id)}>Open</button>
        <button type="button" className="danger secondary compact" disabled={busy || !!s.active_job} onClick={() => void remove(s)}>Delete</button></span>
    </li>)}</ul>)}
  </section>
  return <Dialog label="duplicates-title" className="duplicates-dialog" onClose={onClose}>
    <div className="text-dialog-form">
      <h2 id="duplicates-title">Find duplicates</h2>
      <p className="hint">Compares every scene’s Base Image on this computer, at no cost. Copies you made with Duplicate scene are not listed. Nothing is deleted unless you choose Delete.</p>
      {error ? <p className="frame-error" role="alert">{error}</p> : !found ? <p role="status">Checking your scenes… The first check also fingerprints older scenes, which can take a moment.</p>
        : !found.exact.length && !found.near.length ? <p className="ok-line" role="status">No duplicates among your {plural(found.checked, 'scene')}.</p>
          : <div className="duplicate-list">
            {section('Exact copies', 'The same file added more than once.', found.exact)}
            {section('Near copies', 'The same picture re-saved, resized or in another format. Check them before deleting: similar shots from one session can look alike.', found.near)}
          </div>}
      <div className="dialog-actions"><button type="button" onClick={onClose}>Done</button></div>
    </div>
  </Dialog>
}
