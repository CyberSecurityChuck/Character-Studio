import { useMemo, useState } from 'react'
import { send } from './api'
import { Dialog, plural } from './Batches'
import { CardMenu } from './Controls'
import type { SceneSet } from './SceneSets'
import type { SceneSummary } from './Scenes'

// The Sets tab of the Scenes page (7C review, D038): every scene set as a card, like Groups
// under Characters, with Open, Rename, Add scenes and Delete.

const stageOrder: [SceneSummary['stage'], string][] = [
  ['not_analysed', 'not analysed'], ['needs_check', 'need your check'], ['ready_to_approve', 'ready to approve'],
  ['approved', 'approved'], ['completed', 'completed'], ['running', 'running'],
]

function StageLine({ scenes }: { scenes: SceneSummary[] }) {
  if (!scenes.length) return <p className="hint">No scenes yet. Add some with Add scenes or + Add scenes.</p>
  const parts = stageOrder.map(([id, word]) => [scenes.filter(s => s.stage === id).length, id, word] as const).filter(([n]) => n > 0)
  const problems = scenes.filter(s => s.problem).length
  return <ul className="set-stages">{parts.map(([n, id, word]) => <li key={id} className={`stage-${id}`}><b>{n}</b> {word}</li>)}{problems > 0 && <li className="stage-problem"><b>{problems}</b> with problems</li>}</ul>
}

export function SetsView({ scenes, sets, token, busy, onOpen, onRename, onDelete, onNew, onMoved, onImport }: {
  scenes: SceneSummary[]; sets: SceneSet[]; token: string; busy: boolean
  onOpen: (setId: string) => void; onRename: (item: SceneSet) => void; onDelete: (item: SceneSet) => void
  onNew: () => void; onMoved: (text: string) => void; onImport: (setId: string) => void
}) {
  const [adding, setAdding] = useState<SceneSet | null>(null)
  const loose = scenes.filter(s => !s.scene_set_id)
  return <div className="sets-view">
    <div className="sets-head"><p className="hint">A set groups scenes so you can prepare, approve and generate them together. Each scene is in at most one set.</p>
      <button type="button" disabled={busy} onClick={onNew}>+ New set</button></div>
    {!sets.length ? <div className="empty-library panel"><h2>No scene sets yet</h2><p>Create a set here, or choose a new set when you add scenes. Then use Add scenes to put scenes you already have into it.</p></div>
      : <div className="sets-grid">{sets.map(item => {
        const members = scenes.filter(s => s.scene_set_id === item.id)
        return <article key={item.id} className="set-tile">
          <button type="button" className="set-tile-main" disabled={busy} onClick={() => onOpen(item.id)} aria-label={`Open ${item.name}`}>
            <span className={`set-mosaic n${Math.min(4, members.length)}`}>{members.slice(0, 4).map(s => <img key={s.id} src={s.thumbnail_url} alt="" loading="lazy" />)}{!members.length && <span className="set-mosaic-empty">Empty</span>}</span>
          </button>
          <div className="set-tile-copy">
            <div className="set-tile-title"><h3>{item.name}</h3>
              <CardMenu label={`scene set ${item.name}`} disabled={busy} items={[
                { label: 'Rename set', onSelect: () => onRename(item) },
                { label: 'Delete set', danger: true, onSelect: () => onDelete(item) },
              ]} /></div>
            <p className="hint">{plural(members.length, 'scene')} · created {new Date(item.created_at).toLocaleDateString(undefined, { dateStyle: 'medium' })}</p>
            <StageLine scenes={members} />
            <div className="set-tile-actions">
              <button type="button" className="secondary compact" disabled={busy} onClick={() => onOpen(item.id)}>Open</button>
              <button type="button" className="secondary compact" disabled={busy} onClick={() => setAdding(item)}>Add scenes</button>
            </div>
          </div>
        </article>
      })}</div>}
    {loose.length > 0 && sets.length > 0 && <p className="hint sets-loose">{plural(loose.length, 'scene')} {loose.length === 1 ? 'is' : 'are'} not in a set. <button type="button" className="link-button" onClick={() => onOpen('none')}>Show {loose.length === 1 ? 'it' : 'them'}</button></p>}
    {adding && <AddToSetDialog item={adding} scenes={scenes} sets={sets} token={token} onClose={() => setAdding(null)} onImport={() => { const id = adding.id; setAdding(null); onImport(id) }}
      onAdded={count => { setAdding(null); onMoved(`${plural(count, 'scene')} added to “${adding.name}”.`) }} />}
  </div>
}

/** Pick scenes to put into a set. A scene that is in another set leaves that set. */
function AddToSetDialog({ item, scenes, sets, token, onClose, onAdded, onImport }: { item: SceneSet; scenes: SceneSummary[]; sets: SceneSet[]; token: string; onClose: () => void; onAdded: (count: number) => void; onImport: () => void }) {
  const [query, setQuery] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const names = useMemo(() => Object.fromEntries(sets.map(s => [s.id, s.name])), [sets])
  const others = scenes.filter(s => s.scene_set_id !== item.id && s.title.toLocaleLowerCase().includes(query.toLocaleLowerCase()))
    .sort((a, b) => Number(!!a.scene_set_id) - Number(!!b.scene_set_id) || b.created_at.localeCompare(a.created_at))
  const fromOther = scenes.filter(s => picked.includes(s.id) && s.scene_set_id).length
  const toggle = (id: string) => setPicked(old => old.includes(id) ? old.filter(x => x !== id) : [...old, id])
  async function add() {
    setBusy(true); setError('')
    try { const r = await send<{ moved: number }>('/api/scene-set-members', 'PUT', token, { scene_ids: picked, scene_set_id: item.id }); onAdded(r.moved) }
    catch (e) { setError(e instanceof Error ? e.message : 'The scenes could not be added.'); setBusy(false) }
  }
  return <Dialog label="add-to-set-title" className="assign-dialog" onClose={onClose}>
    <div className="text-dialog-form">
      <h2 id="add-to-set-title">Add scenes to “{item.name}”</h2>
      <div className="add-import"><div><strong>New images</strong><span className="hint">Import Base Images from your computer straight into this set.</span></div>
        <button type="button" className="secondary compact" disabled={busy} onClick={onImport}>Import new images…</button></div>
      <h3 className="sub-head">Scenes already in your studio</h3>
      <p className="hint">Scenes not in a set are listed first. Adding a scene that is in another set moves it here. Nothing else about the scene changes.</p>
      <div className="assign-toolbar"><input type="search" aria-label="Search scenes" placeholder="Search by title" value={query} onChange={e => setQuery(e.target.value)} />
        <span className="hint">{plural(picked.length, 'scene')} chosen</span></div>
      {!others.length ? <p className="notice-line">{query ? 'No other scenes match.' : 'Every scene in your studio is already in this set. Use Import new images to add more.'}</p> : <ul className="add-grid">{others.map(s => <li key={s.id} className={picked.includes(s.id) ? 'on' : ''}>
        <label><input type="checkbox" checked={picked.includes(s.id)} onChange={() => toggle(s.id)} />
          <img src={s.thumbnail_url} alt="" loading="lazy" /><strong>{s.title}</strong>
          <small>{s.scene_set_id ? `In ${names[s.scene_set_id] ?? 'another set'}` : 'Not in a set'}</small></label></li>)}</ul>}
      {fromOther > 0 && <p className="notice-line">{plural(fromOther, 'chosen scene')} {fromOther === 1 ? 'leaves its' : 'leave their'} current set.</p>}
      {error && <p className="frame-error" role="alert">{error}</p>}
      <div className="dialog-actions"><button type="button" className="secondary" disabled={busy} onClick={onClose}>Cancel</button>
        <button type="button" disabled={busy || !picked.length} onClick={() => void add()}>{busy ? 'Adding…' : `Add ${plural(picked.length, 'scene')}`}</button></div>
    </div>
  </Dialog>
}
