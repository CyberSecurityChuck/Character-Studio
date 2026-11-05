import { useCallback, useEffect, useMemo, useState } from 'react'
import { request, send } from './api'
import { Dialog, plural } from './Batches'
import { Avatar, type Character } from './Library'
import { SubjectCanvas, imageList, type BoxDraft } from './Mapping'
import { replaceRoute } from './route'
import type { SceneSet } from './SceneSets'
import type { SceneDetail } from './Scenes'

// Phase 7C-1: approving a whole scene set - the review queue and Approve all (D030, D037).
// Every scene still gets its own approval snapshot; nothing here generates anything.

export type ApprovalRow = {
  scene_id: string; title: string; thumbnail_url: string; state: 'ready' | 'blocked' | 'approved'; reason: string | null
  uncertain: number; warnings: string[]; mismatch: string | null; analysis_id: string | null; prompt_id: string | null; prompt_version: number | null
}
export type ApprovalCounts = { total: number; approved: number; blocked: number; ready: number; clean: number; uncertain: number; warnings: number; mismatched: number }
export type ApprovalList = { rows: ApprovalRow[]; counts: ApprovalCounts }
type Outcome = { done: { scene_id: string; title: string }[]; skipped: { scene_id: string; title: string; reason: string }[] }

const SKIP_LIMIT = 8
const actionWords = { keep: 'Keeps its original look', unresolved: 'Not decided' } as const

// Approve all ------------------------------------------------------------------------------------

/** A thumbnail for every scene that can be approved; risky ones need an explicit tick first. */
export function ApproveAllDialog({ item, token, onClose, onDone }: { item: SceneSet; token: string; onClose: () => void; onDone: (text: string, problem?: string) => void }) {
  const [list, setList] = useState<ApprovalList | null>(null)
  const [tickDetails, setTickDetails] = useState(false)
  const [tickWarnings, setTickWarnings] = useState(false)
  const [tickMismatch, setTickMismatch] = useState(false)
  const [off, setOff] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  useEffect(() => { request<ApprovalList>(`/api/scene-sets/${item.id}/approval`).then(setList, e => setError(e instanceof Error ? e.message : 'The scenes could not be loaded.')) }, [item.id])
  const ready = useMemo(() => list?.rows.filter(r => r.state === 'ready') ?? [], [list])
  const blocked = list?.rows.filter(r => r.state === 'blocked') ?? []
  const needs = (r: ApprovalRow) => [r.uncertain && !tickDetails ? 'accept uncertain details' : '', r.warnings.length && !tickWarnings ? 'accept warnings' : '', r.mismatch && !tickMismatch ? 'extra people may keep their original look' : ''].filter(Boolean)
  const included = ready.filter(r => !needs(r).length && !off.has(r.scene_id))
  const toggle = (id: string) => setOff(old => { const next = new Set(old); if (next.has(id)) next.delete(id); else next.add(id); return next })
  const counts = list?.counts
  async function approve() {
    setBusy(true); setError('')
    try {
      const result = await send<Outcome>(`/api/scene-sets/${item.id}/approve-all`, 'POST', token, {
        items: included.map(r => ({ scene_id: r.scene_id, prompt_id: r.prompt_id, analysis_id: r.analysis_id })),
        accept_uncertain: tickDetails, accept_warnings: tickWarnings, allow_mismatch: tickMismatch,
      })
      setOutcome(result)
    } catch (e) { setError(e instanceof Error ? e.message : 'The scenes could not be approved.') }
    finally { setBusy(false) }
  }
  const finish = () => {
    if (outcome) onDone(`${plural(outcome.done.length, 'scene')} approved, each with its own approval${outcome.skipped.length ? `. ${plural(outcome.skipped.length, 'scene')} could not be approved` : ''}.`, outcome.skipped.length ? `Not approved: ${outcome.skipped.map(s => `${s.title} (${s.reason})`).join('; ')}` : undefined)
    else onClose()
  }
  return <Dialog label="approve-all-title" className="assign-dialog approve-all" onClose={finish}>
    <div className="text-dialog-form">
      <h2 id="approve-all-title">Approve all · {item.name}</h2>
      {error && <p className="frame-error" role="alert">{error}</p>}
      {list === null && !error ? <p role="status">Loading…</p> : outcome ? <>
        <p className="ok-line">{plural(outcome.done.length, 'scene')} approved. Each has its own approval; nothing was generated.</p>
        {outcome.skipped.length > 0 && <div className="check-box warning"><strong>{plural(outcome.skipped.length, 'scene')} could not be approved</strong>
          <ul>{outcome.skipped.slice(0, SKIP_LIMIT).map(s => <li key={s.scene_id}><b>{s.title}</b>: {s.reason}</li>)}{outcome.skipped.length > SKIP_LIMIT && <li>and {outcome.skipped.length - SKIP_LIMIT} more</li>}</ul></div>}
        <div className="dialog-actions"><button type="button" onClick={finish}>Done</button></div>
      </> : counts && !ready.length ? <>
        <p className="hint">No scene in this set is ready to approve right now.{counts.blocked ? ` ${plural(counts.blocked, 'scene')} still need${counts.blocked === 1 ? 's' : ''} analysis, characters or a prompt.` : ''}</p>
        <div className="dialog-actions"><button type="button" onClick={onClose}>Close</button></div>
      </> : counts && <>
        <div className="check-box warning aa-risk"><strong>Before you approve many scenes at once</strong>
          <ul>
            <li>Each scene gets its own approval of the exact analysis, assignments, reference photos and prompt it has now. Changing any of them later cancels that scene’s approval.</li>
            <li>You do not see each scene in full here. Scenes with uncertain details, warnings or a different number of people and characters are left out until you tick the matching box below.</li>
            <li>Approving generates nothing and costs nothing. Generating stays a separate click.</li>
          </ul></div>
        <div className="aa-ticks">
          <label className={`checkbox-label ${counts.uncertain ? '' : 'is-off'}`}><input type="checkbox" checked={tickDetails} disabled={!counts.uncertain} onChange={e => setTickDetails(e.target.checked)} />
            <span><b>Accept uncertain details</b> ({plural(counts.uncertain, 'scene')})<small>The engine was not sure about them. Ticking confirms them as described, saves a new analysis version and keeps each saved prompt word for word.</small></span></label>
          <label className={`checkbox-label ${counts.warnings ? '' : 'is-off'}`}><input type="checkbox" checked={tickWarnings} disabled={!counts.warnings} onChange={e => setTickWarnings(e.target.checked)} />
            <span><b>Accept warnings</b> ({plural(counts.warnings, 'scene')})<small>For example a prompt that no longer names every assigned person. Each scene’s first warning is shown on its tile.</small></span></label>
          <label className={`checkbox-label ${counts.mismatched ? '' : 'is-off'}`}><input type="checkbox" checked={tickMismatch} disabled={!counts.mismatched} onChange={e => setTickMismatch(e.target.checked)} />
            <span><b>Extra people may keep their original look</b> ({plural(counts.mismatched, 'scene')})<small>These scenes have a different number of people and characters. People without a character keep their original look; unused characters do not appear.</small></span></label>
        </div>
        <div className="assign-toolbar"><span className="hint">{included.length} of {plural(ready.length, 'scene')} will be approved</span></div>
        <ul className="aa-grid">{ready.map(r => {
          const missing = needs(r)
          const on = !missing.length && !off.has(r.scene_id)
          return <li key={r.scene_id} className={`${on ? 'on' : ''} ${missing.length ? 'held' : ''}`}>
            <label><input type="checkbox" checked={on} disabled={!!missing.length || busy} onChange={() => toggle(r.scene_id)} aria-label={`Approve ${r.title}`} />
              <img src={r.thumbnail_url} alt="" loading="lazy" /><strong>{r.title}</strong></label>
            <span className="aa-tags">
              {r.uncertain > 0 && <span className="tag warn">{plural(r.uncertain, 'uncertain detail')}</span>}
              {r.warnings.length > 0 && <span className="tag warn" title={r.warnings.join('\n')}>{plural(r.warnings.length, 'warning')}</span>}
              {r.mismatch && <span className="tag warn">{r.mismatch}</span>}
              {!r.uncertain && !r.warnings.length && !r.mismatch && <span className="tag">Clean</span>}
            </span>
            {r.warnings[0] && <small className="aa-note">{r.warnings[0]}</small>}
            {missing.length > 0 && <small className="aa-held">Left out: tick “{missing[0]}”</small>}
          </li>
        })}</ul>
        {blocked.length > 0 && <div className="check-box blocked"><strong>{plural(blocked.length, 'scene')} cannot be approved</strong>
          <ul>{blocked.slice(0, SKIP_LIMIT).map(s => <li key={s.scene_id}><b>{s.title}</b>: {s.reason}</li>)}{blocked.length > SKIP_LIMIT && <li>and {blocked.length - SKIP_LIMIT} more</li>}</ul></div>}
        <div className="dialog-actions"><button type="button" className="secondary" disabled={busy} onClick={onClose}>Cancel</button>
          <button type="button" disabled={busy || !included.length} onClick={() => void approve()}>{busy ? 'Approving…' : `Approve ${plural(included.length, 'scene')}`}</button></div>
      </>}
    </div>
  </Dialog>
}

// Review queue -----------------------------------------------------------------------------------

// Where the queue was before Open full editor, so coming back lands on the same scene.
let resume: { set: string; at: string } | null = null

/** One screen per scene: look, then Approve & next, Skip, or Open full editor. Uncertain details are confirmed here. */
export function ReviewQueue({ setId, token, onExit, onOpenScene }: { setId: string; token: string; onExit: () => void; onOpenScene: (id: string) => void }) {
  const [setName, setSetName] = useState('')
  const [queue, setQueue] = useState<ApprovalRow[] | null>(null)
  const [index, setIndex] = useState(0)
  const [detail, setDetail] = useState<SceneDetail | null>(null)
  const [characters, setCharacters] = useState<Character[]>([])
  const [checked, setChecked] = useState(false)
  const [approved, setApproved] = useState<string[]>([])
  const [skipped, setSkipped] = useState<ApprovalRow[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [promptOpen, setPromptOpen] = useState(false)
  const load = useCallback((start?: string | null) => Promise.all([
    request<ApprovalList>(`/api/scene-sets/${setId}/approval`), request<SceneSet[]>('/api/scene-sets'), request<Character[]>('/api/characters'),
  ]).then(([list, sets, people]) => {
    const rows = list.rows.filter(r => r.state === 'ready')
    setQueue(rows); setCharacters(people); setSetName(sets.find(s => s.id === setId)?.name ?? '')
    setIndex(Math.max(0, rows.findIndex(r => r.scene_id === start)))
  }, e => setError(e instanceof Error ? e.message : 'The queue could not be loaded.')), [setId])
  // After Open full editor the address is the scene's, so the place comes from memory.
  useEffect(() => { void load(new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('at') ?? (resume?.set === setId ? resume.at : null)) }, [load, setId])
  const current = queue?.[index] ?? null
  const loadDetail = useCallback((id: string) => request<SceneDetail>(`/api/scenes/${id}`).then(d => { setDetail(d); setError('') }, e => setError(e instanceof Error ? e.message : 'The scene could not be loaded.')), [])
  useEffect(() => {
    setDetail(null); setChecked(false); setPromptOpen(false)
    if (!current) return
    replaceRoute(`scenes/review?set=${setId}&at=${current.scene_id}`)
    resume = { set: setId, at: current.scene_id }
    void loadDetail(current.scene_id)
  }, [current?.scene_id, setId, loadDetail]) // eslint-disable-line react-hooks/exhaustive-deps
  const byId = useMemo(() => Object.fromEntries(characters.map(c => [c.id, c])), [characters])
  const names = useMemo(() => Object.fromEntries((detail?.subjects ?? []).map(s => [s.label, s.character_id ? byId[s.character_id] : undefined])), [detail, byId])
  const boxes: BoxDraft[] = detail?.subjects.map(s => ({ label: s.label, bounding_box: s.bounding_box })) ?? []

  const next = () => setIndex(i => i + 1)
  async function confirmDetails() {
    if (!detail) return
    setBusy(true); setError('')
    try {
      await send(`/api/scene-sets/${setId}/uncertain/accept`, 'POST', token, { items: [{ scene_id: detail.id, analysis_id: detail.analyses[0].id }], keep_prompt: true })
      await loadDetail(detail.id)
    } catch (e) { setError(e instanceof Error ? e.message : 'The details could not be confirmed.') }
    finally { setBusy(false) }
  }
  async function approve() {
    if (!detail || !current) return
    setBusy(true); setError('')
    try {
      await send(`/api/scenes/${detail.id}/approve`, 'POST', token, { prompt_id: detail.review.prompt_id, accept_warnings: detail.review.warnings.length > 0 })
      setApproved(a => [...a, current.title]); next()
    } catch (e) { setError(e instanceof Error ? e.message : 'The scene could not be approved.') }
    finally { setBusy(false) }
  }
  const skip = () => { if (current) setSkipped(s => [...s, current]); next() }

  const pending = detail?.analyses[0]?.analysis.uncertainties ?? []
  const prompt = detail?.prompts[0]
  const warnings = detail?.review.warnings ?? []
  const blockers = (detail?.review.blockers ?? []).filter(b => !pending.length || !b.startsWith('Confirm or correct the'))
  const canApprove = !!detail && !busy && !pending.length && !blockers.length && (!warnings.length || checked) && !detail.active_job && detail.approval.state !== 'approved'
  const total = (queue?.length ?? 0)
  const finished = queue !== null && index >= total

  return <div className="review-queue">
    <header className="rq-head">
      <button type="button" className="secondary compact" onClick={() => { resume = null; onExit() }}>← Back to scenes</button>
      <div className="rq-title"><h2>Review queue{setName ? ` · ${setName}` : ''}</h2>
        {queue !== null && total > 0 && <span className="hint">{finished ? 'Finished' : `Scene ${index + 1} of ${total}`} · {approved.length} approved · {skipped.length} skipped</span>}</div>
      {queue !== null && total > 0 && <div className="rq-progress" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={Math.min(index, total)}><span style={{ width: `${(Math.min(index, total) / total) * 100}%` }} /></div>}
    </header>
    {error && <p className="frame-error" role="alert">{error}</p>}
    {queue === null && !error ? <p role="status">Loading the queue…</p>
      : queue !== null && !total ? <div className="panel rq-done"><h3>Nothing to review</h3><p className="hint">No scene in this set is waiting for approval. Scenes still missing analysis, characters or a prompt are not part of the queue.</p><button type="button" onClick={() => { resume = null; onExit() }}>Back to scenes</button></div>
        : finished ? <div className="panel rq-done">
          <h3>{approved.length ? `${plural(approved.length, 'scene')} approved` : 'Queue finished'}</h3>
          <p className="hint">Each approved scene has its own approval. Nothing has been generated.</p>
          {skipped.length > 0 && <div className="check-box warning"><strong>{plural(skipped.length, 'scene')} skipped</strong><ul>{skipped.map(s => <li key={s.scene_id}>{s.title}</li>)}</ul></div>}
          <div className="dialog-actions">
            {skipped.length > 0 && <button type="button" className="secondary" onClick={() => { setApproved([]); setSkipped([]); void load() }}>Review skipped scenes again</button>}
            <button type="button" onClick={() => { resume = null; onExit() }}>Back to scenes</button></div></div>
          : current && <div className="rq-body">
            <section className="rq-image">
              {detail ? <SubjectCanvas scene={detail} boxes={boxes} names={names} show editing={false} selected={null} /> : <div className="rq-image-wait"><img src={current.thumbnail_url} alt="" /></div>}
            </section>
            <section className="rq-side">
              <div className="rq-scene-head"><h3>{current.title}</h3>{detail?.mismatch && <span className="tag warn">{detail.mismatch}</span>}</div>
              {!detail ? <p role="status">Loading the scene…</p> : <>
                <h4 className="sub-head">Who appears</h4>
                {!detail.subjects.length ? <p className="hint">No people in this scene.</p> : <ul className="review-subjects">{detail.subjects.map(s => {
                  const c = s.character_id ? byId[s.character_id] : undefined
                  return <li key={s.label}><span className="subject-chip">{s.label}</span>
                    {s.action === 'replace' ? <span className="review-who">{c && <Avatar character={c} size="mini" />}{c?.name ?? 'A character'}<small className="hint">{imageList(s.images)}</small></span> : <span className="review-who muted">{actionWords[s.action as 'keep' | 'unresolved']}</span>}
                  </li>
                })}</ul>}
                {pending.length > 0 && <div className="check-box warning rq-box"><strong>{plural(pending.length, 'uncertain detail')}</strong>
                  <ul>{pending.map(u => <li key={u.field + u.note}><b>{u.field}</b>: {u.note}</li>)}</ul>
                  <p className="hint">The engine was not sure. Confirm them as described (saved as confirmed by you; the prompt below stays as it is), or open the full editor to correct them.</p>
                  <button type="button" className="compact" disabled={busy} onClick={() => void confirmDetails()}>Confirm these details</button></div>}
                <h4 className="sub-head">Prompt{prompt ? ` · version ${prompt.version}${prompt.is_polished ? ' · polished' : ''}` : ''}</h4>
                {prompt ? <><pre className={`review-prompt ${promptOpen ? '' : 'rq-clamp'}`}>{prompt.prompt_text}</pre>
                  <button type="button" className="link-button" onClick={() => setPromptOpen(o => !o)}>{promptOpen ? 'Show less' : 'Show the whole prompt'}</button></> : <p className="hint">No saved prompt.</p>}
                {blockers.length > 0 && <div className="check-box blocked rq-box"><strong>Before you can approve</strong><ul>{blockers.map(b => <li key={b}>{b}</li>)}</ul></div>}
                {warnings.length > 0 && <div className="check-box warning rq-box"><strong>Please check</strong><ul>{warnings.map(w => <li key={w}>{w}</li>)}</ul>
                  <label className="checkbox-label"><input type="checkbox" checked={checked} onChange={e => setChecked(e.target.checked)} /> I checked these and want to approve anyway.</label></div>}
                {detail.review.notes.map(n => <p key={n} className="notice-line">{n}</p>)}
                {!blockers.length && !warnings.length && !pending.length && <p className="check-box ok rq-box">Everything needed is in place. Approval saves an unchangeable snapshot of these inputs.</p>}
              </>}
              <div className="rq-actions">
                <button type="button" className="secondary" disabled={busy} onClick={skip}>Skip</button>
                <button type="button" className="secondary" disabled={busy} onClick={() => onOpenScene(current.scene_id)}>Open full editor</button>
                <button type="button" disabled={!canApprove} onClick={() => void approve()}>Approve &amp; next</button>
              </div>
            </section>
          </div>}
  </div>
}
