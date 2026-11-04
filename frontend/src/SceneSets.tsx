import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError, request, send, type Bootstrap } from './api'
import { Dialog, plural } from './Batches'
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

/** One button per stage with its count; the chosen one is kept in the address. */
export function StageFilters({ scenes, value, onChange }: { scenes: SceneSummary[]; value: StageFilter; onChange: (stage: StageFilter) => void }) {
  return <div className="stage-filters" role="group" aria-label="Filter by stage">
    {stageFilters.map(f => {
      const count = scenes.filter(s => inStage(s, f.id)).length
      return <button key={f.id} type="button" className={`stage-filter ${f.id === 'problems' && count ? 'has-problems' : ''} ${count ? '' : 'empty'}`} aria-pressed={value === f.id} onClick={() => onChange(f.id)}>
        {f.label}<span>{count}</span>
      </button>
    })}
  </div>
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
type Entry = { file: File; title: string; preview: string; check?: Check; error?: string; twin?: { index: number; exact: boolean }; include: boolean }

const MAX_NEW_SCENES = 500
const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const isImage = (file: File) => IMAGE_TYPES.includes(file.type) || /\.(jpe?g|png|webp)$/i.test(file.name)
const titleFrom = (file: File) => file.name.replace(/\.[^.]+$/, '').trim().slice(0, 120) || 'Untitled scene'
const bits = (a: string, b: string) => { let x = BigInt(`0x${a}`) ^ BigInt(`0x${b}`), n = 0; while (x) { n += Number(x & 1n); x >>= 1n } return n }
const flagged = (e: Entry) => !!(e.check?.exact.length || e.check?.near.length || e.twin)

/** Why a file is unticked: an exact or near copy in the studio or earlier in this selection. */
function CopyNote({ entry, entries }: { entry: Entry; entries: Entry[] }) {
  if (entry.error) return <small className="frame-error">{entry.error}</small>
  if (!entry.check) return <small className="hint">Checking for copies…</small>
  const { exact, near } = entry.check
  const twin = entry.twin ? entries[entry.twin.index] : null
  if (!exact.length && !near.length && !twin) return null
  const match = exact[0] ?? near[0]
  // A scene already in the studio is named first; the picture always shows what the text names.
  const text = exact.length ? `Exact copy of “${exact[0].title}”${exact.length > 1 ? ` and ${plural(exact.length - 1, 'other scene')}` : ''}`
    : near.length ? `Looks like “${near[0].title}” (re-saved, resized or another format)`
      : `${entry.twin!.exact ? 'Exact copy' : 'Looks like a copy'} of “${twin!.title || titleFrom(twin!.file)}” in this selection`
  return <span className="copy-note"><img src={match ? match.thumbnail_url : twin!.preview} alt={`Matching image: ${match ? match.title : twin!.file.name}`} /><small>{text}</small></span>
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
  const run = useRef(0)
  const previews = useRef<string[]>([])
  const limitMb = Math.floor(data.max_upload_bytes / 1048576)
  // Stop checking and free the previews when the dialog closes.
  useEffect(() => () => { run.current += 1; previews.current.forEach(url => URL.revokeObjectURL(url)) }, [])

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

  function choose(list: FileList | null) {
    const all = [...(list ?? [])]
    if (!all.length) return
    const images = all.filter(isImage)
    setIgnored(all.length - images.length)
    setError(images.length > MAX_NEW_SCENES ? `You chose ${images.length} images. Up to ${MAX_NEW_SCENES} are added at a time, so the first ${MAX_NEW_SCENES} are listed.` : images.length ? '' : 'No JPEG, PNG or WebP images were found there.')
    const kept = images.slice(0, MAX_NEW_SCENES).map(file => ({ file, title: images.length === 1 ? '' : titleFrom(file), preview: URL.createObjectURL(file), include: false }))
    previews.current.forEach(url => URL.revokeObjectURL(url))
    previews.current = kept.map(e => e.preview)
    setEntries(kept)
    run.current += 1
    if (kept.length) void checkAll(kept, run.current)
  }
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
      const query = new URLSearchParams({ title: entry.title.trim() || titleFrom(entry.file), ...(anyway ? { allow_duplicate: 'true' } : {}), ...(setId ? { scene_set_id: setId } : {}) })
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
  return <form className="new-scene" onSubmit={e => void submit(e)}>
    <h2 id="new-scene-title">{many ? `${entries.length} new scenes` : 'Add scenes'}</h2>
    <p className="hint">Choose a Base Image, several images, or a folder (subfolders included; other files are ignored). The studio checks each image against your scenes for exact and near copies on this computer, at no cost. Nothing is analysed until you choose to.</p>
    <fieldset disabled={busy}>
      {!entries.length ? <div className="import-start">
        <span className="drop-zone"><span><strong>Add Base Images</strong><small>JPEG, PNG or WebP · up to {limitMb} MB each · up to {MAX_NEW_SCENES} at a time</small></span></span>
        {pickers}
      </div> : single ? <div className="new-scene-body">
        <span className="drop-zone has-image"><img src={single.preview} alt="Selected Base Image" /></span>
        <div><label htmlFor="scene-title">Scene title</label><input id="scene-title" maxLength={120} value={single.title} placeholder={titleFrom(single.file)} onChange={e => update(0, { title: e.target.value })} />
          <p className="hint">Optional. The file name is used if you leave it empty.</p>
          <div className={`import-check ${flagged(single) || single.error ? 'flagged' : ''}`}><CopyNote entry={single} entries={entries} />
            {flagged(single) && <label className="checkbox-label"><input type="checkbox" checked={single.include} onChange={e => update(0, { include: e.target.checked })} /><span>Import anyway</span></label>}
            {single.check && !flagged(single) && <small className="ok-line">No copies found in your studio.</small>}</div>
          {pickers}</div>
      </div> : <div className="new-scenes">
        <p className="import-summary" role="status">{checking ? `Checking for copies… ${entries.filter(e => e.check || e.error).length} of ${entries.length}` : `${plural(chosen.length, 'image')} ticked to import`}
          {exactCount > 0 && <span className="tag warn">{exactCount} exact {exactCount === 1 ? 'copy' : 'copies'}</span>}
          {nearCount > 0 && <span className="tag warn">{nearCount} near {nearCount === 1 ? 'copy' : 'copies'}</span>}
          {failedCount > 0 && <span className="tag bad">{failedCount} cannot be imported</span>}
          {ignored > 0 && <span className="tag">{ignored} other {ignored === 1 ? 'file' : 'files'} ignored</span>}</p>
        {(exactCount > 0 || nearCount > 0) && <p className="hint">Copies are unticked. Tick <b>Import anyway</b> to add one regardless. Heavily cropped or mirrored copies may not be found.</p>}
        <ol className="new-scene-list">{entries.map((entry, index) => <li key={`${entry.file.webkitRelativePath || entry.file.name}-${index}`} className={entry.error ? 'too-large' : flagged(entry) ? 'flagged' : ''}>
          <img src={entry.preview} alt="" loading="lazy" />
          <div><label htmlFor={`new-title-${index}`} className="visually-hidden">Title for {entry.file.name}</label>
            <input id={`new-title-${index}`} maxLength={120} value={entry.title} placeholder={titleFrom(entry.file)} onChange={e => update(index, { title: e.target.value })} />
            <CopyNote entry={entry} entries={entries} /></div>
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
