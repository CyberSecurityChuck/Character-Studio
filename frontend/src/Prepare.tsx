import { useCallback, useEffect, useMemo, useState } from 'react'
import { request, send } from './api'
import { ChargeSummary, engineNames, isApiEngine, sendsTo, useApiEngines } from './ApiEngines'
import { Dialog, plural, MAX_ANALYSIS_RUNS, type Batch } from './Batches'
import { Avatar, type Character, type Group } from './Library'
import { PresetSelect, usePresets } from './Presets'
import { duration } from './Results'
import type { SceneSet } from './SceneSets'

// Phase 7B: preparing a whole scene set - Analyse all, the Assign table, Draft prompts for all,
// optional Polish all and the polished-prompt review (D030, D035).

type Counts = { total: number; analyse: number; analysed: number; uncertain: number; assign: number; assign_open: number; draft: number; redraft: number; polish: number; polish_waiting: number; polish_running: number; review: number; mismatched: number; busy: number }
type Skipped = { scene_id: string; title: string; reason: string }

const SKIP_LIMIT = 8
function SkippedList({ items, heading }: { items: { title: string; reason: string }[]; heading: string }) {
  if (!items.length) return null
  return <div className="check-box warning"><strong>{heading}</strong>
    <ul>{items.slice(0, SKIP_LIMIT).map(s => <li key={s.title + s.reason}><b>{s.title}</b>: {s.reason}</li>)}{items.length > SKIP_LIMIT && <li>and {items.length - SKIP_LIMIT} more</li>}</ul></div>
}

export type PrepareAction = 'analyse' | 'check' | 'assign' | 'draft' | 'polish' | 'review'
type StepState = 'done' | 'next' | 'todo' | 'running' | 'waiting' | 'optional'
const stateWords: Record<StepState, string> = { done: 'Done', next: 'Next up', todo: 'To do', running: 'Running', waiting: 'Waiting', optional: 'Optional' }

/** "Prepare this set": the preparation steps with how many scenes each would touch, coloured by state. */
export function PreparePanel({ item, token, analysisEngine, version, disabled, onChanged, onNotice, onBatches, onOpenScene }: {
  item: SceneSet; token: string; analysisEngine: string; version: string; disabled: boolean
  onChanged: () => void; onNotice: (text: string, problem?: string) => void; onBatches: () => void; onOpenScene: (id: string) => void
}) {
  const [counts, setCounts] = useState<Counts | null>(null)
  const [open, setOpen] = useState<PrepareAction | null>(null)
  const [busy, setBusy] = useState(false)
  const load = useCallback(() => request<Counts>(`/api/scene-sets/${item.id}/preparation`).then(setCounts, () => undefined), [item.id])
  // Reloaded whenever the page's scenes change (analyses, assignments, prompts, polish runs).
  useEffect(() => { void load() }, [load, version, item.scene_count])
  if (!counts || !counts.total) return null
  const polishing = counts.polish_waiting + counts.polish_running
  const close = () => { setOpen(null); void load(); onChanged() }
  async function cancelPolish() {
    if (!window.confirm('Cancel the polish runs that have not started? A run in progress finishes.')) return
    setBusy(true)
    try { const r = await send<{ cancelled: number }>(`/api/scene-sets/${item.id}/polish-all/cancel`, 'POST', token); onNotice(`${plural(r.cancelled, 'waiting polish run')} cancelled.`); void load(); onChanged() }
    catch (e) { onNotice('', e instanceof Error ? e.message : 'The runs could not be cancelled.') }
    finally { setBusy(false) }
  }
  // Every step is in exactly one state; the first unfinished step is "Next up" (orange).
  const raw: Record<'analyse' | 'check' | 'assign' | 'draft', StepState> = {
    analyse: counts.analyse ? (counts.busy ? 'running' : 'todo') : 'done',
    check: counts.uncertain ? 'todo' : counts.analysed ? 'done' : 'waiting',
    assign: counts.assign_open ? 'todo' : counts.assign ? 'done' : 'waiting',
    draft: counts.draft ? 'todo' : counts.redraft ? 'done' : 'waiting',
  }
  const firstOpen = (['analyse', 'check', 'assign', 'draft'] as const).find(k => raw[k] === 'todo')
  const stateOf = (k: keyof typeof raw): StepState => k === firstOpen ? 'next' : raw[k]
  const polishState: StepState = polishing ? 'running' : counts.review ? 'next' : counts.polish ? 'optional' : 'waiting'
  const card = (state: StepState, n: number, title: React.ReactNode, text: string, action: React.ReactNode) =>
    <li className={`prep-${state}`}><span className="prepare-number">{state === 'done' ? '✓' : n}</span>
      <div><strong>{title}</strong><span>{text}</span></div><span className="prepare-state">{stateWords[state]}</span>{action}</li>
  const btn = (state: StepState, label: string, on: PrepareAction, off: boolean, title?: string) =>
    <button type="button" className={`compact ${state === 'next' ? '' : 'secondary'}`} disabled={disabled || off} title={title} onClick={() => setOpen(on)}>{label}</button>
  return <section className="prepare-panel" aria-label={`Prepare ${item.name}`}>
    <div className="prepare-head"><h3>Prepare this set</h3><span className="hint">One action per step, in order. Each starts only when you click it; nothing here approves or generates anything.</span></div>
    <ol className="prepare-steps">
      {card(stateOf('analyse'), 1, 'Analyse all', counts.analyse ? `${plural(counts.analyse, 'scene')} not analysed` : 'Every scene is analysed',
        btn(stateOf('analyse'), 'Analyse all', 'analyse', !counts.analyse, analysisEngine === 'manual' ? 'Manual analysis is selected in Studio settings' : undefined))}
      {card(stateOf('check'), 2, 'Check details', counts.uncertain ? `${plural(counts.uncertain, 'scene')} with uncertain details` : counts.analysed ? 'Nothing uncertain' : 'Waiting for analyses',
        btn(stateOf('check'), 'Check details', 'check', !counts.uncertain))}
      {card(stateOf('assign'), 3, 'Assign characters', counts.assign_open ? `${plural(counts.assign_open, 'scene')} still need someone` : counts.assign ? `Everyone is assigned${counts.mismatched ? ` · ${counts.mismatched} labelled mismatch` : ''}` : 'Waiting for analyses',
        btn(stateOf('assign'), 'Open the table', 'assign', !counts.assign))}
      {card(stateOf('draft'), 4, 'Draft prompts for all', counts.draft ? `${plural(counts.draft, 'scene')} ready for a draft` : counts.redraft ? 'Drafted. You can redraft with a preset' : 'Waiting for assignments',
        btn(stateOf('draft'), 'Draft prompts', 'draft', !(counts.draft + counts.redraft)))}
      {card(polishState, 5, <>Polish all <small>optional</small></>, polishing ? `${plural(counts.polish_running, 'run')} running, ${counts.polish_waiting} waiting` : counts.review ? `${plural(counts.review, 'polished prompt')} to review` : counts.polish ? `${plural(counts.polish, 'prompt')} could be polished` : 'Needs saved prompts',
        polishing ? <button type="button" className="secondary compact" disabled={busy} onClick={() => void cancelPolish()}>Cancel waiting</button>
          : counts.review ? btn(polishState, 'Review polished', 'review', false)
            : <button type="button" className="secondary compact" disabled={disabled || !counts.polish} onClick={() => setOpen('polish')}>Polish all</button>)}
    </ol>
    {counts.mismatched > 0 && <p className="hint prepare-note">{plural(counts.mismatched, 'scene')} {counts.mismatched === 1 ? 'has' : 'have'} a different number of people and characters. {counts.mismatched === 1 ? 'It stays' : 'They stay'} in Needs your check until you open and approve {counts.mismatched === 1 ? 'it' : 'them'}.</p>}
    {open === 'analyse' && <AnalyseAllDialog item={item} token={token} engine={analysisEngine} count={counts.analyse} onClose={() => setOpen(null)} onStarted={(text, problem) => { close(); onBatches(); onNotice(text, problem) }} />}
    {open === 'check' && <CheckDetails item={item} token={token} onClose={close} onNotice={onNotice} onOpenScene={id => { setOpen(null); onOpenScene(id) }} />}
    {open === 'assign' && <AssignTable item={item} token={token} onClose={close} onNotice={onNotice} />}
    {open === 'draft' && <DraftDialog item={item} token={token} ready={counts.draft} again={counts.redraft} onClose={close} onNotice={onNotice} />}
    {open === 'polish' && <PolishDialog item={item} token={token} count={counts.polish} onClose={() => setOpen(null)} onStarted={text => { close(); onNotice(text) }} />}
    {open === 'review' && <PolishReview item={item} token={token} onClose={close} onNotice={onNotice} />}
  </section>
}

// Check details --------------------------------------------------------------------------------

type UncertainRow = { scene_id: string; title: string; thumbnail_url: string; analysis_id: string; uncertainties: { field: string; note: string }[] }

/** The uncertain details the engine flagged, per scene: accept them as described, or open the scene to correct one. */
function CheckDetails({ item, token, onClose, onNotice, onOpenScene }: { item: SceneSet; token: string; onClose: () => void; onNotice: (text: string, problem?: string) => void; onOpenScene: (id: string) => void }) {
  const [rows, setRows] = useState<UncertainRow[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [failed, setFailed] = useState<Skipped[]>([])
  const load = useCallback(() => request<{ rows: UncertainRow[] }>(`/api/scene-sets/${item.id}/uncertain`).then(r => setRows(r.rows), e => setError(e.message)), [item.id])
  useEffect(() => { void load() }, [load])
  async function accept(list: UncertainRow[]) {
    setBusy(true); setError(''); setFailed([])
    try {
      const result = await send<{ done: { count: number }[]; failed: Skipped[] }>(`/api/scene-sets/${item.id}/uncertain/accept`, 'POST', token, { items: list.map(r => ({ scene_id: r.scene_id, analysis_id: r.analysis_id })) })
      setFailed(result.failed)
      if (result.done.length) onNotice(`Details accepted for ${plural(result.done.length, 'scene')}. They are saved as confirmed by you.`)
      await load()
    } catch (e) { setError(e instanceof Error ? e.message : 'The details could not be accepted.') }
    finally { setBusy(false) }
  }
  const total = rows?.reduce((n, r) => n + r.uncertainties.length, 0) ?? 0
  return <Dialog label="check-title" className="assign-dialog" onClose={onClose}>
    <div className="text-dialog-form">
      <h2 id="check-title">Check details · {item.name}</h2>
      <p className="hint">The engine was not sure about these details. Read them, then accept them as described or open the scene to correct one. Accepting saves them as <b>confirmed by you</b> in a new analysis version; the people, boxes and assignments stay exactly as they are.</p>
      {error && <p className="frame-error" role="alert">{error}</p>}
      {rows === null ? <p role="status">Loading…</p> : !rows.length ? <p className="ok-line">No scene has uncertain details.</p> : <>
        <div className="assign-toolbar"><span className="hint">{plural(total, 'detail')} in {plural(rows.length, 'scene')}</span>
          <button type="button" className="compact" disabled={busy} onClick={() => { if (window.confirm(`Accept all ${plural(total, 'detail')} in ${plural(rows.length, 'scene')} as described?`)) void accept(rows) }}>Accept all</button></div>
        <ul className="assign-rows detail-rows">{rows.map(row => <li key={row.scene_id}>
          <img src={row.thumbnail_url} alt="" loading="lazy" />
          <div className="assign-title"><strong>{row.title}</strong>
            <div className="detail-list">{row.uncertainties.map(u => <p key={u.field + u.note}><b>{u.field}</b><span>{u.note}</span></p>)}</div></div>
          <div className="row-actions"><button type="button" className="secondary compact" disabled={busy} onClick={() => onOpenScene(row.scene_id)}>Open scene</button>
            <button type="button" className="secondary compact" disabled={busy} onClick={() => void accept([row])}>Accept as described</button></div>
        </li>)}</ul></>}
      <SkippedList items={failed} heading={`${plural(failed.length, 'scene')} could not be changed`} />
      <div className="dialog-actions"><button type="button" onClick={onClose}>Done</button></div>
    </div>
  </Dialog>
}

// Analyse all ----------------------------------------------------------------------------

function AnalyseAllDialog({ item, token, engine, count, onClose, onStarted }: { item: SceneSet; token: string; engine: string; count: number; onClose: () => void; onStarted: (text: string, problem?: string) => void }) {
  const apiEngines = useApiEngines()
  const [model, setModel] = useState<string | null>(null)
  const [average, setAverage] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const charged = isApiEngine(engine)
  const name = engineNames[engine] ?? engine
  const parts = Math.ceil(count / MAX_ANALYSIS_RUNS)
  useEffect(() => {
    request<{ analysis: Record<string, number | null> }>('/api/batches/timing').then(t => setAverage(t.analysis[engine] ?? null), () => setAverage(null))
    if (charged) request<{ models: Record<string, { analysis?: string }> }>('/api/engines/settings').then(s => setModel(s.models[engine]?.analysis ?? null), () => undefined)
  }, [engine, charged])
  async function start() {
    setBusy(true); setError('')
    try {
      const result = await send<{ batches: Batch[]; queued: number; skipped: Skipped[] }>(`/api/scene-sets/${item.id}/analyse-all`, 'POST', token, charged ? { confirm_charges: true } : {})
      onStarted(`Analysing ${plural(result.queued, 'scene')} in ${plural(result.batches.length, 'batch')}, one run at a time.`, result.skipped.length ? `Skipped: ${result.skipped.map(s => `${s.title} (${s.reason})`).join(', ')}.` : undefined)
    } catch (e) { setError(e instanceof Error ? e.message : 'Analyse all could not be started.'); setBusy(false) }
  }
  return <Dialog label="analyse-all-title" onClose={onClose}>
    <div className="text-dialog-form">
      <h2 id="analyse-all-title">Analyse {plural(count, 'scene')} with {name}</h2>
      <p className="hint">Every scene in “{item.name}” that has no analysis is queued. Scenes that already have one are left alone.</p>
      {engine === 'manual' ? <p className="notice-line">Manual analysis is selected in Studio settings, so nothing can be queued. Choose an engine there first.</p> : <>
        {charged && apiEngines.byId[engine] && <ChargeSummary engine={apiEngines.byId[engine]} model={model} runs={count} />}
        <div className="check-box batch-summary">
          <strong>{plural(count, 'run')} from {charged ? `your ${name} key (charged per use)` : `your ${name} plan’s allowance`}</strong>
          <ul>
            <li>Each run sends one Base Image to {sendsTo[engine]}{charged ? '' : ', using your own sign-in'}.</li>
            <li>{parts > 1 ? `The studio splits them into ${parts} batches of at most ${MAX_ANALYSIS_RUNS} and runs` : 'The studio runs them as one batch,'} them one after another, never at the same time{average ? `: about ${duration(average * count)} in all, going by earlier runs on this computer` : ''}.</li>
            <li><b>A long run can use up {charged ? 'your key’s limits' : 'your plan’s allowance'} and stop partway.</b> If a limit or a sign-out stops it, every batch pauses, the finished analyses are kept, and nothing continues until you click Continue.</li>
            <li>A failed scene is marked Failed and the next one starts. Nothing is retried on its own.</li>
          </ul>
        </div></>}
      {error && <p className="frame-error" role="alert">{error}</p>}
      <div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Cancel</button>
        <button type="button" disabled={busy || engine === 'manual' || !count} onClick={() => void start()}>{busy ? 'Starting…' : `Analyse ${plural(count, 'scene')}${charged ? ' and accept charges' : ''}`}</button></div>
    </div>
  </Dialog>
}

// Assign table ----------------------------------------------------------------------------

type Person = { label: string; bounding_box: { x: number; y: number; width: number; height: number }; summary: string; action: 'replace' | 'keep' | 'unresolved'; character_id: string | null; confirmed: boolean }
type Row = { scene_id: string; title: string; revision: number; thumbnail_url: string; stage: string; locked: string | null; mismatch: string | null; group_id: string | null; people: Person[] }
type Proposal = { scene_id: string; mappings: { label: string; action: 'replace' | 'keep'; character_id: string | null }[]; intended: number | null }
type Edit = { choices: Record<string, string>; intended: number | null }

// What a person's pick box holds: '' = undecided, 'keep' = original look, otherwise a character id.
const choiceOf = (p: Person) => p.action === 'replace' ? p.character_id ?? '' : p.action === 'keep' ? 'keep' : ''
const noteFor = (people: number, intended: number | null) => intended == null ? null : people === 0 ? 'No people found' : people === intended ? null : `Mismatch: ${people} ${people === 1 ? 'person' : 'people'}, ${intended} ${intended === 1 ? 'character' : 'characters'}`

function AssignTable({ item, token, onClose, onNotice }: { item: SceneSet; token: string; onClose: () => void; onNotice: (text: string, problem?: string) => void }) {
  const [rows, setRows] = useState<Row[] | null>(null)
  const [waiting, setWaiting] = useState(0)
  const [characters, setCharacters] = useState<Character[]>([])
  const [groups, setGroups] = useState<Group[]>([])
  const [edits, setEdits] = useState<Record<string, Edit>>({})
  const [rule, setRule] = useState<'one' | 'group'>('one')
  const [oneId, setOneId] = useState('')
  const [groupId, setGroupId] = useState('')
  const [order, setOrder] = useState<string[]>([])
  const [largest, setLargest] = useState(false)
  const [onlyEmpty, setOnlyEmpty] = useState(true)
  const [onlyOpen, setOnlyOpen] = useState(false)
  const [skipped, setSkipped] = useState<Skipped[]>([])
  const [filled, setFilled] = useState('')
  const [failed, setFailed] = useState<Skipped[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const load = useCallback(() => Promise.all([
    request<{ rows: Row[]; not_analysed: number }>(`/api/scene-sets/${item.id}/assign`), request<Character[]>('/api/characters'), request<Group[]>('/api/groups'),
  ]).then(([table, c, g]) => { setRows(table.rows); setWaiting(table.not_analysed); setCharacters(c); setGroups(g) }, e => setError(e instanceof Error ? e.message : 'The table could not be loaded.')), [item.id])
  useEffect(() => { void load() }, [load])
  const usable = useMemo(() => characters.filter(c => !c.archived && c.photos.length > 0), [characters])
  const byId = useMemo(() => Object.fromEntries(characters.map(c => [c.id, c])), [characters])
  useEffect(() => { if (!oneId && usable[0]) setOneId(usable[0].id) }, [usable, oneId])
  useEffect(() => { if (!groupId && groups[0]) { setGroupId(groups[0].id); setOrder(groups[0].member_ids) } }, [groups, groupId])
  const people = order.filter(id => byId[id])
  const moveInOrder = (index: number, by: number) => setOrder(o => { const next = [...o]; [next[index], next[index + by]] = [next[index + by], next[index]]; return next })

  const choicesOf = (row: Row) => edits[row.scene_id]?.choices ?? Object.fromEntries(row.people.map(p => [p.label, choiceOf(p)]))
  const setChoice = (row: Row, label: string, value: string) => setEdits(e => ({ ...e, [row.scene_id]: { choices: { ...choicesOf(row), [label]: value }, intended: null } }))
  const duplicates = (row: Row) => { const seen = new Set<string>(); for (const id of Object.values(choicesOf(row))) { if (id && id !== 'keep') { if (seen.has(id)) return true; seen.add(id) } } return false }
  const mismatchOf = (row: Row) => edits[row.scene_id] ? noteFor(row.people.length, edits[row.scene_id].intended) : row.mismatch
  const dirty = rows?.filter(r => edits[r.scene_id] && !r.locked) ?? []
  const clash = dirty.some(duplicates)

  async function fill() {
    setBusy(true); setError(''); setFilled(''); setSkipped([])
    try {
      const body = rule === 'one' ? { rule, character_id: oneId, several_people: largest ? 'largest' : 'skip', only_empty: onlyEmpty } : { rule, group_id: groupId || null, order: people, only_empty: onlyEmpty }
      const result = await send<{ proposals: Proposal[]; skipped: Skipped[] }>(`/api/scene-sets/${item.id}/assign/fill`, 'POST', token, body)
      setEdits(old => {
        const next = { ...old }
        for (const p of result.proposals) next[p.scene_id] = { choices: Object.fromEntries(p.mappings.map(m => [m.label, m.action === 'keep' ? 'keep' : m.character_id ?? ''])), intended: p.intended }
        return next
      })
      setSkipped(result.skipped)
      setFilled(`${plural(result.proposals.length, 'row')} filled. Check them, change any by hand, then save the table.`)
    } catch (e) { setError(e instanceof Error ? e.message : 'The rows could not be filled.') }
    finally { setBusy(false) }
  }
  async function save() {
    if (!rows) return
    setBusy(true); setError(''); setFailed([])
    try {
      const body = { rows: dirty.map(r => ({ scene_id: r.scene_id, revision: r.revision, group_id: rule === 'group' ? groupId || null : null, intended: edits[r.scene_id].intended,
        mappings: r.people.map(p => { const pick = choicesOf(r)[p.label]; return pick === 'keep' ? { label: p.label, action: 'keep' } : pick ? { label: p.label, action: 'replace', character_id: pick } : { label: p.label, action: 'unresolved' } }) })) }
      const result = await send<{ saved: Skipped[]; failed: Skipped[] }>(`/api/scene-sets/${item.id}/assign`, 'PUT', token, body)
      setFailed(result.failed)
      setEdits(old => Object.fromEntries(Object.entries(old).filter(([id]) => result.failed.some(f => f.scene_id === id))))
      if (result.saved.length) onNotice(`Assignments saved for ${plural(result.saved.length, 'scene')}. Saving the table confirms them.`)
      await load()
    } catch (e) { setError(e instanceof Error ? e.message : 'The table could not be saved.') }
    finally { setBusy(false) }
  }
  const shown = (rows ?? []).filter(r => !onlyOpen || r.people.some(p => !choicesOf(r)[p.label]))
  return <Dialog label="assign-title" className="assign-dialog" onClose={onClose}>
    <div className="text-dialog-form">
      <h2 id="assign-title">Assign characters · {item.name}</h2>
      <p className="hint">One row per analysed scene. Use a fill rule, then change any row by hand. Saving the table <b>confirms</b> the assignments, so the scenes can go straight to a prompt. Nothing is sent anywhere and nothing is approved.</p>
      <fieldset className="assign-fill" disabled={busy}>
        <legend className="visually-hidden">Fill rule</legend>
        <div className="fill-head"><span className="fill-title">Fill rule</span>
          <div className="segmented" role="radiogroup" aria-label="Fill rule">
            <label className={`segment ${rule === 'one' ? 'selected' : ''}`}><input type="radio" name="fill-rule" checked={rule === 'one'} onChange={() => setRule('one')} />One character</label>
            <label className={`segment ${rule === 'group' ? 'selected' : ''}`}><input type="radio" name="fill-rule" checked={rule === 'group'} onChange={() => setRule('group')} />A group, left to right</label>
          </div></div>
        {rule === 'one' ? <div className="fill-field"><label htmlFor="fill-character">Character for every one-person scene</label>
          <select id="fill-character" value={oneId} onChange={e => setOneId(e.target.value)}>{usable.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
          : !groups.length ? <p className="notice-line">No groups yet. Create one on the Characters page.</p> : <div className="fill-field">
            <label htmlFor="fill-group">Group</label>
            <select id="fill-group" value={groupId} onChange={e => { setGroupId(e.target.value); setOrder(groups.find(g => g.id === e.target.value)?.member_ids ?? []) }}>{groups.map(g => <option key={g.id} value={g.id}>{g.name} ({g.member_ids.length})</option>)}</select>
            <ol className="order-list" aria-label="Characters from left to right">{people.map((id, index) => <li key={id} className={usable.some(c => c.id === id) ? '' : 'unavailable'}>
              <span className="order-number">{index + 1}</span><Avatar character={byId[id]} size="mini" /><span className="order-name">{byId[id].name}{!usable.some(c => c.id === id) && <small> · {byId[id].archived ? 'archived' : 'no photos'}</small>}</span>
              <button type="button" className="secondary compact icon-only" aria-label={`Move ${byId[id].name} left`} disabled={index === 0} onClick={() => moveInOrder(index, -1)}>↑</button>
              <button type="button" className="secondary compact icon-only" aria-label={`Move ${byId[id].name} right`} disabled={index === people.length - 1} onClick={() => moveInOrder(index, 1)}>↓</button></li>)}</ol></div>}
        <div className="fill-options">
          {rule === 'one' && <label className="option-line"><input type="checkbox" checked={largest} onChange={e => setLargest(e.target.checked)} /><span><b>Scenes with several people</b><small>Give the character to the largest person. The others keep their original look and the scene is labelled.</small></span></label>}
          <label className="option-line"><input type="checkbox" checked={onlyEmpty} onChange={e => setOnlyEmpty(e.target.checked)} /><span><b>Only rows nobody is assigned in yet</b><small>Untick to replace what rows already have.</small></span></label>
        </div>
        <div className="fill-action"><button type="button" disabled={!rows?.length || (rule === 'one' ? !oneId : !people.length)} onClick={() => void fill()}>Fill rows</button></div>
      </fieldset>
      {filled && <p className="ok-line" role="status">{filled}</p>}
      <SkippedList items={skipped} heading={`${plural(skipped.length, 'row')} left as they were`} />
      {error && <p className="frame-error" role="alert">{error}</p>}
      {rows === null && !error ? <p role="status">Loading the table…</p> : !rows?.length ? <p className="notice-line">No scene in this set has an analysis yet. Run Analyse all first.</p> : <>
        <div className="assign-toolbar"><span className="hint">{plural(rows.length, 'scene')}{waiting ? ` · ${waiting} not analysed yet` : ''}</span>
          <label className="checkbox-label"><input type="checkbox" checked={onlyOpen} onChange={e => setOnlyOpen(e.target.checked)} /><span>Only rows with someone undecided</span></label></div>
        <div className="assign-columns" aria-hidden="true"><span>Scene</span><span>People and characters</span></div>
        <ul className="assign-rows">{shown.map(row => {
          const note = mismatchOf(row)
          return <li key={row.scene_id} className={`${row.locked ? 'locked' : ''} ${edits[row.scene_id] && !row.locked ? 'changed' : ''}`}>
            <img src={row.thumbnail_url} alt="" loading="lazy" />
            <div className="assign-title"><strong>{row.title}</strong>
              <span className="assign-tags">{row.people.length === 0 ? <span className="tag warn">No people found</span> : <span className="tag">{row.people.length === 1 ? '1 person' : `${row.people.length} people`}</span>}
                {note && row.people.length > 0 && <span className="tag warn">{note}</span>}
                {edits[row.scene_id] && !row.locked && <span className="tag">Changed</span>}</span>
              {row.locked && <small className="hint">{row.locked}</small>}
              {!row.locked && duplicates(row) && <small className="frame-error">A character can appear only once in a scene.</small>}</div>
            <div className="assign-people">{row.people.map(p => <label key={p.label} className="assign-person"><span>{p.label}<small>{p.summary}</small></span>
              <select aria-label={`${row.title}: ${p.label}`} value={choicesOf(row)[p.label] ?? ''} disabled={!!row.locked || busy} onChange={e => setChoice(row, p.label, e.target.value)}>
                <option value="">Choose…</option><option value="keep">Keep original look</option>
                {usable.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                {characters.filter(c => !usable.includes(c) && Object.values(choicesOf(row)).includes(c.id)).map(c => <option key={c.id} value={c.id}>{c.name} (unavailable)</option>)}
              </select></label>)}
              {row.people.length === 0 && <span className="hint">Nothing to assign.</span>}</div>
          </li>
        })}</ul>
        {onlyOpen && !shown.length && <p className="ok-line">Everyone is decided in every row.</p>}
      </>}
      <SkippedList items={failed} heading={`${plural(failed.length, 'row')} could not be saved`} />
      <div className="dialog-actions"><span className="spacer hint" role="status">{dirty.length ? `${plural(dirty.length, 'row')} changed, not saved yet` : ''}</span>
        <button type="button" className="secondary" disabled={busy} onClick={() => { if (!dirty.length || window.confirm('Close without saving the changed rows?')) onClose() }}>Close</button>
        <button type="button" disabled={busy || !dirty.length || clash} onClick={() => void save()}>{busy ? 'Saving…' : `Save ${plural(dirty.length, 'row')}`}</button></div>
    </div>
  </Dialog>
}

// Draft prompts for all --------------------------------------------------------------------

function DraftDialog({ item, token, ready, again, onClose, onNotice }: { item: SceneSet; token: string; ready: number; again: number; onClose: () => void; onNotice: (text: string, problem?: string) => void }) {
  const { presets } = usePresets()
  const [presetId, setPresetId] = useState('')
  const [replace, setReplace] = useState(ready === 0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<{ drafted: { scene_id: string; title: string; version: number }[]; skipped: Skipped[]; preset: string | null } | null>(null)
  const count = ready + (replace ? again : 0)
  async function start() {
    setBusy(true); setError('')
    try {
      const r = await send<NonNullable<typeof result>>(`/api/scene-sets/${item.id}/draft-prompts`, 'POST', token, { ...(presetId ? { preset_id: presetId } : {}), replace_existing: replace })
      setResult(r)
      onNotice(r.drafted.length ? `Drafted ${plural(r.drafted.length, 'prompt')}${r.preset ? ` with “${r.preset}”` : ''}. Each is a saved version; nothing is approved.` : 'No prompts were drafted.')
    } catch (e) { setError(e instanceof Error ? e.message : 'The prompts could not be drafted.') }
    finally { setBusy(false) }
  }
  return <Dialog label="draft-title" onClose={onClose}>
    <div className="text-dialog-form">
      <h2 id="draft-title">Draft prompts for “{item.name}”</h2>
      {result ? <>
        <p className="ok-line" role="status">{plural(result.drafted.length, 'prompt')} drafted{result.preset ? ` with “${result.preset}”` : ''}.</p>
        <SkippedList items={result.skipped} heading={`${plural(result.skipped.length, 'scene')} left alone`} />
        <div className="dialog-actions"><button type="button" onClick={onClose}>Done</button></div>
      </> : <>
        <p className="hint">The studio writes each scene’s prompt from its own template, the analysis and the assignments, and saves it as the next prompt version. No engine runs and nothing is sent anywhere. A scene needs a finished analysis with nothing uncertain and every person assigned; approved scenes are never changed.</p>
        <PresetSelect id="draft-preset" presets={presets} value={presetId} disabled={busy} label="Preset (optional)" onChange={p => setPresetId(p?.id ?? '')} />
        <p className="hint preset-bar-note">A preset fills Scene changes and adds its lines to every negative prompt.</p>
        {again > 0 && <label className="checkbox-label"><input type="checkbox" checked={replace} disabled={busy} onChange={e => setReplace(e.target.checked)} /><span>Also write a new version for the {plural(again, 'scene')} that already {again === 1 ? 'has' : 'have'} a current saved prompt (earlier versions are kept)</span></label>}
        <p><b>{plural(count, 'scene')}</b> will get a new draft.</p>
        {error && <p className="frame-error" role="alert">{error}</p>}
        <div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Cancel</button><button type="button" disabled={busy || !count} onClick={() => void start()}>{busy ? 'Drafting…' : `Draft ${plural(count, 'prompt')}`}</button></div>
      </>}
    </div>
  </Dialog>
}

// Polish all and its review -----------------------------------------------------------------

function PolishDialog({ item, token, count, onClose, onStarted }: { item: SceneSet; token: string; count: number; onClose: () => void; onStarted: (text: string) => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function start() {
    setBusy(true); setError('')
    try { const r = await send<{ queued: number }>(`/api/scene-sets/${item.id}/polish-all`, 'POST', token); onStarted(`Polishing ${plural(r.queued, 'prompt')}, one after another. Review the results when they finish.`) }
    catch (e) { setError(e instanceof Error ? e.message : 'Polish all could not be started.'); setBusy(false) }
  }
  return <Dialog label="polish-all-title" onClose={onClose}>
    <div className="text-dialog-form">
      <h2 id="polish-all-title">Polish {plural(count, 'prompt')}? <small className="tag">Optional</small></h2>
      <p className="hint">Polish asks Claude to make a saved prompt read more clearly without adding or dropping anything. It is off by default because it is <b>one Claude run per scene</b>.</p>
      <div className="check-box batch-summary"><strong>{plural(count, 'run')} from your Claude plan’s allowance</strong><ul>
        <li>Each run sends one prompt’s text and its analysis to Anthropic via Claude Code, never your photos.</li>
        <li>They run one after another. A plan limit or sign-out makes the remaining runs fail; nothing is retried on its own, and you can cancel the ones that have not started.</li>
        <li>Nothing changes until you choose: the results wait in a review list.</li></ul></div>
      {error && <p className="frame-error" role="alert">{error}</p>}
      <div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Cancel</button><button type="button" disabled={busy} onClick={() => void start()}>{busy ? 'Starting…' : `Polish ${plural(count, 'prompt')}`}</button></div>
    </div>
  </Dialog>
}

type ReviewRow = { scene_id: string; title: string; thumbnail_url: string; job_id: string; prompt_version: number; current_text: string; polished_text: string; missing: string[] }

function PolishReview({ item, token, onClose, onNotice }: { item: SceneSet; token: string; onClose: () => void; onNotice: (text: string, problem?: string) => void }) {
  const [rows, setRows] = useState<ReviewRow[] | null>(null)
  const [choice, setChoice] = useState<Record<string, 'use' | 'keep'>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [failed, setFailed] = useState<Skipped[]>([])
  const load = useCallback(() => request<{ rows: ReviewRow[] }>(`/api/scene-sets/${item.id}/polish-review`).then(r => setRows(r.rows), e => setError(e.message)), [item.id])
  useEffect(() => { void load() }, [load])
  const decided = Object.keys(choice).length
  async function apply() {
    setBusy(true); setError(''); setFailed([])
    try {
      const body = { decisions: (rows ?? []).filter(r => choice[r.scene_id]).map(r => ({ scene_id: r.scene_id, job_id: r.job_id, decision: choice[r.scene_id] })) }
      const result = await send<{ done: { decision: string }[]; failed: (Skipped)[] }>(`/api/scene-sets/${item.id}/polish-review`, 'POST', token, body)
      setFailed(result.failed); setChoice({})
      const used = result.done.filter(d => d.decision === 'use').length
      onNotice(`${plural(used, 'polished prompt')} used, ${plural(result.done.length - used, 'original')} kept.`)
      await load()
    } catch (e) { setError(e instanceof Error ? e.message : 'The choices could not be applied.') }
    finally { setBusy(false) }
  }
  const useAll = () => setChoice(Object.fromEntries((rows ?? []).map(r => [r.scene_id, r.missing.length ? 'keep' : 'use'] as const)))
  return <Dialog label="review-title" className="assign-dialog" onClose={onClose}>
    <div className="text-dialog-form">
      <h2 id="review-title">Polished prompts · {item.name}</h2>
      <p className="hint">Compare each polished prompt with the one you have. Nothing changes until you apply your choices. A polished prompt that lost required elements (marked ⚠) is never used by “Use all polished”; open that scene to fix it by hand.</p>
      {error && <p className="frame-error" role="alert">{error}</p>}
      {rows === null ? <p role="status">Loading…</p> : !rows.length ? <p className="ok-line">Nothing is waiting for review.</p> : <>
        <div className="assign-toolbar"><span className="hint">{plural(rows.length, 'prompt')} to review</span>
          <span className="row-actions"><button type="button" className="secondary compact" disabled={busy} onClick={useAll}>Use all polished</button>
            <button type="button" className="secondary compact" disabled={busy} onClick={() => setChoice(Object.fromEntries(rows.map(r => [r.scene_id, 'keep'] as const)))}>Keep all originals</button>
            <button type="button" className="link-button" disabled={busy || !decided} onClick={() => setChoice({})}>Clear choices</button></span></div>
        <ul className="assign-rows polish-rows">{rows.map(row => <li key={row.scene_id}>
          <img src={row.thumbnail_url} alt="" loading="lazy" />
          <div className="assign-title"><strong>{row.title}</strong><small className="hint">Compared with version {row.prompt_version}</small>
            {row.missing.length > 0 && <span className="tag warn" title={row.missing.join(' ')}>⚠ Lost required elements</span>}
            <details className="polish-compare"><summary>Show both texts</summary>
              <div className="polish-columns"><div><b>Your prompt</b><pre>{row.current_text}</pre></div><div><b>Polished</b><pre>{row.polished_text}</pre></div></div>
              {row.missing.length > 0 && <ul className="hint">{row.missing.map(m => <li key={m}>{m}</li>)}</ul>}</details></div>
          <div className="segmented" role="radiogroup" aria-label={`Decision for ${row.title}`}>
            {([['use', 'Use polished'], ['keep', 'Keep original']] as const).map(([id, label]) => <label key={id} className={`segment ${choice[row.scene_id] === id ? 'selected' : ''}`}>
              <input type="radio" name={`polish-${row.scene_id}`} checked={choice[row.scene_id] === id} disabled={busy || (id === 'use' && row.missing.length > 0)} onChange={() => setChoice(c => ({ ...c, [row.scene_id]: id }))} />{label}</label>)}</div>
        </li>)}</ul></>}
      <SkippedList items={failed} heading={`${plural(failed.length, 'prompt')} could not be changed`} />
      <div className="dialog-actions"><span className="spacer hint">{decided ? `${plural(decided, 'choice')} not applied yet` : 'Undecided prompts stay as they are.'}</span>
        <button type="button" className="secondary" disabled={busy} onClick={onClose}>Close</button>
        <button type="button" disabled={busy || !decided} onClick={() => void apply()}>{busy ? 'Applying…' : `Apply ${plural(decided, 'choice')}`}</button></div>
    </div>
  </Dialog>
}
