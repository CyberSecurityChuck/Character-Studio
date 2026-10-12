import { useCallback, useEffect, useRef, useState } from 'react'
import { request, send } from './api'
import { ChargeSummary, engineNames, isApiEngine, sendsTo, useApiEngines } from './ApiEngines'
import { PresetSelect, usePresets } from './Presets'
import { Avatar, type Character, type Group } from './Library'
import { duration } from './Results'
import type { SceneSummary } from './Scenes'

export type BatchItem = { job_id: string; position: number; scene_id: string; scene_title: string | null; thumbnail_url: string; status: string; mode: string | null; retry_of: string | null; error_kind: string | null; error_details: string | null; result_id: string | null; result_version: number | null; seconds: number | null; started_at: string | null }
export type Batch = {
  id: string; kind: 'analysis' | 'generation'; engine: string; engine_name: string; status: string
  state: 'running' | 'pausing' | 'paused' | 'cancelling' | 'cancelled' | 'finished'
  pause_kind: string | null; pause_details: string | null; settings: { count?: number; mode?: string }
  created_at: string; updated_at: string; counts: Record<'not_started' | 'running' | 'completed' | 'failed' | 'cancelled' | 'interrupted', number>
  total: number; scene_count: number; retryable: number; average_seconds: number | null; estimate_seconds: number | null; items: BatchItem[]
}
type Skipped = { scene_id: string; title: string; reason: string }
export type BatchStart = { batch: Batch; skipped: Skipped[] }

// Batch sizes the server accepts (backend/batches.py).
export const MAX_ANALYSIS_RUNS = 50
export const MAX_GENERATION_RUNS = 20
const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`
const formatDate = (value: string) => new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
const allowance: Record<string, string> = { claude_cli: 'your Claude plan’s allowance', codex_cli: 'your ChatGPT plan’s allowance', gemini_api: 'your Google API key (may be charged)', anthropic_api: 'your Anthropic API key (charged per use)', openai_api: 'your OpenAI API key (charged per use)' }
const stateLabels: Record<Batch['state'], string> = { running: 'Running', pausing: 'Pausing after this run', paused: 'Paused', cancelling: 'Stopping', cancelled: 'Cancelled', finished: 'Finished' }
const itemLabels: Record<string, string> = { not_started: 'Not started', running: 'Running', completed: 'Done', failed: 'Failed', cancelled: 'Cancelled', interrupted: 'Interrupted' }
const pauseTitles: Record<string, (name: string, engine: string) => string> = {
  user: () => 'Paused by you',
  usage_limit: (name, engine) => isApiEngine(engine) ? `Paused: ${name} reports a rate, quota or spending limit` : `Paused: ${name}’s plan limit appears to be reached`,
  key_problem: engine => `Paused: ${engine} did not accept the key`,
  model_problem: engine => `Paused: ${engine} does not offer the chosen model`,
  signed_out: engine => `Paused: ${engine} is signed out`,
  not_installed: engine => `Paused: ${engine} could not be started`,
  restart: () => 'Paused when the studio stopped',
}
export const isActive = (batch: Batch) => !['finished', 'cancelled'].includes(batch.state)
const approvedStates = ['approved', 'generated']

function BatchCard({ batch, token, collapsed, onChanged, onOpenScene }: { batch: Batch; token: string; collapsed?: boolean; onChanged: () => void; onOpenScene?: (id: string, step: string) => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const { counts } = batch
  const remaining = counts.not_started
  const problems = counts.failed + counts.interrupted
  const what = batch.kind === 'generation' ? 'image' : 'analysis'
  const runs = (n: number) => batch.kind === 'generation' ? plural(n, 'image') : `${n} ${n === 1 ? 'analysis' : 'analyses'}`
  // API engines: continuing or retrying may be charged, so the server needs the confirmation.
  const charged = isApiEngine(batch.engine)
  const chargeLine = charged ? ' Each run may be charged to your account by the provider; nothing is retried on its own.' : ''
  async function act(path: string, method = 'POST', question?: string) {
    if (question && !window.confirm(question)) return
    setBusy(true); setError('')
    try { await send(`/api/batches/${batch.id}${path}`, method, token, charged && ['/continue', '/retry'].includes(path) ? { confirm_charges: true } : undefined); onChanged() }
    catch (e) { setError(e instanceof Error ? e.message : 'That did not work. Reload and try again.') }
    finally { setBusy(false) }
  }
  async function cancelRun(item: BatchItem) {
    if (!window.confirm(`Cancel the ${what} that is running for “${item.scene_title}”? It may already have used some allowance.`)) return
    setBusy(true); setError('')
    try { await send(`/api/jobs/${item.job_id}/cancel`, 'POST', token); onChanged() }
    catch (e) { setError(e instanceof Error ? e.message : 'The run could not be cancelled.') }
    finally { setBusy(false) }
  }
  const share = (n: number) => `${(n / Math.max(1, batch.total)) * 100}%`
  const step = batch.kind === 'generation' ? 'generate' : 'analysis'
  const retriedAs = Object.fromEntries(batch.items.filter(i => i.retry_of).map(i => [i.retry_of, i.position]))
  return <article className={`batch-card ${batch.state}`} aria-label={`${batch.kind === 'generation' ? 'Generation' : 'Analysis'} batch`}>
    <div className="batch-head">
      <div><strong>{batch.kind === 'generation' ? `Generate ${runs(batch.total)}` : `Analyse ${plural(batch.total, 'scene')}`}</strong>
        <span className="hint"> · {batch.engine_name} · {batch.kind === 'generation' && batch.scene_count > 1 ? `${plural(batch.scene_count, 'scene')} · ` : ''}{batch.settings.mode === 'variation' ? 'variations · ' : ''}started {formatDate(batch.created_at)}</span></div>
      <span className={`batch-state ${batch.state}`}>{stateLabels[batch.state]}</span>
    </div>
    <div className="batch-bar" role="img" aria-label={`${counts.completed} done, ${problems} failed or interrupted, ${counts.cancelled} cancelled, ${remaining + counts.running} not finished, of ${batch.total}`}>
      <span className="done" style={{ width: share(counts.completed) }} />
      <span className="failed" style={{ width: share(problems) }} />
      <span className="cancelled" style={{ width: share(counts.cancelled) }} />
      <span className="running" style={{ width: share(counts.running) }} />
    </div>
    <p className="batch-counts">
      <span><b>{counts.completed}</b> of {batch.total} done</span>
      {problems > 0 && <span className="bad"><b>{problems}</b> {counts.interrupted && !counts.failed ? 'interrupted' : 'failed'}</span>}
      {counts.cancelled > 0 && <span><b>{counts.cancelled}</b> cancelled</span>}
      {remaining > 0 && <span><b>{remaining}</b> not started</span>}
      {batch.state === 'running' && batch.estimate_seconds != null && <span className="hint">about {duration(batch.estimate_seconds + (counts.running ? batch.average_seconds ?? 0 : 0))} left</span>}
    </p>
    {batch.state === 'paused' && batch.pause_kind && <div className="check-box warning batch-paused">
      <strong>{(pauseTitles[batch.pause_kind] ?? pauseTitles.user)(engineNames[batch.engine] ?? batch.engine_name, batch.engine)}</strong>
      {batch.pause_details && <p>{batch.pause_details}</p>}
      <p>{plural(remaining, 'item')} {remaining === 1 ? 'is' : 'are'} waiting. Nothing continues on its own{batch.pause_kind === 'usage_limit' ? '; wait until your limit resets, then continue' : batch.pause_kind === 'signed_out' ? '; sign in again, then continue' : batch.pause_kind === 'key_problem' || batch.pause_kind === 'model_problem' ? '; check the key and model in Studio settings, then continue' : ''}.</p>
    </div>}
    {batch.state === 'pausing' && <p className="hint">The run in progress finishes first; nothing new starts after it.</p>}
    {error && <p className="frame-error" role="alert">{error}</p>}
    <div className="batch-actions">
      {batch.state === 'running' && <button type="button" className="secondary compact" disabled={busy} onClick={() => void act('/pause')}>Pause</button>}
      {batch.state === 'paused' && <button type="button" className="compact" disabled={busy}
        onClick={() => void act('/continue', 'POST', `Continue the batch? ${runs(remaining)} ${remaining === 1 ? 'runs' : 'run'} one after another, using ${allowance[batch.engine]}.${chargeLine}`)}>Continue</button>}
      {['running', 'pausing', 'paused'].includes(batch.state) && remaining > 0 && <button type="button" className="danger secondary compact" disabled={busy}
        onClick={() => void act('/cancel', 'POST', `Cancel the ${plural(remaining, 'item')} that ${remaining === 1 ? 'has' : 'have'} not started? Nothing is sent for them.${counts.running ? ' The run in progress continues; you can cancel it in the list below.' : ''}`)}>Cancel remaining</button>}
      {!isActive(batch) && batch.retryable > 0 && <button type="button" className="secondary compact" disabled={busy}
        onClick={() => void act('/retry', 'POST', `Try the ${plural(batch.retryable, 'failed item')} again? This starts ${plural(batch.retryable, 'new run')}, using ${allowance[batch.engine]}. Earlier attempts and results are kept.${chargeLine}`)}>Try failed again ({batch.retryable})</button>}
      {!isActive(batch) && <button type="button" className="link-button" disabled={busy} onClick={() => void act('', 'DELETE')}>Remove from list</button>}
    </div>
    <details className="batch-items" open={!collapsed && isActive(batch) && batch.total <= 6}>
      <summary>Items ({batch.total})</summary>
      <ol>{batch.items.map(item => <li key={item.job_id} className={item.status}>
        <img src={item.thumbnail_url} alt="" loading="lazy" />
        <div className="batch-item-copy">
          {onOpenScene && item.scene_title ? <button type="button" className="link-button" onClick={() => onOpenScene(item.scene_id, step)}>{item.scene_title}</button> : <strong>{item.scene_title ?? 'Deleted scene'}</strong>}
          <span className="hint">{item.retry_of ? 'Tried again · ' : ''}{batch.kind === 'generation' ? (item.mode === 'variation' ? 'Variation' : 'Image') : 'Analysis'}{item.result_version ? ` · Result ${item.result_version}` : ''}{item.seconds != null && item.status === 'completed' ? ` · ${duration(item.seconds)}` : ''}</span>
          {item.error_details && item.status !== 'cancelled' && <span className="batch-item-error">{item.error_details}</span>}
          {item.status === 'failed' && retriedAs[item.job_id] && <span className="hint">Tried again as item {retriedAs[item.job_id]}</span>}
          {item.status === 'interrupted' && batch.kind === 'generation' && <span className="hint">Open the scene to look for a saved image before generating again.</span>}
        </div>
        <span className={`run-status ${item.status}`}>{itemLabels[item.status] ?? item.status}</span>
        {item.status === 'running' && <button type="button" className="link-button" disabled={busy} onClick={() => void cancelRun(item)}>Cancel run</button>}
      </li>)}</ol>
    </details>
  </article>
}

/** Batches from the server, refreshed while any of them is running. */
export function BatchList({ token, sceneId, activeOnly, refreshKey, title = 'Batches', onOpenScene, onProgress }: {
  token: string; sceneId?: string; activeOnly?: boolean; refreshKey?: number; title?: string
  onOpenScene?: (id: string, step: string) => void; onProgress?: () => void
}) {
  const [batches, setBatches] = useState<Batch[]>([])
  const progress = useRef('')
  const load = useCallback(() => request<Batch[]>('/api/batches').then(list => {
    setBatches(list)
    // Tell the page when an item finishes, so its cards and stages catch up.
    const signature = list.map(b => `${b.id}:${b.counts.completed + b.counts.failed + b.counts.cancelled + b.counts.interrupted}:${b.state}`).join('|')
    if (progress.current && signature !== progress.current) onProgress?.()
    progress.current = signature
  }, () => undefined), [onProgress])
  useEffect(() => { void load() }, [load, refreshKey])
  const shown = batches.filter(b => (!sceneId || b.items.some(i => i.scene_id === sceneId)) && (!(activeOnly || sceneId) || isActive(b)))
  const moving = shown.some(b => ['running', 'pausing', 'cancelling'].includes(b.state))
  useEffect(() => {
    if (!moving) return
    const timer = window.setInterval(() => void load(), 2000)
    return () => window.clearInterval(timer)
  }, [moving, load])
  if (!shown.length) return null
  const active = shown.filter(isActive)
  const done = shown.filter(b => !isActive(b))
  return <section className="batch-list" aria-label={title}>
    {!sceneId && <div className="section-title"><h2>{title}</h2>{active.length > 0 && <span>ONE RUN AT A TIME</span>}</div>}
    {active.map(b => <BatchCard key={b.id} batch={b} token={token} collapsed={!!sceneId} onChanged={() => void load()} onOpenScene={onOpenScene} />)}
    {done.length > 0 && <details className="batch-history"><summary>Finished batches ({done.length})</summary>
      {done.map(b => <BatchCard key={b.id} batch={b} token={token} onChanged={() => void load()} onOpenScene={onOpenScene} />)}
    </details>}
  </section>
}

function Dialog({ label, className = '', children, onClose }: { label: string; className?: string; children: React.ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => { ref.current?.showModal() }, [])
  return <dialog ref={ref} className={`image-dialog text-dialog batch-dialog ${className}`} aria-labelledby={label} onClose={onClose}>{children}</dialog>
}

function SkippedList({ items }: { items: { title: string; reason: string }[] }) {
  if (!items.length) return null
  return <div className="check-box warning"><strong>{plural(items.length, 'scene')} will be skipped</strong>
    <ul>{items.slice(0, 8).map(s => <li key={s.title + s.reason}><b>{s.title}</b>: {s.reason}</li>)}{items.length > 8 && <li>and {items.length - 8} more</li>}</ul></div>
}

/** Confirm a batch before anything is queued: how many runs, which allowance, what is skipped. */
export function BatchDialog({ kind, scenes, preselectAll, engine, token, onClose, onStarted }: {
  kind: 'analysis' | 'generation'; scenes: SceneSummary[]; preselectAll?: boolean; engine: string; token: string
  onClose: () => void; onStarted: (result: BatchStart) => void
}) {
  const [includeAnalysed, setIncludeAnalysed] = useState(false)
  const [count, setCount] = useState(1)
  const [mode, setMode] = useState<'generate' | 'variation'>('generate')
  const { presets } = usePresets()
  const [presetId, setPresetId] = useState('')
  const eligible = kind === 'generation' ? scenes.filter(s => approvedStates.includes(s.workflow_state) && !s.active_job) : []
  // Scenes that already have results start unticked when the list comes from the toolbar.
  const [chosen, setChosen] = useState<string[]>(() => eligible.filter(s => preselectAll || s.workflow_state === 'approved').map(s => s.id))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [average, setAverage] = useState<number | null>(null)
  const apiEngines = useApiEngines()
  const [model, setModel] = useState<string | null>(null)
  const charged = isApiEngine(engine)
  useEffect(() => {
    if (charged) request<{ models: Record<string, { analysis?: string }> }>('/api/engines/settings').then(s => setModel(s.models[engine]?.analysis ?? null), () => undefined)
  }, [charged, engine])
  useEffect(() => {
    request<{ analysis: Record<string, number | null>; generation: number | null }>('/api/batches/timing')
      .then(t => setAverage(kind === 'generation' ? t.generation : t.analysis[engine] ?? null), () => setAverage(null))
  }, [kind, engine])
  const skipped: { title: string; reason: string }[] = []
  let queued: SceneSummary[] = []
  if (kind === 'analysis') {
    for (const s of scenes) {
      if (s.active_job) skipped.push({ title: s.title, reason: 'another run is running or waiting for it' })
      else if (s.analysis_version != null && !includeAnalysed) skipped.push({ title: s.title, reason: 'it already has an analysis' })
      else queued.push(s)
    }
  } else {
    for (const s of scenes) {
      if (s.active_job) skipped.push({ title: s.title, reason: 'another run is running or waiting for it' })
      else if (!approvedStates.includes(s.workflow_state)) skipped.push({ title: s.title, reason: 'it is not approved' })
    }
    queued = eligible.filter(s => chosen.includes(s.id))
  }
  const analysed = kind === 'analysis' ? scenes.filter(s => !s.active_job && s.analysis_version != null).length : 0
  const runs = kind === 'generation' ? queued.length * count : queued.length
  const limit = kind === 'generation' ? MAX_GENERATION_RUNS : MAX_ANALYSIS_RUNS
  const name = engineNames[engine] ?? engine
  async function start() {
    setBusy(true); setError('')
    try {
      const result = kind === 'analysis'
        ? await send<BatchStart>('/api/batches/analysis', 'POST', token, { scene_ids: queued.map(s => s.id), include_analysed: includeAnalysed, ...(charged ? { confirm_charges: true } : {}) })
        : await send<BatchStart>('/api/batches/generation', 'POST', token, { items: queued.map(s => ({ scene_id: s.id })), count, mode, ...(presetId ? { preset_id: presetId } : {}) })
      onStarted(result)
    } catch (e) { setError(e instanceof Error ? e.message : 'The batch could not be started.'); setBusy(false) }
  }
  return <Dialog label="batch-title" onClose={onClose}>
    <div className="text-dialog-form">
      <h2 id="batch-title">{kind === 'analysis' ? `Analyse ${plural(queued.length, 'scene')} with ${name}` : 'Generate approved scenes'}</h2>
      {kind === 'generation' && <>
        <p className="hint">Each scene uses its own approval: exactly the prompt and photos you approved for it.</p>
        {eligible.length ? <ul className="batch-choices">{eligible.map(s => <li key={s.id}><label className="checkbox-label">
          <input type="checkbox" checked={chosen.includes(s.id)} disabled={busy} onChange={() => setChosen(c => c.includes(s.id) ? c.filter(x => x !== s.id) : [...c, s.id])} />
          <img src={s.thumbnail_url} alt="" /><span><b>{s.title}</b>{s.result_count ? <small> · {plural(s.result_count, 'result')} already</small> : null}</span></label></li>)}</ul>
          : <p className="notice-line">None of these scenes has a valid approval. Approve each scene on its Review step first.</p>}
        <div className="batch-options">
          <PresetSelect id="batch-preset" presets={presets} value={presetId} disabled={busy} onChange={p => { setPresetId(p?.id ?? ''); if (p) setCount(Math.min(p.images, 5)) }} />
          <div><span className="field-label">Images per scene</span>
            <div className="segmented" role="radiogroup" aria-label="Images per scene">{[1, 2, 3, 4, 5].map(n => <label key={n} className={`segment ${count === n ? 'selected' : ''}`}><input type="radio" name="batch-count" checked={count === n} disabled={busy} onChange={() => setCount(n)} />{n}</label>)}</div></div>
          <div><span className="field-label">Kind</span>
            <div className="segmented" role="radiogroup" aria-label="Kind of image">{(['generate', 'variation'] as const).map(m => <label key={m} className={`segment ${mode === m ? 'selected' : ''}`}><input type="radio" name="batch-mode" checked={mode === m} disabled={busy} onChange={() => setMode(m)} />{m === 'generate' ? 'New image' : 'Variation'}</label>)}</div></div>
        </div>
        {eligible.length > 0 && !queued.length && <p className="hint">Tick the scenes to generate. Scenes that already have results start unticked.</p>}
        {mode === 'variation' && <p className="hint">A variation asks for small natural differences in fine details, never in composition, poses, outfits or identities.</p>}
      </>}
      {kind === 'analysis' && analysed > 0 && <label className="checkbox-label"><input type="checkbox" checked={includeAnalysed} disabled={busy} onChange={e => setIncludeAnalysed(e.target.checked)} />
        <span>Also analyse the {plural(analysed, 'scene')} that already {analysed === 1 ? 'has' : 'have'} an analysis. A new version is added; an approval is cancelled when it arrives.</span></label>}
      {runs > 0 && charged && apiEngines.byId[engine] && <ChargeSummary engine={apiEngines.byId[engine]} model={model} runs={runs} />}
      {runs > 0 && <div className="check-box batch-summary">
        <strong>{kind === 'generation' ? `${plural(runs, 'image')} from ${allowance[engine]}` : `${runs} ${runs === 1 ? 'run' : 'runs'} from ${allowance[engine]}`}</strong>
        <ul>
          <li>{kind === 'generation' ? 'Each run sends one scene’s Base Image and approved reference photos' : 'Each run sends one Base Image'} to {sendsTo[engine]}{charged ? '' : ', using your own sign-in'}.</li>
          <li>They run one after another, never at the same time{average ? `: about ${duration(average * runs)} in all, going by earlier runs on this computer` : ''}.</li>
          <li>A failed item is marked Failed and the next one starts. {charged ? 'A refused key or a rate or spending limit' : 'A plan limit or signing out'} pauses the batch until you continue it. Nothing is retried on its own.</li>
        </ul>
      </div>}
      {runs > limit && <p className="frame-error" role="alert">A batch makes at most {limit} {kind === 'generation' ? 'images, because image generation uses your allowance quickly' : 'runs'}. Choose fewer.</p>}
      <SkippedList items={skipped} />
      {error && <p className="frame-error" role="alert">{error}</p>}
      <div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Cancel</button>
        <button type="button" disabled={busy || !runs || runs > limit} onClick={() => void start()}>{busy ? 'Starting…' : kind === 'generation' ? `Generate ${plural(runs, 'image')}` : `Analyse ${plural(runs, 'scene')}${charged ? ' and accept charges' : ''}`}</button></div>
    </div>
  </Dialog>
}

type Suggestion = { suggested: { scene_id: string; title: string; assigned: number; subjects: number }[]; skipped: Skipped[]; left_out: string[] }

/** Suggest a group's characters for several scenes, left to right; each scene is confirmed on its own. */
export function GroupDialog({ scenes, token, onClose, onDone }: { scenes: SceneSummary[]; token: string; onClose: () => void; onDone: (result: Suggestion) => void }) {
  const [groups, setGroups] = useState<Group[]>([])
  const [characters, setCharacters] = useState<Character[]>([])
  const [groupId, setGroupId] = useState('')
  const [order, setOrder] = useState<string[]>([])
  const [replace, setReplace] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    Promise.all([request<Group[]>('/api/groups'), request<Character[]>('/api/characters')])
      .then(([g, c]) => { setGroups(g); setCharacters(c); if (g[0]) { setGroupId(g[0].id); setOrder(g[0].member_ids) } }, e => setError(e.message))
  }, [])
  const byId = Object.fromEntries(characters.map(c => [c.id, c]))
  const usable = (id: string) => !!byId[id] && !byId[id].archived && byId[id].photos.length > 0
  const people = order.filter(id => byId[id])
  const move = (index: number, by: number) => setOrder(o => { const next = [...o]; [next[index], next[index + by]] = [next[index + by], next[index]]; return next })
  const ready = scenes.filter(s => s.analysis_version != null && !s.active_job && !approvedStates.includes(s.workflow_state))
  async function submit() {
    setBusy(true); setError('')
    try { onDone(await send<Suggestion>('/api/scenes/suggest-group', 'POST', token, { scene_ids: scenes.map(s => s.id), group_id: groupId, order: people, replace_existing: replace })) }
    catch (e) { setError(e instanceof Error ? e.message : 'The suggestions could not be saved.'); setBusy(false) }
  }
  return <Dialog label="group-title" className="group-dialog" onClose={onClose}>
    <div className="text-dialog-form">
      <h2 id="group-title">Suggest from a group</h2>
      <p className="hint">The studio places the group’s characters from left to right in each scene, as suggestions. Nothing is sent anywhere and nothing is approved: open each scene, check who is where, then save its assignments.</p>
      {!groups.length ? <p className="notice-line">No groups yet. Create one on the Characters page first.</p> : <>
        <label htmlFor="suggest-group">Group</label>
        <select id="suggest-group" value={groupId} disabled={busy} onChange={e => { setGroupId(e.target.value); setOrder(groups.find(g => g.id === e.target.value)?.member_ids ?? []) }}>
          {groups.map(g => <option key={g.id} value={g.id}>{g.name} ({g.member_ids.length})</option>)}
        </select>
        <span className="field-label">From left to right</span>
        <ol className="order-list">{people.map((id, index) => <li key={id} className={usable(id) ? '' : 'unavailable'}>
          <span className="order-number">{index + 1}</span><Avatar character={byId[id]} size="mini" /><span className="order-name">{byId[id].name}{!usable(id) && <small> · {byId[id].archived ? 'archived' : 'no photos'}, left out</small>}</span>
          <button type="button" className="secondary compact icon-only" aria-label={`Move ${byId[id].name} left`} disabled={busy || index === 0} onClick={() => move(index, -1)}>↑</button>
          <button type="button" className="secondary compact icon-only" aria-label={`Move ${byId[id].name} right`} disabled={busy || index === people.length - 1} onClick={() => move(index, 1)}>↓</button>
        </li>)}</ol>
        {!people.length && <p className="hint">This group has nobody in it yet.</p>}
        <label className="checkbox-label"><input type="checkbox" checked={replace} disabled={busy} onChange={e => setReplace(e.target.checked)} /><span>Replace assignments that scenes already have</span></label>
        <p className="hint">{ready.length} of {plural(scenes.length, 'selected scene')} can take suggestions now. Scenes without an analysis, approved scenes and scenes with a run in progress are skipped.</p>
      </>}
      {error && <p className="frame-error" role="alert">{error}</p>}
      <div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Cancel</button>
        <button type="button" disabled={busy || !groupId || !people.some(usable) || !ready.length} onClick={() => void submit()}>{busy ? 'Saving…' : 'Suggest assignments'}</button></div>
    </div>
  </Dialog>
}
