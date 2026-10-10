import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import { send } from './api'
import { sentence } from './Controls'
import { Avatar, type Character, type Group } from './Library'
import type { ApprovalRecord, Box, PendingPolish, SceneDetail, SubjectAssignment } from './Scenes'

export type Action = 'replace' | 'keep' | 'unresolved'
export type BoxDraft = { label: string; bounding_box: Box }
type Draft = { action: Action; character_id: string | null; reference_ids: string[] | null }

const MAX_REFERENCES = 4
const actionLabels: Record<Action, string> = { replace: 'Use a character', keep: 'Keep original', unresolved: 'Decide later' }
const formatDate = (value: string) => new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value))
const round = (value: number) => Math.round(value * 10000) / 10000
const photoUrl = (id: string) => `/api/photos/${id}/thumbnail`
export const imageList = (images: number[]) => images.length ? images.map(n => `Image ${n}`).join(', ') : ''

function savedDrafts(scene: SceneDetail): Record<string, Draft> {
  return Object.fromEntries(scene.subjects.map(s => [s.label, { action: s.action, character_id: s.character_id, reference_ids: s.references_auto ? null : s.reference_ids }]))
}

/** The Base Image with subject boxes: read-only, clickable, or editable (drag to move, corner to resize). */
export function SubjectCanvas({ scene, boxes, names, show, editing, selected, onSelect, onChange }: {
  scene: { width: number; height: number; original_url: string; title: string }
  boxes: BoxDraft[]; names: Record<string, Character | undefined>; show: boolean; editing: boolean
  selected: string | null; onSelect?: (label: string) => void; onChange?: (label: string, box: Box) => void
}) {
  const frame = useRef<HTMLDivElement>(null)
  const drag = useRef<{ label: string; mode: 'move' | 'resize'; x: number; y: number; box: Box } | null>(null)
  function update(label: string, from: Box, dx: number, dy: number, mode: 'move' | 'resize') {
    const next = mode === 'move'
      ? { ...from, x: clamp(from.x + dx, 0, 1 - from.width), y: clamp(from.y + dy, 0, 1 - from.height) }
      : { ...from, width: clamp(from.width + dx, 0.02, 1 - from.x), height: clamp(from.height + dy, 0.02, 1 - from.y) }
    onChange?.(label, { x: round(next.x), y: round(next.y), width: round(next.width), height: round(next.height) })
  }
  function start(e: PointerEvent<HTMLElement>, item: BoxDraft, mode: 'move' | 'resize') {
    onSelect?.(item.label)
    if (!editing) return
    e.preventDefault(); e.stopPropagation()
    frame.current?.setPointerCapture(e.pointerId)
    drag.current = { label: item.label, mode, x: e.clientX, y: e.clientY, box: item.bounding_box }
  }
  function move(e: PointerEvent<HTMLDivElement>) {
    const d = drag.current
    const rect = frame.current?.getBoundingClientRect()
    if (!d || !rect) return
    update(d.label, d.box, (e.clientX - d.x) / rect.width, (e.clientY - d.y) / rect.height, d.mode)
  }
  function key(e: KeyboardEvent<HTMLElement>, item: BoxDraft) {
    const steps: Record<string, [number, number]> = { ArrowLeft: [-0.01, 0], ArrowRight: [0.01, 0], ArrowUp: [0, -0.01], ArrowDown: [0, 0.01] }
    if (!editing || !steps[e.key]) return
    e.preventDefault()
    update(item.label, item.bounding_box, ...steps[e.key], e.shiftKey ? 'resize' : 'move')
  }
  const interactive = editing || !!onSelect
  return <div ref={frame} className={`base-image ${editing ? 'editing' : ''}`} style={{ aspectRatio: `${scene.width} / ${scene.height}` }}
    onPointerMove={move} onPointerUp={() => { drag.current = null }} onPointerCancel={() => { drag.current = null }}>
    <img src={scene.original_url} alt={`Base Image for ${scene.title}`} draggable={false} />
    {show && boxes.map(item => {
      const who = names[item.label]
      const b = item.bounding_box
      return <span key={item.label} role={interactive ? 'button' : undefined} tabIndex={interactive ? 0 : undefined}
        aria-label={interactive ? `${item.label}${who ? `, ${who.name}` : ''}${editing ? '. Arrow keys move the box; Shift and arrow keys resize it.' : ''}` : undefined}
        aria-pressed={interactive && !editing ? selected === item.label : undefined}
        className={`subject-box ${interactive ? 'interactive' : ''} ${selected === item.label ? 'selected' : ''}`}
        style={{ left: `${b.x * 100}%`, top: `${b.y * 100}%`, width: `${b.width * 100}%`, height: `${b.height * 100}%` }}
        onPointerDown={e => start(e, item, 'move')} onKeyDown={e => { if (!editing && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onSelect?.(item.label) } else key(e, item) }}>
        <span className="subject-tag">{who && <Avatar character={who} size="mini" />}{item.label}{who ? ` · ${who.name}` : ''}</span>
        {editing && <span className="resize-handle" aria-hidden="true" onPointerDown={e => start(e, item, 'resize')} />}
      </span>
    })}
  </div>
}

function ReferencePicker({ character, draft, saved, onChange }: { character: Character; draft: Draft; saved: SubjectAssignment | undefined; onChange: (ids: string[] | null) => void }) {
  const auto = draft.reference_ids === null
  const savedRefs = saved && saved.character_id === character.id ? saved.reference_ids : null
  const chosen = auto ? savedRefs ?? [] : draft.reference_ids!
  const unchanged = !!savedRefs && JSON.stringify(chosen) === JSON.stringify(savedRefs)
  function toggle(id: string) {
    const index = chosen.indexOf(id)
    onChange(index >= 0 ? chosen.filter(x => x !== id) : [...chosen, id].slice(0, MAX_REFERENCES))
  }
  return <div className="ref-picker">
    <div className="ref-head">
      <strong>Reference photos</strong>
      <span className="hint">{auto ? savedRefs ? 'Chosen by the studio: the primary photo plus complementary views.' : 'The studio chooses up to 3 complementary photos when you save.' : `${chosen.length} of up to ${MAX_REFERENCES}, in the order you picked them.`}</span>
      {!auto && <button type="button" className="link-button" onClick={() => onChange(null)}>Let the studio choose</button>}
    </div>
    <div className="ref-grid" role="group" aria-label={`Reference photos of ${character.name}`}>
      {character.photos.map(p => {
        const index = chosen.indexOf(p.id)
        const number = unchanged && saved ? saved.images[index] : undefined
        return <label key={p.id} className={`ref-tile ${index >= 0 ? 'selected' : ''}`}>
          <input type="checkbox" className="visually-hidden" checked={index >= 0} disabled={index < 0 && chosen.length >= MAX_REFERENCES} onChange={() => toggle(p.id)} />
          <img src={p.thumbnail_url} alt="" loading="lazy" />
          <span className="ref-label">{p.label}{p.id === character.primary_photo_id ? ' · Primary' : ''}</span>
          {index >= 0 && <span className="ref-order">{number ? `Image ${number}` : `#${index + 1}`}</span>}
        </label>
      })}
    </div>
    {!chosen.length && !auto && <p className="frame-error">Choose at least one photo, or let the studio choose.</p>}
  </div>
}

/** Step 02: who appears where. Groups only narrow the list; the user confirms every subject. */
export function MappingPanel({ scene, token, characters, groups, busy, highlight, onHighlight, onSaved, onDirty, onAdjust, onRun }: {
  scene: SceneDetail; token: string; characters: Character[]; groups: Group[]; busy: boolean
  highlight: string | null; onHighlight: (label: string | null) => void; onSaved: (detail: SceneDetail) => Promise<void>
  onDirty: (dirty: boolean) => void; onAdjust: () => void; onRun: (action: () => Promise<void>, success: string) => void
}) {
  const [draft, setDraft] = useState<Record<string, Draft>>(() => savedDrafts(scene))
  const [group, setGroup] = useState(scene.mapping_group_id ?? '')
  const savedKey = JSON.stringify([savedDrafts(scene), scene.mapping_group_id ?? ''])
  useEffect(() => { const [d, g] = JSON.parse(savedKey); setDraft(d); setGroup(g) }, [savedKey])
  const dirty = JSON.stringify([draft, group]) !== savedKey
  useEffect(() => { onDirty(dirty); return () => onDirty(false) }, [dirty, onDirty])
  const cards = useRef<Record<string, HTMLElement | null>>({})
  useEffect(() => { if (highlight) cards.current[highlight]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) }, [highlight])

  const byId = Object.fromEntries(characters.map(c => [c.id, c]))
  const assigned = new Set(Object.values(draft).map(d => d.character_id).filter(Boolean) as string[])
  const members = new Set(groups.find(g => g.id === group)?.member_ids ?? [])
  const choices = characters.filter(c => (!c.archived || assigned.has(c.id)) && (!group || members.has(c.id) || assigned.has(c.id)))
  const stale = scene.subjects.some(s => s.action !== 'unresolved' && !s.confirmed)
  const set = (label: string, next: Partial<Draft>) => setDraft(old => ({ ...old, [label]: { ...old[label], ...next } }))
  const takenBy = (id: string, label: string) => Object.entries(draft).find(([other, d]) => other !== label && d.action === 'replace' && d.character_id === id)?.[0]

  function save() {
    if (scene.approval.state === 'approved' && !window.confirm('Saving changed assignments cancels the current approval. Continue?')) return
    onRun(async () => {
      const mappings = scene.subjects.map(s => {
        const d = draft[s.label]
        return d.action === 'replace' ? { label: s.label, action: d.action, character_id: d.character_id, reference_ids: d.reference_ids } : { label: s.label, action: d.action }
      })
      await onSaved(await send<SceneDetail>(`/api/scenes/${scene.id}/mappings`, 'PUT', token, { revision: scene.revision, group_id: group || null, mappings }))
    }, 'Assignments saved.')
  }

  if (!scene.analyses.length) return <p className="hint">Assign characters once the scene has an analysis.</p>
  return <>
    <div className="mapping-toolbar">
      <div><label htmlFor="mapping-group">Choose from</label>
        <select id="mapping-group" value={group} disabled={busy} onChange={e => setGroup(e.target.value)}>
          <option value="">All characters</option>
          {groups.map(g => <option key={g.id} value={g.id}>{g.name} ({g.member_ids.length})</option>)}
        </select></div>
      <button type="button" className="secondary" disabled={busy || dirty || !!scene.active_job} title={dirty ? 'Save or cancel your assignments first' : undefined} onClick={onAdjust}>Adjust subjects</button>
    </div>
    <p className="hint group-hint">A group only shortens the list. It never decides who stands where.</p>
    {stale && <p className="notice-line warning-line">The analysis changed after you assigned characters, so subjects may be numbered differently. Check each subject, then save.</p>}
    {!scene.subjects.length && <p className="notice-line">No people were found in this image, so there is nothing to assign. You can add a subject with Adjust subjects.</p>}
    <div className="assign-list">
      {scene.subjects.map(s => {
        const d = draft[s.label] ?? { action: 'unresolved', character_id: null, reference_ids: null }
        const character = d.character_id ? byId[d.character_id] : undefined
        return <section key={s.label} ref={el => { cards.current[s.label] = el }} className={`assign-card ${highlight === s.label ? 'highlight' : ''}`} aria-label={s.label}
          onMouseEnter={() => onHighlight(s.label)} onMouseLeave={() => onHighlight(null)} onFocus={() => onHighlight(s.label)}>
          <div className="assign-head">
            <span className="subject-chip">{s.label}</span>
            <span className="assign-summary">{[sentence(s.position), sentence(s.summary)].filter(Boolean).join(' · ')}</span>
            <span className={`assign-state ${d.action}`}>{d.action === 'replace' ? character?.name ?? 'Choose a character' : actionLabels[d.action]}</span>
          </div>
          <div className="segmented" role="radiogroup" aria-label={`What happens to ${s.label}`}>
            {(['replace', 'keep', 'unresolved'] as Action[]).map(a => <label key={a} className={`segment ${d.action === a ? 'selected' : ''}`}>
              <input type="radio" name={`action-${s.label}`} checked={d.action === a} disabled={busy} onChange={() => set(s.label, a === 'replace' ? { action: a } : { action: a, character_id: null, reference_ids: null })} />{actionLabels[a]}</label>)}
          </div>
          {d.action === 'replace' && <>
            <div className="character-picker" role="radiogroup" aria-label={`Character for ${s.label}`}>
              {choices.map(c => {
                const taken = takenBy(c.id, s.label)
                const reason = taken ? `Already ${taken}` : !c.photos.length ? 'No photos yet' : c.archived ? 'Archived' : ''
                return <label key={c.id} className={`pick-tile ${d.character_id === c.id ? 'selected' : ''} ${taken || !c.photos.length ? 'unavailable' : ''}`} title={reason || undefined}>
                  <input type="radio" className="visually-hidden" name={`character-${s.label}`} checked={d.character_id === c.id} disabled={busy || !!taken || !c.photos.length}
                    onChange={() => set(s.label, { character_id: c.id, reference_ids: null })} />
                  <Avatar character={c} size="mini" /><span className="pick-name">{c.name}</span>{reason && <small>{reason}</small>}
                </label>
              })}
              {!choices.length && <p className="hint">{group ? 'Nobody in this group yet. Choose All characters or edit the group.' : 'No characters yet. Add one in Characters first.'}</p>}
            </div>
            {character && <ReferencePicker character={character} draft={d} saved={scene.subjects.find(x => x.label === s.label)} onChange={ids => set(s.label, { reference_ids: ids })} />}
          </>}
          {d.action === 'keep' && <p className="hint">This person stays as they are in the Base Image. No reference photos are used for them.</p>}
          {d.action === 'unresolved' && <p className="hint">Every subject needs a character or Keep original before you can approve.</p>}
          {!dirty && s.problems.filter(p => !p.startsWith('Choose a character or Keep')).map(p => <p key={p} className="frame-error">{p}</p>)}
        </section>
      })}
    </div>
    <div className="panel-actions">
      <span className="spacer">{dirty ? 'Unsaved changes' : 'All assignments saved'}</span>
      <button type="button" className="secondary" disabled={!dirty || busy} onClick={() => { const [d, g] = JSON.parse(savedKey); setDraft(d); setGroup(g) }}>Cancel</button>
      <button type="button" disabled={!dirty || busy} onClick={save}>Save assignments</button>
    </div>
  </>
}

/** Word-level differences between two texts (longest common subsequence). */
export type Segment = { text: string; kind: 'same' | 'del' | 'ins' }
export function diffWords(before: string, after: string): { left: Segment[]; right: Segment[]; exact: boolean } {
  const a = before.split(/(\s+)/), b = after.split(/(\s+)/)
  const n = a.length, m = b.length
  if (n * m > 3_000_000) return { left: [{ text: before, kind: 'same' }], right: [{ text: after, kind: 'same' }], exact: false }
  const width = m + 1
  const table = new Uint32Array((n + 1) * width)
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
    table[i * width + j] = a[i] === b[j] ? table[(i + 1) * width + j + 1] + 1 : Math.max(table[(i + 1) * width + j], table[i * width + j + 1])
  const left: Segment[] = [], right: Segment[] = []
  const push = (list: Segment[], text: string, kind: Segment['kind']) => {
    const last = list[list.length - 1]
    if (last && last.kind === kind) last.text += text; else list.push({ text, kind })
  }
  let i = 0, j = 0
  while (i < n && j < m) {
    if (a[i] === b[j]) { push(left, a[i], 'same'); push(right, b[j], 'same'); i++; j++ }
    else if (table[(i + 1) * width + j] >= table[i * width + j + 1]) push(left, a[i++], 'del')
    else push(right, b[j++], 'ins')
  }
  while (i < n) push(left, a[i++], 'del')
  while (j < m) push(right, b[j++], 'ins')
  return { left, right, exact: true }
}

function DiffText({ segments }: { segments: Segment[] }) {
  return <div className="diff-text">{segments.map((s, i) => s.kind === 'del' ? <del key={i}>{s.text}</del> : s.kind === 'ins' ? <ins key={i}>{s.text}</ins> : <span key={i}>{s.text}</span>)}</div>
}

/** Compare the original and polished prompts; nothing changes until the user chooses. */
export function PolishDialog({ scene, pending, token, onClose, onSaved }: { scene: SceneDetail; pending: PendingPolish; token: string; onClose: () => void; onSaved: (detail: SceneDetail, message: string) => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const original = scene.prompts.find(p => p.id === pending.prompt_id)
  const [text, setText] = useState(pending.polished_text)
  const [handEdit, setHandEdit] = useState(false)
  const [missing, setMissing] = useState(pending.missing)
  const [accepted, setAccepted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { ref.current?.showModal() }, [])
  useEffect(() => {
    if (text === pending.polished_text) { setMissing(pending.missing); return }
    const timer = window.setTimeout(() => {
      send<{ missing: string[] }>(`/api/scenes/${scene.id}/prompts/check`, 'POST', token, { prompt_text: text }).then(r => setMissing(r.missing), () => undefined)
    }, 400)
    return () => window.clearTimeout(timer)
  }, [text, pending, scene.id, token])
  useEffect(() => { setAccepted(false) }, [missing.join('|')])
  const diff = useMemo(() => diffWords(original?.prompt_text ?? '', text), [original, text])
  async function decide(use: boolean) {
    setBusy(true); setError('')
    try {
      const detail = use
        ? await send<SceneDetail>(`/api/scenes/${scene.id}/prompts/polished`, 'POST', token, { job_id: pending.job_id, prompt_text: text, accept_warnings: accepted })
        : await send<SceneDetail>(`/api/scenes/${scene.id}/prompts/polished/${pending.job_id}/keep-original`, 'POST', token)
      onSaved(detail, use ? `Polished prompt saved as version ${detail.prompts[0].version}. Version ${pending.prompt_version} is kept.` : 'Kept the original prompt.')
    } catch (e) { setError(e instanceof Error ? e.message : 'That did not work. Try again.'); setBusy(false) }
  }
  return <dialog ref={ref} className="image-dialog polish-dialog" aria-labelledby="polish-title" onClose={onClose}>
    <div className="polish-body">
      <h2 id="polish-title">Compare the polished prompt</h2>
      <p className="hint">Claude rewrote version {pending.prompt_version} for clarity under fixed rules: keep every fact, add nothing, keep the subject labels, image numbers and identity instructions. <del>Removed</del> and <ins>added</ins> words are marked.{!diff.exact && ' These prompts are too long to mark every change.'}</p>
      <div className="compare-grid">
        <section aria-label="Original prompt"><h3>Original · version {pending.prompt_version}</h3><DiffText segments={diff.left} /></section>
        <section aria-label="Polished prompt"><div className="compare-head"><h3>Polished</h3><button type="button" className="link-button" onClick={() => setHandEdit(h => !h)}>{handEdit ? 'Show changes' : 'Edit by hand'}</button></div>
          {handEdit ? <><label htmlFor="polished-text" className="visually-hidden">Polished prompt</label><textarea id="polished-text" className="prompt-area" rows={18} maxLength={40000} value={text} onChange={e => setText(e.target.value)} /></> : <DiffText segments={diff.right} />}
        </section>
      </div>
      {missing.length > 0 ? <div className="check-box warning" role="alert">
        <strong>Some required elements are missing</strong>
        <ul>{missing.map(m => <li key={m}>{m}</li>)}</ul>
        <label className="checkbox-label"><input type="checkbox" checked={accepted} onChange={e => setAccepted(e.target.checked)} /> Use it anyway. I checked these myself.</label>
      </div> : <p className="check-box ok">All required elements are present: every subject, its image numbers and every keep-original instruction.</p>}
      {error && <p className="frame-error" role="alert">{error}</p>}
      <div className="dialog-actions">
        <button type="button" className="link-button" onClick={onClose}>Decide later</button>
        <span className="spacer" />
        <button type="button" className="secondary" disabled={busy} onClick={() => void decide(false)}>Keep original</button>
        <button type="button" disabled={busy || !text.trim() || (missing.length > 0 && !accepted)} onClick={() => void decide(true)}>{text === pending.polished_text ? 'Use polished' : 'Use my edited version'}</button>
      </div>
    </div>
  </dialog>
}

function ApprovalSummary({ record }: { record: ApprovalRecord }) {
  return <ul className="plain-list">{record.mappings.map(m => <li key={m.subject}><strong>{m.subject}</strong>: {m.action === 'replace' ? `${m.character_name ?? 'Deleted character'} (${imageList(m.images)})` : actionLabels[m.action as Action]}</li>)}</ul>
}

/** Step 04: everything the image will be made from, then explicit approval. */
export function ReviewPanel({ scene, characters, generationEngine, busy, unsaved, onApprove, onWithdraw, onGo }: {
  scene: SceneDetail; characters: Character[]; generationEngine: string; busy: boolean; unsaved: boolean
  onApprove: (acceptWarnings: boolean) => void; onWithdraw: (id: string) => void; onGo: (step: 'analysis' | 'characters' | 'prompt') => void
}) {
  const [checked, setChecked] = useState(false)
  const { blockers, warnings, notes } = scene.review
  useEffect(() => { setChecked(false) }, [warnings.join('|'), scene.review.prompt_id])
  const byId = Object.fromEntries(characters.map(c => [c.id, c]))
  const analysis = scene.analyses[0]
  const prompt = scene.prompts[0]
  const current = scene.approval.current
  const approved = scene.approval.state === 'approved' && current
  const canApprove = !approved && !blockers.length && (!warnings.length || checked) && !unsaved && !busy
  return <>
    {approved ? <div className="approved-banner" role="status">
      <span className="approved-mark" aria-hidden="true">✓</span>
      <div><strong>Approved {formatDate(current.approved_at)}</strong>
        <p>These exact inputs are locked for generation: analysis version {current.analysis_version}, prompt version {current.prompt_version}{current.is_polished ? ' (polished)' : ''}, the assignments and reference photos below. Changing any of them cancels the approval.</p>
        <p className="hint">Snapshot {current.snapshot_hash.slice(0, 12)} · Generation arrives in Phase 5.</p></div>
      <button type="button" className="secondary" disabled={busy} onClick={() => { if (window.confirm('Withdraw this approval? The scene stays as it is; you can approve it again later.')) onWithdraw(current.id) }}>Withdraw</button>
    </div> : scene.approval.ended_reason && <p className="notice-line warning-line">Previous approval ended: {scene.approval.ended_reason}</p>}

    <div className="review-grid">
      <section className="review-card">
        <div className="review-card-head"><h4>Scene and analysis</h4><button type="button" className="link-button" onClick={() => onGo('analysis')}>Edit</button></div>
        <img className="review-thumb" src={scene.thumbnail_url} alt="" />
        <p>Image 1 · Base Image · {scene.width} × {scene.height}</p>
        <p className="hint">{analysis ? `Analysis version ${analysis.version} · ${analysis.analysis.subjects.length} ${analysis.analysis.subjects.length === 1 ? 'person' : 'people'}` : 'Not analysed yet'}</p>
      </section>
      <section className="review-card">
        <div className="review-card-head"><h4>Generation</h4></div>
        <p><strong>{generationEngine === 'manual' ? 'Manual' : 'Codex'}</strong> is the generation engine in Studio settings.</p>
        <p className="hint">Approval covers the content, not the engine, so you can switch engines later without approving again. Output: one image framed like the Base Image; more settings arrive with generation in Phase 5.</p>
        <p className="hint"><strong>Cost:</strong> no per-use charge and no API key. Generating with Codex will use your ChatGPT plan’s allowance, which image generation uses faster than text. Nothing is generated or sent in this phase.</p>
      </section>
    </div>

    <section className="review-card wide">
      <div className="review-card-head"><h4>Subjects and characters</h4><button type="button" className="link-button" onClick={() => onGo('characters')}>Edit</button></div>
      {!scene.subjects.length ? <p className="hint">No people in this scene.</p> : <ul className="review-subjects">{scene.subjects.map(s => {
        const c = s.character_id ? byId[s.character_id] : undefined
        return <li key={s.label}>
          <span className="subject-chip">{s.label}</span>
          {s.action === 'replace' ? <span className="review-who">{c && <Avatar character={c} size="mini" />}{c?.name ?? 'Choose a character'}</span> : <span className="review-who muted">{actionLabels[s.action]}</span>}
          {s.action === 'replace' && <span className="review-refs">{s.reference_ids.map((id, i) => <span key={id} className="review-ref"><img src={photoUrl(id)} alt="" loading="lazy" /><small>Image {s.images[i]}</small></span>)}</span>}
        </li>
      })}</ul>}
    </section>

    <section className="review-card wide">
      <div className="review-card-head"><h4>{prompt ? `Prompt · version ${prompt.version}${prompt.is_polished ? ' · polished' : ''}` : 'Prompt'}</h4><button type="button" className="link-button" onClick={() => onGo('prompt')}>Edit</button></div>
      {prompt ? <><pre className="review-prompt">{prompt.prompt_text}</pre>
        <h4 className="sub-head">Negative prompt</h4><pre className="review-prompt short">{prompt.negative_prompt || '—'}</pre></> : <p className="hint">Save a prompt version first.</p>}
    </section>

    {!approved && <>
      {blockers.length > 0 && <div className="check-box blocked"><strong>Before you can approve</strong><ul>{blockers.map(b => <li key={b}>{b}</li>)}</ul></div>}
      {warnings.length > 0 && <div className="check-box warning"><strong>Please check</strong><ul>{warnings.map(w => <li key={w}>{w}</li>)}</ul>
        <label className="checkbox-label"><input type="checkbox" checked={checked} disabled={!!blockers.length} onChange={e => setChecked(e.target.checked)} /> I checked these and want to approve anyway.</label></div>}
      {notes.map(n => <p key={n} className="notice-line">{n}</p>)}
      {!blockers.length && !warnings.length && <p className="check-box ok">Everything needed is in place. Approval saves an unchangeable snapshot of these inputs.</p>}
      <div className="panel-actions">
        <span className="spacer">{unsaved ? 'Save or discard your unsaved edits first.' : 'Approval is saved and survives restarts.'}</span>
        <button type="button" disabled={!canApprove} onClick={() => onApprove(warnings.length > 0)}>Approve scene</button>
      </div>
    </>}

    {scene.approvals.length > 0 && <details className="approval-history"><summary>Approval history ({scene.approvals.length})</summary>
      <ul>{scene.approvals.map(a => <li key={a.id}>
        <div><strong>{formatDate(a.approved_at)}</strong> <span className={`run-status ${a.invalidated_at ? 'cancelled' : 'completed'}`}>{a.invalidated_at ? 'Ended' : 'Active'}</span></div>
        <span className="hint">Analysis v{a.analysis_version} · prompt v{a.prompt_version}{a.is_polished ? ' (polished)' : ''}{a.invalidated_reason ? ` · ${a.invalidated_reason}` : ''}</span>
        <ApprovalSummary record={a} />
      </li>)}</ul></details>}
  </>
}
