import { useEffect, useRef, useState, type FormEvent } from 'react'
import { getBootstrap, request, type Bootstrap } from './api'

type Photo = { id: string; label: string; width: number; height: number; thumbnail_url: string; original_url: string }
type Character = { id: string; name: string; age_category: string; notes: string; archived: boolean; revision: number; primary_photo_id: string | null; photos: Photo[]; group_ids: string[]; created_at: string; updated_at: string; cleanup_pending?: boolean }
type Group = { id: string; name: string; revision: number; member_ids: string[] }
const labels = ['Front', 'Left three-quarter', 'Right three-quarter', 'Left profile', 'Right profile', 'Full body', 'Additional']

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
  const [tab, setTab] = useState<'characters' | 'groups'>('characters')
  const [editingGroup, setEditingGroup] = useState<Group | null>(null)
  const [groupName, setGroupName] = useState('')
  const [members, setMembers] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [preview, setPreview] = useState<Photo | null>(null)
  const errorRef = useRef<HTMLDivElement>(null)
  const nameRef = useRef<HTMLInputElement>(null)
  const dialogRef = useRef<HTMLDialogElement>(null)
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
    let active = true
    Promise.all([request<Character[]>('/api/characters'), request<Group[]>('/api/groups')])
      .then(([c, g]) => { if (active) { setCharacters(c); setGroups(g) } })
      .catch(e => { if (active) setError(e.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

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
  function resetGroup() { setEditingGroup(null); setGroupName(''); setMembers([]) }
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
    })
  }
  function saveGroup(e: FormEvent) {
    e.preventDefault()
    void run(async () => {
      const g = await mutate<Group>(editingGroup ? `/api/groups/${editingGroup.id}` : '/api/groups', editingGroup ? 'PUT' : 'POST', {
        name: groupName.trim(), member_ids: members, ...(editingGroup ? { revision: editingGroup.revision } : {}),
      })
      setGroups(old => old.some(x => x.id === g.id) ? old.map(x => x.id === g.id ? g : x) : [...old, g])
      setCharacters(old => old.map(c => ({ ...c, group_ids: [...c.group_ids.filter(id => id !== g.id), ...(g.member_ids.includes(c.id) ? [g.id] : [])] })))
      setEditingGroup(g); setGroupName(g.name); setMembers(g.member_ids)
    })
  }
  function changePhoto(photo: Photo, label: string, primary = false) {
    if (!selected) return
    void run(async () => acceptCharacter(await mutate<Character>(`/api/photos/${photo.id}`, 'PUT', { revision: selected.revision, label, primary })))
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
            const photo = c.photos.find(p => p.id === c.primary_photo_id)
            return <button className={`character-card ${selected?.id === c.id ? 'selected' : ''}`} aria-pressed={selected?.id === c.id} key={c.id} disabled={busy} onClick={() => { if (canLeave()) { resetGroup(); selectCharacter(c); requestAnimationFrame(() => nameRef.current?.focus()) } }}>
              {photo ? <img src={photo.thumbnail_url} alt={`${c.name}, primary reference`} loading="lazy" /> : <span className="character-placeholder" aria-hidden="true">{c.name.slice(0, 1).toLocaleUpperCase()}</span>}
              <span className="character-card-copy"><strong>{c.name}</strong><span>{c.age_category} · {c.photos.length} {c.photos.length === 1 ? 'photo' : 'photos'}</span></span>
            </button>
          })}</div>}
        </section>
        {(creating || selected) && <section className="panel character-detail" aria-label="Character profile">
          <div className="section-title"><h2>{creating ? 'New character' : 'Character profile'}</h2><button className="secondary" disabled={busy} onClick={() => { if (canLeave()) clearEditors() }}>Close</button></div>
          <form onSubmit={saveCharacter}><fieldset disabled={busy}>
            <label htmlFor="character-name">Name or alias</label><input ref={nameRef} id="character-name" required maxLength={80} value={name} onChange={e => setName(e.target.value)} />
            <label htmlFor="age-category">Age category</label><select id="age-category" value={age} onChange={e => setAge(e.target.value)}>{['Adult', 'Teen', 'Child'].map(a => <option key={a}>{a}</option>)}</select>
            <label htmlFor="character-notes">Notes (optional)</label><textarea id="character-notes" maxLength={4000} rows={3} value={notes} onChange={e => setNotes(e.target.value)} />
            <p className="hint">Use a nickname if you prefer. Avoid unnecessary personal details.</p>
            <div className="save-row"><button disabled={!name.trim() || (!creating && !characterDirty)}>{creating ? 'Create character' : 'Save profile'}</button>{characterDirty && <span>Unsaved edits</span>}</div>
          </fieldset></form>
          {selected && <>
            <p className="hint">Created {new Date(selected.created_at).toLocaleDateString()} · Updated {new Date(selected.updated_at).toLocaleDateString()}</p>
            <div className="detail-section"><h3>Reference photos</h3><p className="hint">JPEG, PNG or WebP · up to {Math.floor(data.max_upload_bytes / 1048576)} MB each. Originals stay unchanged.</p>
              <label htmlFor="photo-upload">Add photos</label><input ref={uploadRef} id="photo-upload" type="file" accept="image/jpeg,image/png,image/webp" multiple disabled={busy || !!characterDirty || selected.archived} onChange={e => void upload(Array.from(e.target.files || []))} />
              {characterDirty && <p className="hint">Save your profile before managing photos or archiving.</p>}
              {selected.archived && <p className="hint">Restore this character to add more photos.</p>}
              <div className="photo-grid">{selected.photos.map(p => <article className="photo-card" key={p.id}>
                <button className="photo-preview" onClick={() => setPreview(p)} aria-label={`Preview ${p.label} photo`}><img src={p.thumbnail_url} alt={`${selected.name}: ${p.label}`} loading="lazy" /></button>
                <span className="photo-meta">{p.width} × {p.height}{p.id === selected.primary_photo_id ? ' · Primary' : ''}</span>
                <label htmlFor={`label-${p.id}`}>Reference label</label><select id={`label-${p.id}`} disabled={busy || !!characterDirty} value={p.label} onChange={e => changePhoto(p, e.target.value)}>{labels.map(l => <option key={l}>{l}</option>)}</select>
                <button className="secondary" disabled={busy || !!characterDirty || p.id === selected.primary_photo_id} onClick={() => changePhoto(p, p.label, true)}>{p.id === selected.primary_photo_id ? 'Primary reference' : 'Make primary'}</button>
                <button className="danger secondary" disabled={busy || !!characterDirty} onClick={() => { if (window.confirm('Permanently delete this original photo and its thumbnail? This cannot be undone.')) void run(async () => {
                  const c = await mutate<Character>(`/api/photos/${p.id}?revision=${selected.revision}`, 'DELETE'); acceptCharacter(c)
                  if (c.cleanup_pending) throw new Error('Photo removed from the library. A locked file is pending deletion; restart the studio to retry cleanup.')
                }, 'Photo deleted.') }}>Delete photo</button>
              </article>)}</div>
              {!selected.photos.length && <p className="hint">No photos yet. The first photo becomes the primary reference.</p>}
            </div>
            <div className="detail-section"><h3>Groups</h3><p>{groups.filter(g => g.member_ids.includes(selected.id)).map(g => g.name).join(', ') || 'No groups yet.'}</p><button className="secondary" disabled={busy} onClick={() => { if (canLeave()) { clearEditors(); setTab('groups') } }}>Manage groups</button></div>
            <div className="detail-section"><h3>{selected.archived ? 'Archived character' : 'Remove from the library'}</h3><p className="hint">Archive hides the character and keeps its photos and memberships. Permanent deletion removes the profile, originals, thumbnails and memberships. There is no generation history in this phase.</p>
              <div className="save-row"><button className="secondary" disabled={busy || !!characterDirty} onClick={() => void run(async () => acceptCharacter(await mutate<Character>(`/api/characters/${selected.id}/archive`, 'PUT', { revision: selected.revision, archived: !selected.archived })), selected.archived ? 'Character restored.' : 'Character archived.')}>{selected.archived ? 'Restore character' : 'Archive character'}</button>
                <button className="danger secondary" disabled={busy || !!characterDirty} onClick={() => { if (window.confirm(`Permanently delete “${selected.name}” and all ${selected.photos.length} reference photos? This cannot be undone. Archive instead if you want to keep them.`)) void run(async () => {
                  const result = await mutate<{cleanup_pending: boolean}>(`/api/characters/${selected.id}?revision=${selected.revision}`, 'DELETE')
                  setCharacters(old => old.filter(c => c.id !== selected.id)); clearEditors()
                  setGroups(await request<Group[]>('/api/groups'))
                  if (result.cleanup_pending) throw new Error('Character removed. Locked files are pending deletion; restart the studio to retry cleanup.')
                }, 'Character deleted.') }}>Delete permanently</button></div>
            </div>
          </>}
        </section>}
      </div>
    </> : <div className="group-columns">
      <section className="panel"><h2>Your groups</h2><p>Organize couples, families or any collection. Characters can belong to several groups.</p>
        <button className="secondary" disabled={busy} onClick={() => { if (canLeave()) resetGroup() }}>+ New group</button>
        {!groups.length && <p className="hint">No groups yet. Create one using the form.</p>}
        <div className="group-list">{groups.map(g => <button key={g.id} className="secondary" disabled={busy} aria-pressed={editingGroup?.id === g.id} onClick={() => { if (canLeave()) { setEditingGroup(g); setGroupName(g.name); setMembers(g.member_ids) } }}><strong>{g.name}</strong><span>{g.member_ids.length} members</span></button>)}</div>
      </section>
      <section className="panel"><h2>{editingGroup ? 'Edit group' : 'New group'}</h2><form onSubmit={saveGroup}><fieldset disabled={busy}>
        <label htmlFor="group-name">Group name</label><input id="group-name" required maxLength={80} value={groupName} onChange={e => setGroupName(e.target.value)} />
        <fieldset className="member-picker"><legend>Members</legend>{characters.map(c => <label className="checkbox-label" key={c.id}><input type="checkbox" checked={members.includes(c.id)} onChange={e => setMembers(old => e.target.checked ? [...old, c.id] : old.filter(id => id !== c.id))} />{c.name}{c.archived ? ' (archived)' : ''}</label>)}{!characters.length && <p>Create characters first, or save an empty group.</p>}</fieldset>
        <div className="save-row"><button disabled={!groupName.trim() || (!!editingGroup && !groupDirty)}>{editingGroup ? 'Save group' : 'Create group'}</button>{groupDirty && <span>Unsaved edits</span>}</div>
      </fieldset></form>
        {editingGroup && <div className="detail-section"><p className="hint">Deleting a group keeps every character and photo.</p><button className="danger secondary" disabled={busy || groupDirty} onClick={() => { if (window.confirm(`Delete group “${editingGroup.name}”? Characters and photos will remain.`)) void run(async () => {
          await mutate(`/api/groups/${editingGroup.id}?revision=${editingGroup.revision}`, 'DELETE')
          setGroups(old => old.filter(g => g.id !== editingGroup.id)); setCharacters(old => old.map(c => ({ ...c, group_ids: c.group_ids.filter(id => id !== editingGroup.id) }))); resetGroup()
        }, 'Group deleted. Characters kept.') }}>Delete group</button></div>}
      </section>
    </div>}
    <dialog ref={dialogRef} className="image-dialog" aria-labelledby="preview-title" onClose={() => setPreview(null)} onClick={e => { if (e.target === e.currentTarget) setPreview(null) }}>
      <form method="dialog"><button className="secondary" autoFocus>Close preview</button></form>
      {preview && <><h2 id="preview-title">{preview.label} reference</h2><img src={preview.original_url} alt={`${preview.label} reference at original size`} /><a href={preview.original_url} target="_blank" rel="noreferrer">Open original at full size</a></>}
    </dialog>
  </div>
}
