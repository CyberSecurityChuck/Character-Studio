import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type PointerEvent } from 'react'
import { getBootstrap, request, type Bootstrap } from './api'
import { replaceRoute, routeParts } from './route'

type Frame = { x: number; y: number; zoom: number }
type Photo = { id: string; label: string; width: number; height: number; frame?: Frame; thumbnail_url: string; original_url: string }
type Character = { id: string; name: string; age_category: string; notes: string; archived: boolean; revision: number; primary_photo_id: string | null; photos: Photo[]; group_ids: string[]; created_at: string; updated_at: string; cleanup_pending?: boolean }
type Group = { id: string; name: string; revision: number; member_ids: string[] }
const labels = ['Front', 'Left three-quarter', 'Right three-quarter', 'Left profile', 'Right profile', 'Full body', 'Additional']
const defaultFrame: Frame = { x: 0.5, y: 0.3, zoom: 1 }
const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value))

// Sizes are percentages of a square box, so one frame renders identically at every avatar size.
function frameBox(photo: Photo, frame: Frame) {
  const ratio = photo.width / photo.height
  return { w: Math.max(ratio, 1) * frame.zoom * 100, h: Math.max(1 / ratio, 1) * frame.zoom * 100 }
}
function FramedImage({ photo, frame = photo.frame ?? defaultFrame }: { photo: Photo; frame?: Frame }) {
  const { w, h } = frameBox(photo, frame)
  return <img className="framed" src={photo.thumbnail_url} alt="" draggable={false} loading="lazy" style={{ width: `${w}%`, height: `${h}%`, left: `${(100 - w) * frame.x}%`, top: `${(100 - h) * frame.y}%` }} />
}
function Avatar({ character, size = 'card' }: { character: Character; size?: 'card' | 'header' | 'mini' }) {
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
  const errorRef = useRef<HTMLDivElement>(null)
  const nameRef = useRef<HTMLInputElement>(null)
  const groupNameRef = useRef<HTMLInputElement>(null)
  const dialogRef = useRef<HTMLDialogElement>(null)
  const frameDialogRef = useRef<HTMLDialogElement>(null)
  const uploadRef = useRef<HTMLInputElement>(null)
  const lock = useRef(false)
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
  function canLeave() { return !busy && (!dirty || window.confirm('Discard unsaved edits?')) }
  function resetGroup() { setEditingGroup(null); setCreatingGroup(false); setGroupName(''); setMembers([]) }
  function openGroup(g: Group) { setEditingGroup(g); setCreatingGroup(false); setGroupName(g.name); setMembers(g.member_ids) }
  function newGroup() { if (canLeave()) { resetGroup(); setCreatingGroup(true); requestAnimationFrame(() => groupNameRef.current?.focus()) } }
  function clearEditors() { setSelected(null); setCreating(false); setName(''); setAge('Adult'); setNotes(''); resetGroup() }
  async function run(action: () => Promise<void>, success = 'Saved locally.') {
    if (lock.current) return
    lock.current = true; setBusy(true); setError(''); setMessage('')
    try { await action(); setMessage(success) }
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
      <div className="library-tabs" aria-label="Library sections">{(['characters', 'groups'] as const).map(t => <button key={t} className={tab === t ? '' : 'secondary'} aria-pressed={tab === t} disabled={busy} onClick={() => { if (canLeave()) { clearEditors(); setTab(t) } }}>{t === 'characters' ? 'Characters' : 'Groups'}</button>)}</div>
      <button className="secondary" disabled={busy} onClick={() => void reload()}>Reload library</button>
    </div>
    {error && <div className="error" role="alert" tabIndex={-1} ref={errorRef}><strong>Could not finish that action.</strong><p>{error}</p><p>Your unsaved edits remain. Reloading discards them.</p></div>}
    <p className="library-status" role="status">{busy ? message || 'Saving…' : message}</p>
    {loading ? <p role="status">Loading your library…</p> : tab === 'characters' ? <>
      <div className="library-toolbar filters">
        <div><label htmlFor="character-search">Search characters</label><input id="character-search" type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search by name" /></div>
        <div><label htmlFor="group-filter">Group</label><select id="group-filter" value={groupFilter} onChange={e => setGroupFilter(e.target.value)}><option value="">All groups</option>{groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}</select></div>
        <label className="checkbox-label"><input type="checkbox" checked={archived} onChange={e => setArchived(e.target.checked)} /> Show archived</label>
        <button disabled={busy} onClick={() => { if (canLeave()) { resetGroup(); selectCharacter(null); requestAnimationFrame(() => nameRef.current?.focus()) } }}>+ New character</button>
      </div>
      <div className={`library-columns ${creating || selected ? 'with-detail' : ''}`}>
        <section aria-label="Saved characters">
          {!filtered.length ? <div className="empty-library panel"><span className="tiny-label">FAMILIAR FACES, SAVED ONCE</span><h2>{query || groupFilter ? 'No matching characters' : archived ? 'No archived characters' : 'Your cast starts here'}</h2><p>{query || groupFilter ? 'Try another name or group.' : 'Create a profile, then add a few reference photos. Everything stays on this computer.'}</p></div> : <div className="character-grid">{filtered.map(c => {
            return <button className={`character-card ${selected?.id === c.id ? 'selected' : ''}`} aria-pressed={selected?.id === c.id} key={c.id} disabled={busy} onClick={() => { if (canLeave()) { resetGroup(); selectCharacter(c); requestAnimationFrame(() => nameRef.current?.focus()) } }}>
              <Avatar character={c} />
              <span className="character-card-copy"><strong>{c.name}</strong><span>{c.age_category} · {c.photos.length} {c.photos.length === 1 ? 'photo' : 'photos'}</span></span>
            </button>
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
                    <button className="danger secondary" disabled={photoLocked} aria-label={`Delete photo ${i + 1}`} onClick={() => { if (window.confirm('Permanently delete this original photo and its thumbnail? This cannot be undone.')) void run(async () => {
                      const c = await mutate<Character>(`/api/photos/${p.id}?revision=${selected.revision}`, 'DELETE'); acceptCharacter(c)
                      if (c.cleanup_pending) throw new Error('Photo removed from the library. A locked file is pending deletion; restart the studio to retry cleanup.')
                    }, 'Photo deleted.') }}>Delete</button>
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
            <div className="detail-section"><h3>{selected.archived ? 'Archived character' : 'Remove from the library'}</h3><p className="hint">Archive hides the character and keeps its photos and memberships. Permanent deletion removes the profile, originals, thumbnails and memberships. There is no generation history in this phase.</p>
              <div className="save-row"><button className="secondary" disabled={photoLocked} onClick={() => void run(async () => acceptCharacter(await mutate<Character>(`/api/characters/${selected.id}/archive`, 'PUT', { revision: selected.revision, archived: !selected.archived })), selected.archived ? 'Character restored.' : 'Character archived.')}>{selected.archived ? 'Restore character' : 'Archive character'}</button>
                <button className="danger secondary" disabled={photoLocked} onClick={() => { if (window.confirm(`Permanently delete “${selected.name}” and all ${selected.photos.length} reference photos? This cannot be undone. Archive instead if you want to keep them.`)) void run(async () => {
                  const result = await mutate<{cleanup_pending: boolean}>(`/api/characters/${selected.id}?revision=${selected.revision}`, 'DELETE')
                  setCharacters(old => old.filter(c => c.id !== selected.id)); clearEditors()
                  setGroups(await request<Group[]>('/api/groups'))
                  if (result.cleanup_pending) throw new Error('Character removed. Locked files are pending deletion; restart the studio to retry cleanup.')
                }, 'Character deleted.') }}>Delete permanently</button></div>
            </div>
            <p className="hint detail-foot">Created {new Date(selected.created_at).toLocaleDateString()} · Updated {new Date(selected.updated_at).toLocaleDateString()}</p>
          </>}
        </section>}
      </div>
    </> : <div className="group-columns">
      <section className="panel">
        <div className="panel-head"><h2>Your groups</h2><button disabled={busy} onClick={newGroup}>+ New group</button></div>
        <p>Organize couples, families or any collection. Characters can belong to several groups.</p>
        <div className="group-list">{groups.map(g => {
          const shown = g.member_ids.map(id => byId.get(id)).filter((c): c is Character => !!c)
          return <button key={g.id} className="secondary" disabled={busy} aria-pressed={editingGroup?.id === g.id} onClick={() => { if (canLeave()) openGroup(g) }}>
            <span className="group-row-copy"><strong>{g.name}</strong><span>{g.member_ids.length} {g.member_ids.length === 1 ? 'member' : 'members'}</span></span>
            {!!shown.length && <span className="avatar-stack" aria-hidden="true">{shown.slice(0, 4).map(c => <Avatar key={c.id} character={c} size="mini" />)}{shown.length > 4 && <span className="avatar avatar-mini more">+{shown.length - 4}</span>}</span>}
          </button>
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
    <dialog ref={frameDialogRef} className="image-dialog frame-dialog" aria-labelledby="frame-title" onClose={() => setFraming(null)}>
      {framing && <FrameEditor key={framing.id} photo={framing} busy={busy} error={error} onSave={frame => saveFrame(framing, frame)} onCancel={() => setFraming(null)} />}
    </dialog>
  </div>
}
