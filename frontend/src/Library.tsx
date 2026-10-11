import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type PointerEvent } from 'react'
import { getBootstrap, request, type Bootstrap } from './api'
import { CardMenu, CopiesDialog, SelectionBar, TextDialog, type CopyChoice, type CopySummary } from './Controls'
import { replaceRoute, routeParts } from './route'

type Frame = { x: number; y: number; zoom: number }
export type Photo = { id: string; label: string; width: number; height: number; frame?: Frame; thumbnail_url: string; original_url: string }
export type Character = { id: string; name: string; age_category: string; notes: string; archived: boolean; revision: number; primary_photo_id: string | null; photos: Photo[]; group_ids: string[]; assigned_scene_count?: number; created_at: string; updated_at: string; cleanup_pending?: boolean }
export type Group = { id: string; name: string; revision: number; member_ids: string[] }
const labels = ['Front', 'Left three-quarter', 'Right three-quarter', 'Left profile', 'Right profile', 'Full body', 'Additional']
const defaultFrame: Frame = { x: 0.5, y: 0.3, zoom: 1 }
const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value))
// Deleting a character or photo used in scenes changes those scenes; say so before confirming.
const sceneNote = (scenes: number) => scenes ? ` ${scenes === 1 ? 'One scene uses' : `${scenes} scenes use`} this character: those subjects become undecided and any approval there is cancelled.` : ''

// Sizes are percentages of a square box, so one frame renders identically at every avatar size.
function frameBox(photo: Photo, frame: Frame) {
  const ratio = photo.width / photo.height
  return { w: Math.max(ratio, 1) * frame.zoom * 100, h: Math.max(1 / ratio, 1) * frame.zoom * 100 }
}
export function FramedImage({ photo, frame = photo.frame ?? defaultFrame }: { photo: Photo; frame?: Frame }) {
  const { w, h } = frameBox(photo, frame)
  return <img className="framed" src={photo.thumbnail_url} alt="" draggable={false} loading="lazy" style={{ width: `${w}%`, height: `${h}%`, left: `${(100 - w) * frame.x}%`, top: `${(100 - h) * frame.y}%` }} />
}
export function Avatar({ character, size = 'card' }: { character: Character; size?: 'card' | 'header' | 'mini' }) {
  const photo = character.photos.find(p => p.id === character.primary_photo_id)
  return <span className={`avatar avatar-${size}`} aria-hidden="true">{photo ? <FramedImage photo={photo} /> : character.name.slice(0, 1).toLocaleUpperCase()}</span>
}

function FrameEditor({ photo, busy, error, onSave, onCancel }: { photo: Photo; busy: boolean; error: string; onSave: (frame: Frame) => void; onCancel: () => void }) {
  const [frame, setFrame] = useState<Frame>(photo.frame ?? defaultFrame)
  const stage = useRef<HTMLDivElement>(null)
  const drag = useRef<{ x: number; y: number; frame: Frame } | null>(null)
  function shift(dx: number, dy: number, from: Frame) {
    const size = stage.current?.clientWidth || 1
    const { w, h } = frameBox(photo, from)
    const overflowX = (w / 100 - 1) * size, overflowY = (h / 100 - 1) * size
    setFrame({ ...from, x: overflowX > 0 ? clamp(from.x - dx / overflowX, 0, 1) : from.x, y: overflowY > 0 ? clamp(from.y - dy / overflowY, 0, 1) : from.y })
  }
  function zoomBy(step: number) { setFrame(f => ({ ...f, zoom: clamp(Math.round((f.zoom + step) * 100) / 100, 1, 4) })) }
  function onPointerDown(e: PointerEvent<HTMLDivElement>) { e.currentTarget.setPointerCapture(e.pointerId); drag.current = { x: e.clientX, y: e.clientY, frame } }
  function onPointerMove(e: PointerEvent<HTMLDivElement>) { if (drag.current) shift(e.clientX - drag.current.x, e.clientY - drag.current.y, drag.current.frame) }
  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const step = (stage.current?.clientWidth || 100) * 0.04
    const moves: Record<string, [number, number]> = { ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] }
    if (moves[e.key]) shift(...moves[e.key], frame)
    else if (e.key === '+' || e.key === '=') zoomBy(0.1)
    else if (e.key === '-') zoomBy(-0.1)
    else return
    e.preventDefault()
  }
  return <div className="frame-editor">
    <h2 id="frame-title">Adjust thumbnail</h2>
    <p className="hint">Drag the photo to choose what shows inside the circle, and use the slider to zoom. Only the thumbnail changes; your original photo stays as it is.</p>
    <div className="frame-body">
      <div ref={stage} className="frame-stage" tabIndex={0} aria-label="Thumbnail position. Use arrow keys to move the photo and plus or minus to zoom." onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={() => { drag.current = null }} onPointerCancel={() => { drag.current = null }} onKeyDown={onKeyDown}>
        <FramedImage photo={photo} frame={frame} />
      </div>
      <div className="frame-side">
        <span className="tiny-label">PREVIEW</span>
        <div className="frame-previews" aria-hidden="true">{(['card', 'header', 'mini'] as const).map(s => <span key={s} className={`avatar avatar-${s}`}><FramedImage photo={photo} frame={frame} /></span>)}</div>
        <label htmlFor="frame-zoom">Zoom</label>
        <div className="zoom-row"><button type="button" className="secondary icon-button" aria-label="Zoom out" onClick={() => zoomBy(-0.1)}>−</button><input id="frame-zoom" type="range" min={1} max={4} step={0.01} value={frame.zoom} onChange={e => setFrame(f => ({ ...f, zoom: Number(e.target.value) }))} /><button type="button" className="secondary icon-button" aria-label="Zoom in" onClick={() => zoomBy(0.1)}>+</button></div>
        <button type="button" className="link-button" onClick={() => setFrame(defaultFrame)}>Reset to default</button>
      </div>
    </div>
    {error && <p className="frame-error" role="alert">{error}</p>}
    <div className="dialog-actions"><button type="button" className="secondary" onClick={onCancel}>Cancel</button><button type="button" disabled={busy} onClick={() => onSave(frame)}>Save thumbnail</button></div>
  </div>
}

export default function Library({ data, onDirty, onBusy, onSession }: { data: Bootstrap; onSession: (data: Bootstrap) => void; onDirty: (dirty: boolean) => void; onBusy: (busy: boolean) => void }) {
  const [characters, setCharacters] = useState<Character[]>([])
  const [groups, setGroups] = useState<Group[]>([])
  const [selected, setSelected] = useState<Character | null>(null)
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [age, setAge] = useState('Adult')
  const [notes, setNotes] = useState('')
  const [query, setQuery] = useState('')
  const [archived, setArchived] = useState(false)
  const [groupFilter, setGroupFilter] = useState('')
  const [tab, setTab] = useState<'characters' | 'groups'>(() => routeParts()[0] === 'groups' ? 'groups' : 'characters')
  const [editingGroup, setEditingGroup] = useState<Group | null>(null)
  const [creatingGroup, setCreatingGroup] = useState(false)
  const [groupName, setGroupName] = useState('')
  const [members, setMembers] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [preview, setPreview] = useState<Photo | null>(null)
  const [framing, setFraming] = useState<Photo | null>(null)
  const [selecting, setSelecting] = useState(false)
  const [picked, setPicked] = useState<string[]>([])
  const [renaming, setRenaming] = useState<{ kind: 'character' | 'group'; id: string; name: string } | null>(null)
  const [asking, setAsking] = useState<{ title: string; message: string; copies: CopySummary; resolve: (choice: CopyChoice) => void } | null>(null)
  const errorRef = useRef<HTMLDivElement>(null)
  const nameRef = useRef<HTMLInputElement>(null)
  const groupNameRef = useRef<HTMLInputElement>(null)
  const dialogRef = useRef<HTMLDialogElement>(null)
  const frameDialogRef = useRef<HTMLDialogElement>(null)
  const uploadRef = useRef<HTMLInputElement>(null)
  const lock = useRef(false)
  const removedPhotoCopies = useRef(0)
  const characterDirty = (creating || !!selected) && (name !== (selected?.name || '') || age !== (selected?.age_category || 'Adult') || notes !== (selected?.notes || ''))
  const groupDirty = groupName !== (editingGroup?.name || '') || [...members].sort().join() !== [...(editingGroup?.member_ids || [])].sort().join()
  const dirty = !!characterDirty || groupDirty

  useEffect(() => { onDirty(dirty); return () => onDirty(false) }, [dirty, onDirty])
  useEffect(() => { onBusy(busy); return () => onBusy(false) }, [busy, onBusy])
  useEffect(() => { if (error) errorRef.current?.focus() }, [error])
  useEffect(() => {
    if (preview) dialogRef.current?.showModal()
    else dialogRef.current?.close()
  }, [preview])
  useEffect(() => {
    if (framing) { if (!frameDialogRef.current?.open) frameDialogRef.current?.showModal() }
    else frameDialogRef.current?.close()
  }, [framing])
  useEffect(() => {
    let active = true
    Promise.all([request<Character[]>('/api/characters'), request<Group[]>('/api/groups')])
      .then(([c, g]) => {
        if (!active) return
        setCharacters(c); setGroups(g)
        // Reopen the profile or group named in the address after a browser refresh.
        const [section, id] = routeParts()
        const character = section === 'characters' && c.find(x => x.id === id)
        const group = section === 'groups' && g.find(x => x.id === id)
        if (character) { setArchived(character.archived); selectCharacter(character) }
        if (group) openGroup(group)
      })
      .catch(e => { if (active) setError(e.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])
  useEffect(() => {
    if (loading) return
    replaceRoute(tab === 'groups' ? (editingGroup ? `groups/${editingGroup.id}` : 'groups') : (selected ? `characters/${selected.id}` : 'characters'))
  }, [loading, tab, selected?.id, editingGroup?.id])

  const mutate = <T,>(path: string, method: string, body?: unknown) => request<T>(path, {
    method, headers: { 'X-Studio-Token': data.session_token, 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  function selectCharacter(c: Character | null) {
    setSelected(c); setCreating(!c); setName(c?.name || ''); setAge(c?.age_category || 'Adult'); setNotes(c?.notes || '')
  }
  function acceptCharacter(c: Character) {
    setCharacters(old => old.some(x => x.id === c.id) ? old.map(x => x.id === c.id ? c : x) : [...old, c])
    selectCharacter(c)
  }
  // Copies of these photos inside saved packages are never removed silently: ask when there are any.
  async function confirmDelete(title: string, message: string, query: string): Promise<CopyChoice> {
    const copies = await request<CopySummary>(`/api/package-copies?${query}`).catch(() => null)
    if (!copies?.count) return window.confirm(message) ? 'keep' : null
    return new Promise(resolve => setAsking({ title, message, copies, resolve }))
  }
  const copiesNote = (removed: number) => removed ? ` ${removed} package ${removed === 1 ? 'copy' : 'copies'} removed.` : ''
  function canLeave() { return !busy && (!dirty || window.confirm('Discard unsaved edits?')) }
  // Card-level actions update the list without opening the profile or group.
  function replaceCharacter(c: Character) {
    setCharacters(old => old.map(x => x.id === c.id ? c : x))
    if (selected?.id === c.id) selectCharacter(c)
  }
  function replaceGroup(g: Group) {
    setGroups(old => old.map(x => x.id === g.id ? g : x))
    if (editingGroup?.id === g.id) openGroup(g)
  }
  const touchesOpenEdits = (id: string) => (selected?.id === id && !!characterDirty) || (editingGroup?.id === id && groupDirty)
  function guardCard(id: string) { return !touchesOpenEdits(id) || window.confirm('Discard unsaved edits?') }
  function stopSelecting() { setSelecting(false); setPicked([]) }
  function togglePick(id: string) { setPicked(old => old.includes(id) ? old.filter(x => x !== id) : [...old, id]) }
  function archiveFromCard(c: Character) {
    if (!guardCard(c.id)) return
    void run(async () => replaceCharacter(await mutate<Character>(`/api/characters/${c.id}/archive`, 'PUT', { revision: c.revision, archived: !c.archived })), c.archived ? `${c.name} restored.` : `${c.name} archived.`)
  }
  async function deleteCharacterFromCard(c: Character) {
    const choice = await confirmDelete(`Delete ${c.name}?`, `Permanently delete “${c.name}” and all ${c.photos.length} reference photos? This cannot be undone. Archive instead if you want to keep them.${sceneNote(c.assigned_scene_count ?? 0)}`, `character=${c.id}`)
    if (!choice) return
    let removed = 0
    void run(async () => {
      const result = await mutate<{ cleanup_pending: boolean; copies_removed: number }>(`/api/characters/${c.id}?revision=${c.revision}&remove_copies=${choice === 'remove'}`, 'DELETE')
      removed = result.copies_removed
      setCharacters(old => old.filter(x => x.id !== c.id))
      if (selected?.id === c.id) clearEditors()
      setGroups(await request<Group[]>('/api/groups'))
      if (result.cleanup_pending) throw new Error('Character removed. Locked files are pending deletion; restart the studio to retry cleanup.')
    }, () => `${c.name} deleted.${copiesNote(removed)}`)
  }
  function deleteGroupFromCard(g: Group) {
    if (!window.confirm(`Delete group “${g.name}”? Characters and photos will remain.`)) return
    void run(async () => {
      await mutate(`/api/groups/${g.id}?revision=${g.revision}`, 'DELETE')
      setGroups(old => old.filter(x => x.id !== g.id))
      setCharacters(old => old.map(c => ({ ...c, group_ids: c.group_ids.filter(id => id !== g.id) })))
      if (editingGroup?.id === g.id) resetGroup()
    }, 'Group deleted. Characters kept.')
  }
  async function bulkCharacters(kind: 'archive' | 'restore' | 'delete') {
    const chosen = characters.filter(c => picked.includes(c.id))
    if (!chosen.length) return
    const count = `${chosen.length} ${chosen.length === 1 ? 'character' : 'characters'}`
    const used = chosen.filter(c => c.assigned_scene_count).length
    const message = `Permanently delete ${count} and all their reference photos? This cannot be undone. Archive instead if you want to keep them.${used ? ` ${used} of them ${used === 1 ? 'is' : 'are'} assigned in scenes: those subjects become undecided and any approval there is cancelled.` : ''}`
    const choice = kind === 'delete' ? await confirmDelete(`Delete ${count}?`, message, chosen.map(c => `character=${c.id}`).join('&')) : 'keep'
    if (!choice) return
    if (chosen.some(c => touchesOpenEdits(c.id)) && !window.confirm('Discard unsaved edits?')) return
    let removed = 0
    void run(async () => {
      const failed: string[] = []
      let pending = false
      for (const c of chosen) {
        try {
          if (kind === 'delete') {
            const result = await mutate<{ cleanup_pending: boolean; copies_removed: number }>(`/api/characters/${c.id}?revision=${c.revision}&remove_copies=${choice === 'remove'}`, 'DELETE')
            removed += result.copies_removed
            pending ||= result.cleanup_pending
            setCharacters(old => old.filter(x => x.id !== c.id))
            if (selected?.id === c.id) clearEditors()
          } else replaceCharacter(await mutate<Character>(`/api/characters/${c.id}/archive`, 'PUT', { revision: c.revision, archived: kind === 'archive' }))
        } catch { failed.push(c.name) }
      }
      if (kind === 'delete') setGroups(await request<Group[]>('/api/groups'))
      stopSelecting()
      if (failed.length) throw new Error(`Could not ${kind} ${failed.join(', ')}. The others were done. Reload the library and try again.`)
      if (pending) throw new Error('Characters removed. Some locked files are pending deletion; restart the studio to retry cleanup.')
    }, () => `${count} ${kind === 'delete' ? 'deleted' : kind === 'archive' ? 'archived' : 'restored'}.${copiesNote(removed)}`)
  }
  function bulkDeleteGroups() {
    const chosen = groups.filter(g => picked.includes(g.id))
    if (!chosen.length) return
    const count = `${chosen.length} ${chosen.length === 1 ? 'group' : 'groups'}`
    if (!window.confirm(`Delete ${count}? Characters and photos will remain.`)) return
    if (chosen.some(g => touchesOpenEdits(g.id)) && !window.confirm('Discard unsaved edits?')) return
    void run(async () => {
      const failed: string[] = []
      for (const g of chosen) {
        try {
          await mutate(`/api/groups/${g.id}?revision=${g.revision}`, 'DELETE')
          setGroups(old => old.filter(x => x.id !== g.id))
          setCharacters(old => old.map(c => ({ ...c, group_ids: c.group_ids.filter(id => id !== g.id) })))
          if (editingGroup?.id === g.id) resetGroup()
        } catch { failed.push(g.name) }
      }
      stopSelecting()
      if (failed.length) throw new Error(`Could not delete ${failed.join(', ')}. The others were deleted. Reload the library and try again.`)
    }, `${count} deleted. Characters kept.`)
  }
  async function saveRename(value: string) {
    if (!renaming) return
    if (renaming.kind === 'character') {
      const c = characters.find(x => x.id === renaming.id)
      if (!c) throw new Error('This character no longer exists. Reload the library.')
      replaceCharacter(await mutate<Character>(`/api/characters/${c.id}`, 'PUT', { name: value, age_category: c.age_category, notes: c.notes, revision: c.revision }))
    } else {
      const g = groups.find(x => x.id === renaming.id)
      if (!g) throw new Error('This group no longer exists. Reload the library.')
      replaceGroup(await mutate<Group>(`/api/groups/${g.id}`, 'PUT', { name: value, member_ids: g.member_ids, revision: g.revision }))
    }
    setError(''); setMessage('Renamed.')
  }
  function resetGroup() { setEditingGroup(null); setCreatingGroup(false); setGroupName(''); setMembers([]) }
  function openGroup(g: Group) { setEditingGroup(g); setCreatingGroup(false); setGroupName(g.name); setMembers(g.member_ids) }
  function newGroup() { if (canLeave()) { resetGroup(); setCreatingGroup(true); requestAnimationFrame(() => groupNameRef.current?.focus()) } }
  function clearEditors() { setSelected(null); setCreating(false); setName(''); setAge('Adult'); setNotes(''); resetGroup() }
  async function run(action: () => Promise<void>, success: string | (() => string) = 'Saved locally.') {
    if (lock.current) return
    lock.current = true; setBusy(true); setError(''); setMessage('')
    try { await action(); setMessage(typeof success === 'function' ? success() : success) }
    catch (e) { setMessage(''); setError(e instanceof Error ? e.message : 'Unable to save. Your edits are still here.') }
    finally { lock.current = false; setBusy(false) }
  }
  async function reload() {
    if (!canLeave()) return
    await run(async () => {
      const [session, c, g] = await Promise.all([getBootstrap(), request<Character[]>('/api/characters'), request<Group[]>('/api/groups')])
      onSession(session); setCharacters(c); setGroups(g); clearEditors(); setLoading(false)
    }, 'Library refreshed.')
  }
  function saveCharacter(e: FormEvent) {
    e.preventDefault()
    void run(async () => {
      const body = { name: name.trim(), age_category: age, notes, ...(selected ? { revision: selected.revision } : {}) }
      acceptCharacter(await mutate<Character>(selected ? `/api/characters/${selected.id}` : '/api/characters', selected ? 'PUT' : 'POST', body))
    }, selected ? 'Saved locally.' : 'Character created. Add reference photos to complete the profile.')
  }
  function saveGroup(e: FormEvent) {
    e.preventDefault()
    const isNew = !editingGroup
    void run(async () => {
      const g = await mutate<Group>(editingGroup ? `/api/groups/${editingGroup.id}` : '/api/groups', editingGroup ? 'PUT' : 'POST', {
        name: groupName.trim(), member_ids: members, ...(editingGroup ? { revision: editingGroup.revision } : {}),
      })
      setGroups(old => old.some(x => x.id === g.id) ? old.map(x => x.id === g.id ? g : x) : [...old, g])
      setCharacters(old => old.map(c => ({ ...c, group_ids: [...c.group_ids.filter(id => id !== g.id), ...(g.member_ids.includes(c.id) ? [g.id] : [])] })))
      if (isNew) resetGroup()
      else openGroup(g)
    }, isNew ? 'Group created.' : 'Saved locally.')
  }
  function changePhoto(photo: Photo, label: string, primary = false) {
    if (!selected) return
    void run(async () => acceptCharacter(await mutate<Character>(`/api/photos/${photo.id}`, 'PUT', { revision: selected.revision, label, primary })))
  }
  function openFraming(photo: Photo) { setError(''); setMessage(''); setFraming(photo) }
  function saveFrame(photo: Photo, frame: Frame) {
    if (!selected) return
    void run(async () => {
      acceptCharacter(await mutate<Character>(`/api/photos/${photo.id}`, 'PUT', { revision: selected.revision, label: photo.label, frame }))
      setFraming(null)
    }, 'Thumbnail updated.')
  }
  async function upload(files: File[]) {
    if (!selected || !files.length) return
    let current = selected
    await run(async () => {
      for (let i = 0; i < files.length; i++) {
        const file = files[i]
        if (file.size > data.max_upload_bytes) throw new Error(`Photo ${i + 1} is too large. Limit: ${Math.floor(data.max_upload_bytes / 1048576)} MB. Earlier successful uploads are saved.`)
        setMessage(`Uploading photo ${i + 1} of ${files.length}…`)
        try {
          current = await request<Character>(`/api/characters/${current.id}/photos?revision=${current.revision}`, {
            method: 'POST', headers: { 'X-Studio-Token': data.session_token, 'Content-Type': 'application/octet-stream' }, body: file,
          })
          acceptCharacter(current)
        } catch (e) {
          throw new Error(`Stopped at photo ${i + 1} of ${files.length}. ${e instanceof Error ? e.message : 'Upload failed.'} Earlier successful uploads are saved. Reload before retrying.`)
        }
      }
    }, 'Photos saved locally.')
    if (uploadRef.current) uploadRef.current.value = ''
  }

  const byId = new Map(characters.map(c => [c.id, c]))
  const memberOf = selected ? groups.filter(g => g.member_ids.includes(selected.id)) : []
  const primary = selected?.photos.find(p => p.id === selected.primary_photo_id)
  const photoLocked = busy || !!characterDirty
  const filtered = characters.filter(c => c.archived === archived && c.name.toLocaleLowerCase().includes(query.toLocaleLowerCase()) && (!groupFilter || c.group_ids.includes(groupFilter)))
  return <div className="library">
    <div className="library-toolbar">
      <div className="library-tabs" aria-label="Library sections">{(['characters', 'groups'] as const).map(t => <button key={t} className={tab === t ? '' : 'secondary'} aria-pressed={tab === t} disabled={busy} onClick={() => { if (canLeave()) { clearEditors(); stopSelecting(); setTab(t) } }}>{t === 'characters' ? 'Characters' : 'Groups'}</button>)}</div>
      <button className="secondary" disabled={busy} onClick={() => void reload()}>Reload library</button>
    </div>
    {error && <div className="error" role="alert" tabIndex={-1} ref={errorRef}><strong>Could not finish that action.</strong><p>{error}</p><p>Your unsaved edits remain. Reloading discards them.</p></div>}
    <p className="library-status" role="status">{busy ? message || 'Saving…' : message}</p>
    {loading ? <p role="status">Loading your library…</p> : tab === 'characters' ? <>
      <div className="library-toolbar filters">
        <div><label htmlFor="character-search">Search characters</label><input id="character-search" type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search by name" /></div>
        <div><label htmlFor="group-filter">Group</label><select id="group-filter" value={groupFilter} onChange={e => setGroupFilter(e.target.value)}><option value="">All groups</option>{groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}</select></div>
        <label className="checkbox-label"><input type="checkbox" checked={archived} onChange={e => { setArchived(e.target.checked); setPicked([]) }} /> Show archived</label>
        {!selecting && !!filtered.length && <button className="secondary" disabled={busy} onClick={() => setSelecting(true)}>Select</button>}
        <button disabled={busy || selecting} onClick={() => { if (canLeave()) { resetGroup(); selectCharacter(null); requestAnimationFrame(() => nameRef.current?.focus()) } }}>+ New character</button>
      </div>
      {selecting && <SelectionBar count={picked.length} total={filtered.length} onAll={() => setPicked(filtered.map(c => c.id))} onNone={() => setPicked([])} onDone={stopSelecting}>
        <button type="button" className="secondary" disabled={busy || !picked.length} onClick={() => bulkCharacters(archived ? 'restore' : 'archive')}>{archived ? 'Restore' : 'Archive'}</button>
        <button type="button" className="danger secondary" disabled={busy || !picked.length} onClick={() => bulkCharacters('delete')}>Delete</button>
      </SelectionBar>}
      <div className={`library-columns ${creating || selected ? 'with-detail' : ''}`}>
        <section aria-label="Saved characters">
          {!filtered.length ? <div className="empty-library panel"><span className="tiny-label">FAMILIAR FACES, SAVED ONCE</span><h2>{query || groupFilter ? 'No matching characters' : archived ? 'No archived characters' : 'Your cast starts here'}</h2><p>{query || groupFilter ? 'Try another name or group.' : 'Create a profile, then add a few reference photos. Everything stays on this computer.'}</p></div> : <div className="character-grid">{filtered.map(c => {
            const isPicked = picked.includes(c.id)
            return <div key={c.id} className={`character-card ${selected?.id === c.id && !selecting ? 'selected' : ''} ${isPicked ? 'picked' : ''}`}>
              <button className="card-main" aria-pressed={selecting ? isPicked : selected?.id === c.id} disabled={busy} onClick={() => { if (selecting) togglePick(c.id); else if (canLeave()) { resetGroup(); selectCharacter(c); requestAnimationFrame(() => nameRef.current?.focus()) } }}>
                {selecting && <span className="pick-box" aria-hidden="true" />}
                <Avatar character={c} />
                <span className="character-card-copy"><strong>{c.name}</strong><span>{c.age_category} · {c.photos.length} {c.photos.length === 1 ? 'photo' : 'photos'}</span></span>
              </button>
              {!selecting && <CardMenu label={c.name} disabled={busy} items={[
                { label: 'Rename', onSelect: () => { if (guardCard(c.id)) setRenaming({ kind: 'character', id: c.id, name: c.name }) } },
                { label: c.archived ? 'Restore' : 'Archive', onSelect: () => archiveFromCard(c) },
                { label: 'Delete permanently', danger: true, onSelect: () => deleteCharacterFromCard(c) },
              ]} />}
            </div>
          })}</div>}
        </section>
        {(creating || selected) && <section className="panel character-detail" aria-label="Character profile">
          <div className="section-title"><div className="profile-heading">
            {selected && (primary
              ? <button className="avatar-button" disabled={photoLocked} title="Adjust thumbnail" aria-label={`Adjust thumbnail for ${selected.name}`} onClick={() => openFraming(primary)}><Avatar character={selected} size="header" /><span className="avatar-edit" aria-hidden="true">✎</span></button>
              : <Avatar character={selected} size="header" />)}
            <div><span className="tiny-label">{creating ? 'NEW CHARACTER' : 'CHARACTER PROFILE'}</span><h2>{selected ? selected.name : 'New character'}</h2>{selected && <span className="profile-sub">{selected.age_category} · {selected.photos.length} {selected.photos.length === 1 ? 'photo' : 'photos'}{selected.archived ? ' · Archived' : ''}</span>}</div>
          </div><button className="secondary" disabled={busy} onClick={() => { if (canLeave()) clearEditors() }}>Close</button></div>
          <form onSubmit={saveCharacter}><fieldset disabled={busy}>
            <div className="form-grid">
              <div><label htmlFor="character-name">Name or alias</label><input ref={nameRef} id="character-name" required maxLength={80} value={name} onChange={e => setName(e.target.value)} /></div>
              <div><label htmlFor="age-category">Age category</label><select id="age-category" value={age} onChange={e => setAge(e.target.value)}>{['Adult', 'Teen', 'Child'].map(a => <option key={a}>{a}</option>)}</select></div>
              <div className="full"><label htmlFor="character-notes">Notes (optional)</label><textarea id="character-notes" maxLength={4000} rows={3} value={notes} onChange={e => setNotes(e.target.value)} /></div>
            </div>
            <p className="hint">Use a nickname if you prefer. Avoid unnecessary personal details.</p>
            <div className="save-row"><button disabled={!name.trim() || (!creating && !characterDirty)}>{creating ? 'Create character' : 'Save profile'}</button>{characterDirty && <span>Unsaved edits</span>}</div>
          </fieldset></form>
          {selected && <>
            <div className="detail-section">
              <div className="detail-head"><div><h3>Reference photos</h3><p className="hint">JPEG, PNG or WebP · up to {Math.floor(data.max_upload_bytes / 1048576)} MB each. Originals stay unchanged.</p></div>
                <label className={`upload-button ${photoLocked || selected.archived ? 'disabled' : ''}`}><input ref={uploadRef} id="photo-upload" className="visually-hidden" type="file" accept="image/jpeg,image/png,image/webp" multiple disabled={photoLocked || selected.archived} onChange={e => void upload(Array.from(e.target.files || []))} />+ Add photos</label></div>
              {characterDirty && <p className="hint">Save your profile before managing photos or archiving.</p>}
              {selected.archived && <p className="hint">Restore this character to add more photos.</p>}
              <div className="photo-grid">{selected.photos.map((p, i) => {
                const isPrimary = p.id === selected.primary_photo_id
                return <article className="photo-card" key={p.id}>
                  <button className="photo-preview" onClick={() => setPreview(p)} aria-label={`Preview ${p.label} photo`}><img src={p.thumbnail_url} alt={`${selected.name}: ${p.label}`} loading="lazy" />{isPrimary && <span className="photo-badge">Primary</span>}</button>
                  <div className="photo-row"><select aria-label={`Label for photo ${i + 1}`} title="Reference label" disabled={photoLocked} value={p.label} onChange={e => changePhoto(p, e.target.value)}>{labels.map(l => <option key={l}>{l}</option>)}</select><span className="photo-meta">{p.width} × {p.height}</span></div>
                  <div className="photo-actions">
                    {isPrimary
                      ? <button className="secondary" disabled={photoLocked} onClick={() => openFraming(p)}>Adjust thumbnail</button>
                      : <button className="secondary" disabled={photoLocked} onClick={() => changePhoto(p, p.label, true)}>Make primary</button>}
                    <button className="danger secondary" disabled={photoLocked} aria-label={`Delete photo ${i + 1}`} onClick={() => void confirmDelete('Delete this photo?', `Permanently delete this original photo and its thumbnail? This cannot be undone.${selected.assigned_scene_count ? ' Scenes that use it as a reference lose it, and any approval there is cancelled.' : ''}`, `photo=${p.id}`).then(choice => { if (choice) void run(async () => {
                      const c = await mutate<Character & { copies_removed: number }>(`/api/photos/${p.id}?revision=${selected.revision}&remove_copies=${choice === 'remove'}`, 'DELETE'); acceptCharacter(c)
                      removedPhotoCopies.current = c.copies_removed
                      if (c.cleanup_pending) throw new Error('Photo removed from the library. A locked file is pending deletion; restart the studio to retry cleanup.')
                    }, () => `Photo deleted.${copiesNote(removedPhotoCopies.current)}`) })}>Delete</button>
                  </div>
                </article>
              })}</div>
              {!selected.photos.length && <p className="hint">No photos yet. The first photo becomes the primary reference.</p>}
            </div>
            <div className="detail-section">
              <div className="detail-head"><h3>Groups</h3><button className="link-button" disabled={busy} onClick={() => { if (canLeave()) { clearEditors(); setTab('groups') } }}>Manage groups</button></div>
              {memberOf.length
                ? <ul className="chip-list" aria-label={`Groups ${selected.name} belongs to`}>{memberOf.map(g => <li key={g.id}><button className="chip" disabled={busy} title={`Open ${g.name} in Groups`} onClick={() => { if (canLeave()) { clearEditors(); setTab('groups'); openGroup(g) } }}>{g.name}<span>{g.member_ids.length}</span></button></li>)}</ul>
                : <p className="hint">Not in any groups yet.</p>}
            </div>
            <div className="detail-section"><h3>{selected.archived ? 'Archived character' : 'Remove from the library'}</h3><p className="hint">Archive hides the character and keeps its photos and memberships. Permanent deletion removes the profile, originals, thumbnails and memberships; scenes that used the character keep their subjects, undecided. Past approval records are kept.</p>
              <div className="save-row"><button className="secondary" disabled={photoLocked} onClick={() => void run(async () => acceptCharacter(await mutate<Character>(`/api/characters/${selected.id}/archive`, 'PUT', { revision: selected.revision, archived: !selected.archived })), selected.archived ? 'Character restored.' : 'Character archived.')}>{selected.archived ? 'Restore character' : 'Archive character'}</button>
                <button className="danger secondary" disabled={photoLocked} onClick={() => void confirmDelete(`Delete ${selected.name}?`, `Permanently delete “${selected.name}” and all ${selected.photos.length} reference photos? This cannot be undone. Archive instead if you want to keep them.${sceneNote(selected.assigned_scene_count ?? 0)}`, `character=${selected.id}`).then(choice => { if (choice) void run(async () => {
                  const result = await mutate<{ cleanup_pending: boolean; copies_removed: number }>(`/api/characters/${selected.id}?revision=${selected.revision}&remove_copies=${choice === 'remove'}`, 'DELETE')
                  removedPhotoCopies.current = result.copies_removed
                  setCharacters(old => old.filter(c => c.id !== selected.id)); clearEditors()
                  setGroups(await request<Group[]>('/api/groups'))
                  if (result.cleanup_pending) throw new Error('Character removed. Locked files are pending deletion; restart the studio to retry cleanup.')
                }, () => `Character deleted.${copiesNote(removedPhotoCopies.current)}`) })}>Delete permanently</button></div>
            </div>
            <p className="hint detail-foot">Created {new Date(selected.created_at).toLocaleDateString()} · Updated {new Date(selected.updated_at).toLocaleDateString()}</p>
          </>}
        </section>}
      </div>
    </> : <div className="group-columns">
      <section className="panel">
        <div className="panel-head"><h2>Your groups</h2><div className="panel-head-actions">{!selecting && !!groups.length && <button className="secondary" disabled={busy} onClick={() => setSelecting(true)}>Select</button>}<button disabled={busy || selecting} onClick={newGroup}>+ New group</button></div></div>
        <p>Organize couples, families or any collection. Characters can belong to several groups.</p>
        {selecting && <SelectionBar count={picked.length} total={groups.length} onAll={() => setPicked(groups.map(g => g.id))} onNone={() => setPicked([])} onDone={stopSelecting}>
          <button type="button" className="danger secondary" disabled={busy || !picked.length} onClick={bulkDeleteGroups}>Delete</button>
        </SelectionBar>}
        <div className="group-list">{groups.map(g => {
          const shown = g.member_ids.map(id => byId.get(id)).filter((c): c is Character => !!c)
          const isPicked = picked.includes(g.id)
          return <div key={g.id} className={`group-row ${isPicked ? 'picked' : ''}`}>
            <button className="secondary group-main" disabled={busy} aria-pressed={selecting ? isPicked : editingGroup?.id === g.id} onClick={() => { if (selecting) togglePick(g.id); else if (canLeave()) openGroup(g) }}>
              {selecting && <span className="pick-box" aria-hidden="true" />}
              <span className="group-row-copy"><strong>{g.name}</strong><span>{g.member_ids.length} {g.member_ids.length === 1 ? 'member' : 'members'}</span></span>
              {!!shown.length && <span className="avatar-stack" aria-hidden="true">{shown.slice(0, 4).map(c => <Avatar key={c.id} character={c} size="mini" />)}{shown.length > 4 && <span className="avatar avatar-mini more">+{shown.length - 4}</span>}</span>}
            </button>
            {!selecting && <CardMenu label={g.name} disabled={busy} items={[
              { label: 'Rename', onSelect: () => { if (guardCard(g.id)) setRenaming({ kind: 'group', id: g.id, name: g.name }) } },
              { label: 'Delete group', danger: true, onSelect: () => deleteGroupFromCard(g) },
            ]} />}
          </div>
        })}</div>
      </section>
      {!editingGroup && !creatingGroup ? <section className="panel empty-detail"><span className="tiny-label">GROUPS</span><h2>{groups.length ? 'Select a group' : 'No groups yet'}</h2><p>{groups.length ? 'Choose a group from the list to see or change its members.' : 'Use + New group to save a couple, a family or any set of characters you want to pick together later.'}</p></section>
      : <section className="panel"><h2>{editingGroup ? 'Edit group' : 'New group'}</h2><form onSubmit={saveGroup}><fieldset disabled={busy}>
        <label htmlFor="group-name">Group name</label><input ref={groupNameRef} id="group-name" required maxLength={80} value={groupName} onChange={e => setGroupName(e.target.value)} />
        <fieldset className="member-picker"><legend>Members</legend>{characters.map(c => <label className="checkbox-label member-option" key={c.id}><input type="checkbox" checked={members.includes(c.id)} onChange={e => setMembers(old => e.target.checked ? [...old, c.id] : old.filter(id => id !== c.id))} /><Avatar character={c} size="mini" /><span>{c.name}{c.archived ? ' (archived)' : ''}</span></label>)}{!characters.length && <p>Create characters first, or save an empty group.</p>}</fieldset>
        <div className="panel-actions">
          {editingGroup && <button type="button" className="danger secondary" disabled={groupDirty} title={groupDirty ? 'Save or cancel your edits first' : 'Characters and photos are kept'} onClick={() => { if (window.confirm(`Delete group “${editingGroup.name}”? Characters and photos will remain.`)) void run(async () => {
            await mutate(`/api/groups/${editingGroup.id}?revision=${editingGroup.revision}`, 'DELETE')
            setGroups(old => old.filter(g => g.id !== editingGroup.id)); setCharacters(old => old.map(c => ({ ...c, group_ids: c.group_ids.filter(id => id !== editingGroup.id) }))); resetGroup()
          }, 'Group deleted. Characters kept.') }}>Delete group</button>}
          <span className="spacer">{groupDirty && 'Unsaved edits'}</span>
          <button type="button" className="secondary" onClick={() => { if (canLeave()) resetGroup() }}>Cancel</button>
          <button disabled={!groupName.trim() || (!!editingGroup && !groupDirty)}>{editingGroup ? 'Save group' : 'Create group'}</button>
        </div>
      </fieldset></form>
      </section>}
    </div>}
    <dialog ref={dialogRef} className="image-dialog" aria-labelledby="preview-title" onClose={() => setPreview(null)} onClick={e => { if (e.target === e.currentTarget) setPreview(null) }}>
      <form method="dialog"><button className="secondary" autoFocus>Close preview</button></form>
      {preview && <><h2 id="preview-title">{preview.label} reference</h2><img src={preview.original_url} alt={`${preview.label} reference at original size`} /><a href={preview.original_url} target="_blank" rel="noreferrer">Open original at full size</a></>}
    </dialog>
    {asking && <CopiesDialog title={asking.title} message={asking.message} copies={asking.copies} onChoose={choice => { asking.resolve(choice); setAsking(null) }} />}
    {renaming && <TextDialog title={renaming.kind === 'character' ? 'Rename character' : 'Rename group'} label={renaming.kind === 'character' ? 'Name or alias' : 'Group name'} initial={renaming.name} maxLength={80} onSave={saveRename} onClose={() => setRenaming(null)} />}
    <dialog ref={frameDialogRef} className="image-dialog frame-dialog" aria-labelledby="frame-title" onClose={() => setFraming(null)}>
      {framing && <FrameEditor key={framing.id} photo={framing} busy={busy} error={error} onSave={frame => saveFrame(framing, frame)} onCancel={() => setFraming(null)} />}
    </dialog>
  </div>
}
