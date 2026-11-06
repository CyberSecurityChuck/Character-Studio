import { useCallback, useEffect, useMemo, useState } from 'react'
import { request, send } from './api'
import { ChargeSummary, engineNames, generationNames, isApiEngine, isImageEngine, useApiEngines } from './ApiEngines'
import { Dialog, plural, MAX_ANALYSIS_RUNS, MAX_GENERATION_RUNS } from './Batches'
import { type Character, type Group } from './Library'
import { PresetSelect, usePresets } from './Presets'
import type { SceneSet } from './SceneSets'

// Phase 7C-2: Run everything - the full auto-pipeline for one scene set (D030, D037).

type Stopped = { scene_id: string; title: string; reason: string }
type RunBatch = { id: string; kind: 'analysis' | 'generation'; state: string; pause_kind: string | null; total: number; done: number; failed: number; cancelled: number }
export type PipelineRun = {
  id: string; status: 'running' | 'paused' | 'waiting' | 'cancelled' | 'finished'; stage: 'analysing' | 'generating'; pause_details: string | null
  rules: { images: number; stop_before_generating: boolean; let_uncertain: boolean; let_mismatch: boolean; generation_engine: string; analysis_engine: string | null; preset: string | null }
  outcome: { analyse?: number; approved?: number; stopped?: Stopped[]; already_done?: number; generate?: number; images?: number; note?: string }
  batches: RunBatch[]; created_at: string; updated_at: string
}
type Preview = { counts: { total: number; analyse: number; prepare: number; generate: number; done: number; busy: number }; analysis_engine: string; generation_engine: string; run: PipelineRun | null }
type EngineSettings = { models: Record<string, { analysis?: string; generation?: string }>; image_options: Record<string, { size: string; quality?: string }> }

const MAX_IMAGES = 10
const STOP_LIMIT = 8

/** Set the rules once, read what will happen, then start the whole set with one click. */
export function RunEverythingDialog({ item, token, onClose, onStarted }: { item: SceneSet; token: string; onClose: () => void; onStarted: (run: PipelineRun) => void }) {
  const apiEngines = useApiEngines()
  const { presets } = usePresets()
  const [preview, setPreview] = useState<Preview | null>(null)
  const [settings, setSettings] = useState<EngineSettings | null>(null)
  const [characters, setCharacters] = useState<Character[]>([])
  const [groups, setGroups] = useState<Group[]>([])
  const [rule, setRule] = useState<'none' | 'one' | 'group'>('one')
  const [characterId, setCharacterId] = useState('')
  const [largest, setLargest] = useState(false)
  const [groupId, setGroupId] = useState('')
  const [order, setOrder] = useState<string[]>([])
  const [presetId, setPresetId] = useState('')
  const [images, setImages] = useState(1)
  const [letUncertain, setLetUncertain] = useState(false)
  const [letMismatch, setLetMismatch] = useState(false)
  const [pauseFirst, setPauseFirst] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    Promise.all([request<Preview>(`/api/scene-sets/${item.id}/pipeline`), request<EngineSettings>('/api/engines/settings'), request<Character[]>('/api/characters'), request<Group[]>('/api/groups')])
      .then(([p, s, c, g]) => { setPreview(p); setSettings(s); setCharacters(c); setGroups(g) }, e => setError(e instanceof Error ? e.message : 'The set could not be loaded.'))
  }, [item.id])
  const usable = useMemo(() => characters.filter(c => !c.archived && c.photos.length > 0), [characters])
  const byId = useMemo(() => Object.fromEntries(characters.map(c => [c.id, c])), [characters])
  useEffect(() => { if (!characterId && usable[0]) setCharacterId(usable[0].id) }, [usable, characterId])
  useEffect(() => { if (!groupId && groups[0]) { setGroupId(groups[0].id); setOrder(groups[0].member_ids) } }, [groups, groupId])
  const move = (index: number, by: number) => setOrder(o => { const next = [...o]; [next[index], next[index + by]] = [next[index + by], next[index]]; return next })
  const people = order.filter(id => byId[id])

  if (!preview || !settings) return <Dialog label="run-title" onClose={onClose}><div className="text-dialog-form"><h2 id="run-title">Run everything · {item.name}</h2>{error ? <p className="frame-error" role="alert">{error}</p> : <p role="status">Loading…</p>}</div></Dialog>
  const { counts } = preview
  const analysis = preview.analysis_engine, generation = preview.generation_engine
  const analysisPaid = counts.analyse > 0 && isApiEngine(analysis)
  const imagePaid = isImageEngine(generation)
  const charged = analysisPaid || imagePaid
  // At most this many images: every scene that is not finished yet, if none stops.
  const maxImages = (counts.analyse + counts.prepare + counts.generate) * images
  const blocked = (counts.analyse > 0 && analysis === 'manual') || generation === 'manual'
  const ruleMissing = (rule === 'one' && !characterId) || (rule === 'group' && !people.length)
  async function run() {
    setBusy(true); setError('')
    try {
      const started = await send<PipelineRun>(`/api/scene-sets/${item.id}/pipeline`, 'POST', token, {
        rule, character_id: rule === 'one' ? characterId : null, several_people: largest ? 'largest' : 'skip',
        group_id: rule === 'group' ? groupId || null : null, order: rule === 'group' ? people : [],
        preset_id: presetId || null, images, let_uncertain: letUncertain, let_mismatch: letMismatch,
        stop_before_generating: pauseFirst, confirm_charges: charged,
      })
      onStarted(started)
    } catch (e) { setError(e instanceof Error ? e.message : 'Run everything could not be started.'); setBusy(false) }
  }
  return <Dialog label="run-title" className="assign-dialog run-dialog" onClose={onClose}>
    <div className="text-dialog-form">
      <h2 id="run-title">Run everything · {item.name}</h2>
      <p className="hint">Set the rules once. The studio then analyses, assigns, drafts, approves and generates the whole set, one stage after another. Each scene picks up where it is: what you already decided by hand is kept.</p>
      <ol className="run-plan">
        <li><b>Analyse</b> {counts.analyse ? `${plural(counts.analyse, 'scene')} with ${engineNames[analysis] ?? analysis}, in batches of at most ${MAX_ANALYSIS_RUNS}` : 'nothing: every scene is analysed'}</li>
        <li><b>Assign, draft and approve</b> {plural(counts.analyse + counts.prepare, 'scene')} by the rules below (no engine runs for this)</li>
        <li><b>Generate</b> up to {plural(maxImages, 'image')} with {generationNames[generation] ?? generation}, in batches of at most {MAX_GENERATION_RUNS}{counts.done ? ` · ${plural(counts.done, 'scene')} already have results and are left alone` : ''}</li>
      </ol>
      {counts.busy > 0 && <p className="notice-line">{plural(counts.busy, 'scene')} {counts.busy === 1 ? 'has' : 'have'} a run in progress and will stop at Needs your check.</p>}

      <fieldset className="run-rules"><legend>People nobody is assigned to yet</legend>
        <label className="checkbox-label"><input type="radio" name="run-rule" checked={rule === 'one'} onChange={() => setRule('one')} /> One character</label>
        {rule === 'one' && <div className="run-sub">
          <select aria-label="Character" value={characterId} onChange={e => setCharacterId(e.target.value)}>{usable.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
          <label className="checkbox-label"><input type="checkbox" checked={largest} onChange={e => setLargest(e.target.checked)} /> Also in scenes with several people: give it to the largest person, the others keep their look</label></div>}
        <label className="checkbox-label"><input type="radio" name="run-rule" checked={rule === 'group'} disabled={!groups.length} onChange={() => setRule('group')} /> A group, left to right</label>
        {rule === 'group' && <div className="run-sub">
          <select aria-label="Group" value={groupId} onChange={e => { setGroupId(e.target.value); setOrder(groups.find(g => g.id === e.target.value)?.member_ids ?? []) }}>{groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}</select>
          <ol className="run-order">{people.map((id, i) => <li key={id}><span>{i + 1}. {byId[id].name}</span>
            <button type="button" className="secondary compact" disabled={i === 0} aria-label={`Move ${byId[id].name} left`} onClick={() => move(i, -1)}>↑</button>
            <button type="button" className="secondary compact" disabled={i === people.length - 1} aria-label={`Move ${byId[id].name} right`} onClick={() => move(i, 1)}>↓</button></li>)}</ol></div>}
        <label className="checkbox-label"><input type="radio" name="run-rule" checked={rule === 'none'} onChange={() => setRule('none')} /> Leave them to me (those scenes stop at Needs your check)</label>
      </fieldset>

      <div className="run-row">
        <PresetSelect id="run-preset" presets={presets} value={presetId} onChange={p => setPresetId(p?.id ?? '')} label="Preset for new drafts" />
        <div><label htmlFor="run-images">Images per scene</label><input id="run-images" type="number" min={1} max={MAX_IMAGES} value={images} onChange={e => setImages(Math.min(MAX_IMAGES, Math.max(1, Number(e.target.value) || 1)))} /></div>
      </div>

      <fieldset className="run-rules"><legend>Scenes that stop at Needs your check</legend>
        <p className="hint">By default these stop for you to look at. Scenes whose prompt has warnings always stop.</p>
        <label className="checkbox-label"><input type="checkbox" checked={letUncertain} onChange={e => setLetUncertain(e.target.checked)} /> Let scenes with uncertain details through (the details are accepted as described)</label>
        <label className="checkbox-label"><input type="checkbox" checked={letMismatch} onChange={e => setLetMismatch(e.target.checked)} /> Let mismatched scenes through (extra people keep their original look; unused characters do not appear)</label>
        <label className="checkbox-label"><input type="checkbox" checked={pauseFirst} onChange={e => setPauseFirst(e.target.checked)} /> Stop before generating so I can look first</label>
      </fieldset>

      {analysisPaid && apiEngines.byId[analysis] && <ChargeSummary engine={apiEngines.byId[analysis]} model={settings.models[analysis]?.analysis ?? null} runs={counts.analyse} />}
      {imagePaid && apiEngines.byId[generation] && <ChargeSummary engine={apiEngines.byId[generation]} model={settings.models[generation]?.generation ?? null} runs={maxImages} image={settings.image_options[generation]} />}
      <div className="check-box warning"><strong>Before you start</strong>
        <ul>
          <li>Once started, it goes on by itself from one stage to the next{pauseFirst ? ', and stops after approving' : ''}. Nothing else is started for you.</li>
          <li>Every scene that is approved gets its own approval, recorded as <b>automatic</b>. Changing a scene later cancels its approval as always.</li>
          <li><b>A large set can use up {charged ? 'your API keys’ limits' : 'your plans’ allowance'} and stop partway.</b> A limit, a sign-out or a restart pauses the run; what finished is kept, and nothing continues until you click Continue. Nothing is retried.</li>
          {charged && <li><b>Paid engine{analysisPaid && imagePaid ? 's' : ''}:</b> starting accepts the charges for every run of this Run everything.</li>}
        </ul></div>
      {blocked && <p className="frame-error">{generation === 'manual' ? 'Manual generation is selected in Studio settings. Choose an engine there first.' : 'Manual analysis is selected in Studio settings, so scenes without an analysis cannot be analysed.'}</p>}
      {error && <p className="frame-error" role="alert">{error}</p>}
      <div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Cancel</button>
        <button type="button" disabled={busy || blocked || ruleMissing} onClick={() => void run()}>{busy ? 'Starting…' : `Run everything${charged ? ' and accept charges' : ''}`}</button></div>
    </div>
  </Dialog>
}

const stageWords = (run: PipelineRun) => {
  if (run.status === 'finished') return 'Finished'
  if (run.status === 'cancelled') return 'Cancelled'
  if (run.status === 'waiting') return 'Approved, waiting for you to generate'
  if (run.status === 'paused') return 'Paused'
  const paused = run.batches.some(b => b.state === 'paused')
  if (run.stage === 'analysing') return paused ? 'Analysing · paused' : 'Analysing'
  return paused ? 'Generating · paused' : 'Generating'
}

/** The set's latest Run everything: where it stands, what stopped and why, and its buttons. */
export function PipelineCard({ item, token, version, onChanged, onNotice, onOpenScene }: { item: SceneSet; token: string; version: string; onChanged: () => void; onNotice: (text: string, problem?: string) => void; onOpenScene: (id: string) => void }) {
  const [run, setRun] = useState<PipelineRun | null>(null)
  const [busy, setBusy] = useState(false)
  const [hidden, setHidden] = useState(() => window.localStorage.getItem(`character-studio.run-hidden.${item.id}`) ?? '')
  const load = useCallback(() => request<Preview>(`/api/scene-sets/${item.id}/pipeline`).then(p => setRun(p.run), () => undefined), [item.id])
  useEffect(() => { void load() }, [load, version])
  const moving = run?.status === 'running'
  useEffect(() => {
    if (!moving) return
    const timer = window.setInterval(() => { void load(); onChanged() }, 3000)
    return () => window.clearInterval(timer)
  }, [moving, load, onChanged])
  if (!run || hidden === run.id) return null
  const open = ['running', 'paused', 'waiting'].includes(run.status)
  const paid = isImageEngine(run.rules.generation_engine) || (!!run.rules.analysis_engine && isApiEngine(run.rules.analysis_engine))
  async function act(path: 'continue' | 'cancel' | 'generate', question?: string) {
    if (question && !window.confirm(question)) return
    setBusy(true)
    try {
      const charge = path !== 'cancel' && paid
      if (charge && !window.confirm('This uses a paid engine. Accept the charges for the remaining runs?')) { setBusy(false); return }
      const next = await send<PipelineRun>(`/api/pipelines/${run!.id}/${path}`, 'POST', token, charge ? { confirm_charges: true } : {})
      setRun(next); onChanged()
      onNotice(path === 'cancel' ? 'Run everything cancelled. Everything that finished is kept.' : path === 'generate' ? 'Generating the approved scenes, one image after another.' : 'Run everything continues.')
    } catch (e) { onNotice('', e instanceof Error ? e.message : 'That did not work.') }
    finally { setBusy(false) }
  }
  const o = run.outcome
  const stopped = o.stopped ?? []
  const images = run.batches.filter(b => b.kind === 'generation')
  const made = images.reduce((n, b) => n + b.done, 0)
  const analyses = run.batches.filter(b => b.kind === 'analysis')
  const analysed = analyses.reduce((n, b) => n + b.done, 0)
  const analysesTotal = analyses.reduce((n, b) => n + b.total, 0)
  return <section className={`run-card run-${run.status}`} aria-label="Run everything">
    <div className="run-head">
      <span className="run-dot" aria-hidden="true">{moving ? <span className="spinner" /> : run.status === 'finished' ? '✓' : run.status === 'cancelled' ? '–' : '❚❚'}</span>
      <div><strong>Run everything · {stageWords(run)}</strong>
        <span className="hint">{analysesTotal ? `${analysed} of ${analysesTotal} ${analysesTotal === 1 ? 'analysis' : 'analyses'}` : 'No analyses needed'}{o.approved !== undefined ? ` · ${plural(o.approved, 'scene')} approved automatically` : ''}{o.images ? ` · ${made} of ${plural(o.images, 'image')} made` : ''}{stopped.length ? ` · ${stopped.length} stopped for you` : ''}</span></div>
      <span className="run-actions">
        {run.status === 'waiting' && <button type="button" className="compact" disabled={busy} onClick={() => void act('generate')}>Generate {o.generate ? plural(o.generate * run.rules.images, 'image') : 'images'}</button>}
        {run.status === 'paused' && <button type="button" className="compact" disabled={busy} onClick={() => void act('continue')}>Continue</button>}
        {open && <button type="button" className="secondary compact" disabled={busy} onClick={() => void act('cancel', 'Cancel Run everything? Runs that have not started never run; everything that finished is kept.')}>Cancel run</button>}
        {!open && <button type="button" className="secondary compact" onClick={() => { window.localStorage.setItem(`character-studio.run-hidden.${item.id}`, run.id); setHidden(run.id) }}>Hide</button>}
      </span>
    </div>
    {run.pause_details && <p className="notice-line">{run.pause_details}</p>}
    {run.status === 'running' && run.batches.some(b => b.state === 'paused') && <p className="notice-line">A batch of this run is paused. Continue it in Batches below when you are ready; the run then goes on.</p>}
    {o.note && <p className="hint">{o.note}</p>}
    {stopped.length > 0 && <details className="run-stopped"><summary>{plural(stopped.length, 'scene')} stopped at Needs your check</summary>
      <ul>{stopped.slice(0, STOP_LIMIT).map(s => <li key={s.scene_id}><b>{s.title}</b>: {s.reason} <button type="button" className="link-button" onClick={() => onOpenScene(s.scene_id)}>Open scene</button></li>)}{stopped.length > STOP_LIMIT && <li>and {stopped.length - STOP_LIMIT} more</li>}</ul></details>}
  </section>
}
