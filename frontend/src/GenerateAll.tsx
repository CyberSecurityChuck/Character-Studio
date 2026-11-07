import { useEffect, useMemo, useState } from 'react'
import { request, send } from './api'
import { ChargeSummary, generationNames, isImageEngine, sendsTo, useApiEngines } from './ApiEngines'
import { Dialog, plural, MAX_GENERATION_RUNS } from './Batches'
import type { PipelineRun } from './Pipeline'
import { PresetSelect, usePresets } from './Presets'
import type { SceneSet } from './SceneSets'

// Phase 7D: Generate all for a scene set - any number of images in chained batches of 20,
// the estimate before starting, and the per-scene labels of the last run (D030, D039).

type Row = { scene_id: string; title: string; thumbnail_url: string; result_count: number; has_results: boolean; state: 'new' | 'more' | 'blocked'; reason: string | null }
export type GeneratePreview = { engine: string; average_seconds: number | null; counts: { total: number; approved: number; new: number; more: number; blocked: number }; rows: Row[]; results: number; open_run: string | null }
type EngineSettings = { models: Record<string, { generation?: string }>; image_options: Record<string, { size: string; quality?: string }> }

const COUNTS = [1, 2, 3, 4, 5]
const LIST_LIMIT = 8
const plan: Record<string, string> = { codex_cli: 'your ChatGPT plan’s allowance' }

/** Hours and minutes for long runs, rounded: an estimate, not a promise. */
export function roughly(seconds: number) {
  if (seconds < 90) return `${Math.max(1, Math.round(seconds))} s`
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  return `${hours} h${minutes % 60 ? ` ${minutes % 60} min` : ''}`
}

/** Choose the approved scenes, read what the run will use, then start every image with one click. */
export function GenerateAllDialog({ item, token, onClose, onStarted }: { item: SceneSet; token: string; onClose: () => void; onStarted: (run: PipelineRun) => void }) {
  const apiEngines = useApiEngines()
  const { presets } = usePresets()
  const [data, setData] = useState<GeneratePreview | null>(null)
  const [settings, setSettings] = useState<EngineSettings | null>(null)
  const [more, setMore] = useState(false)
  const [off, setOff] = useState<string[]>([])
  const [count, setCount] = useState(1)
  const [mode, setMode] = useState<'generate' | 'variation'>('generate')
  const [presetId, setPresetId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    Promise.all([request<GeneratePreview>(`/api/scene-sets/${item.id}/generate-all`), request<EngineSettings>('/api/engines/settings')])
      .then(([p, s]) => { setData(p); setSettings(s) }, e => setError(e instanceof Error ? e.message : 'The set could not be loaded.'))
  }, [item.id])
  const offered = useMemo(() => (data?.rows ?? []).filter(r => r.state === 'new' || (more && r.state === 'more')), [data, more])
  const blocked = (data?.rows ?? []).filter(r => r.state === 'blocked')
  if (!data || !settings) return <Dialog label="generate-all-title" onClose={onClose}><div className="text-dialog-form"><h2 id="generate-all-title">Generate · {item.name}</h2>{error ? <p className="frame-error" role="alert">{error}</p> : <p role="status">Loading…</p>}</div></Dialog>

  const chosen = offered.filter(r => !off.includes(r.scene_id))
  const images = chosen.length * count
  const perBatch = Math.max(1, Math.floor(MAX_GENERATION_RUNS / count))
  const parts = Math.ceil(chosen.length / perBatch)
  const engine = data.engine
  const name = generationNames[engine] ?? engine
  const charged = isImageEngine(engine)
  const manual = engine === 'manual'
  const preset = presets.find(p => p.id === presetId)
  const options = settings.image_options[engine]
  const image = charged && options ? { size: preset?.image_size ?? options.size, ...(options.quality ? { quality: preset?.image_quality ?? options.quality } : {}) } : undefined
  const from = charged ? `your ${name} key (charged per image)` : plan[engine] ?? `your ${name} plan’s allowance`
  const toggle = (id: string) => setOff(o => o.includes(id) ? o.filter(x => x !== id) : [...o, id])
  async function start() {
    setBusy(true); setError('')
    try {
      const run = await send<PipelineRun>(`/api/scene-sets/${item.id}/generate-all`, 'POST', token, {
        scene_ids: chosen.map(r => r.scene_id), count, mode, ...(presetId ? { preset_id: presetId } : {}), ...(charged ? { confirm_charges: true } : {}),
      })
      onStarted(run)
    } catch (e) { setError(e instanceof Error ? e.message : 'Generate all could not be started.'); setBusy(false) }
  }
  return <Dialog label="generate-all-title" className="assign-dialog generate-dialog" onClose={onClose}>
    <div className="text-dialog-form">
      <h2 id="generate-all-title">Generate · {item.name}</h2>
      <p className="hint">Each scene uses its own approval: exactly the prompt and photos you approved for it. Scenes that already have images from their approval start unticked.</p>
      {manual ? <p className="notice-line">Manual generation is selected in Studio settings. Choose an engine there to generate the set.</p>
        : data.open_run ? <p className="notice-line">A run is already in progress for this set. Wait for it to finish, or cancel it, first.</p> : null}
      {!data.rows.length ? <p className="notice-line">No scene in this set is approved yet. Use the Approve step first.</p> : <>
        <div className="assign-toolbar">
          <span className="hint">{plural(chosen.length, 'scene')} ticked of {plural(offered.length, 'scene')}{data.counts.approved < data.counts.total ? ` · ${data.counts.total - data.counts.approved} not approved yet` : ''}</span>
          <span className="row-actions">
            {data.counts.more > 0 && <label className="checkbox-label"><input type="checkbox" checked={more} disabled={busy} onChange={e => setMore(e.target.checked)} /><span>More images for the {plural(data.counts.more, 'scene')} that already {data.counts.more === 1 ? 'has' : 'have'} results</span></label>}
            <button type="button" className="link-button" disabled={busy || !offered.length} onClick={() => setOff([])}>Tick all</button>
            <button type="button" className="link-button" disabled={busy || !offered.length} onClick={() => setOff(offered.map(r => r.scene_id))}>Untick all</button>
          </span></div>
        {offered.length ? <ul className="generate-choices">{offered.map(r => <li key={r.scene_id}><label>
          <input type="checkbox" checked={!off.includes(r.scene_id)} disabled={busy} onChange={() => toggle(r.scene_id)} />
          <img src={r.thumbnail_url} alt="" loading="lazy" />
          <span><b>{r.title}</b>{r.has_results && <small>{plural(r.result_count, 'result')} already</small>}</span></label></li>)}</ul>
          : <p className="ok-line">Every approved scene already has images. Tick “More images” to make more.</p>}
        {blocked.length > 0 && <div className="check-box warning"><strong>{plural(blocked.length, 'approved scene')} cannot be generated now</strong>
          <ul>{blocked.slice(0, LIST_LIMIT).map(r => <li key={r.scene_id}><b>{r.title}</b>: {r.reason}</li>)}{blocked.length > LIST_LIMIT && <li>and {blocked.length - LIST_LIMIT} more</li>}</ul></div>}
        <div className="batch-options">
          <PresetSelect id="generate-preset" presets={presets} value={presetId} disabled={busy} onChange={p => { setPresetId(p?.id ?? ''); if (p) setCount(Math.min(p.images, 5)) }} />
          <div><span className="field-label">Images per scene</span>
            <div className="segmented" role="radiogroup" aria-label="Images per scene">{COUNTS.map(n => <label key={n} className={`segment ${count === n ? 'selected' : ''}`}><input type="radio" name="generate-count" checked={count === n} disabled={busy} onChange={() => setCount(n)} />{n}</label>)}</div></div>
          <div><span className="field-label">Kind</span>
            <div className="segmented" role="radiogroup" aria-label="Kind of image">{(['generate', 'variation'] as const).map(m => <label key={m} className={`segment ${mode === m ? 'selected' : ''}`}><input type="radio" name="generate-mode" checked={mode === m} disabled={busy} onChange={() => setMode(m)} />{m === 'generate' ? 'New image' : 'Variation'}</label>)}</div></div>
        </div>
        {mode === 'variation' && <p className="hint">A variation asks for small natural differences in fine details, never in composition, poses, outfits or identities.</p>}
      </>}
      {images > 0 && !manual && <>
        {charged && apiEngines.byId[engine] && <ChargeSummary engine={apiEngines.byId[engine]} model={settings.models[engine]?.generation ?? null} runs={images} image={image}
          what="each scene’s Base Image and approved reference photos (without location data) with its approved prompt" />}
        <div className="check-box batch-summary generate-summary">
          <strong>{plural(images, 'image')} from {from}</strong>
          <dl className="generate-figures">
            <div><dt>Images</dt><dd>{images}</dd></div>
            <div><dt>Batches</dt><dd>{parts} <small>of at most {MAX_GENERATION_RUNS}</small></dd></div>
            <div><dt>Estimated time</dt><dd>{data.average_seconds ? `about ${roughly(data.average_seconds * images)}` : 'no estimate yet'}</dd></div>
          </dl>
          <ul>
            <li>Each image sends one scene’s Base Image and approved reference photos to {sendsTo[engine] ?? name}{charged ? '' : ', using your own sign-in'}.</li>
            <li>{parts > 1 ? `The studio splits them into ${parts} batches and runs` : 'The studio runs them as one batch,'} one image after another, never at the same time.</li>
            <li>{data.average_seconds ? `The estimate goes by earlier images on this computer (about ${roughly(data.average_seconds)} each).` : 'No image has been made with this engine on this computer yet, so there is no time estimate.'}</li>
            {!charged && <li>This uses {plural(images, 'image run')} of {from}. Images use a plan’s allowance several times faster than other work.</li>}
          </ul>
        </div>
        <div className="check-box warning"><strong>A long run may stop partway</strong>
          <ul>
            <li><b>{plural(images, 'image')} can use up {charged ? 'your key’s rate or spending limit' : 'your plan’s limit'}.</b> A limit, a sign-out or a restart pauses the run. Every finished image is kept and the summary shows what was done, what failed and what has not started.</li>
            <li>Nothing continues on its own: click Continue when you are ready, for example after the limit resets. Nothing is retried on its own; Try failed again stays your choice.</li>
          </ul></div>
      </>}
      {error && <p className="frame-error" role="alert">{error}</p>}
      <div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Cancel</button>
        <button type="button" disabled={busy || !images || manual || !!data.open_run} onClick={() => void start()}>{busy ? 'Starting…' : `Generate ${plural(images, 'image')}${charged ? ' and accept charges' : ''}`}</button></div>
    </div>
  </Dialog>
}

// Labels of the last run with images ----------------------------------------------------------

export type GenLabel = 'generated' | 'failed' | 'not_started' | 'interrupted' | 'running'
export type SceneLabels = {
  run: { id: string; kind: 'everything' | 'generate'; status: string; created_at: string } | null
  labels: Record<string, { label: GenLabel; made: number; total: number }>
  counts: Record<Exclude<GenLabel, 'running'>, number>
}
export const LABELS = ['generated', 'failed', 'not_started', 'interrupted'] as const
export const labelWords: Record<GenLabel, string> = { generated: 'Generated', failed: 'Failed', not_started: 'Not started', interrupted: 'Interrupted', running: 'Generating' }
export const isLabel = (value: string | null): value is (typeof LABELS)[number] => !!value && (LABELS as readonly string[]).includes(value)

/** One tag on a scene card: how the scene did in the set's last run with images. */
export function LabelTag({ value }: { value: { label: GenLabel; made: number; total: number } | undefined }) {
  if (!value) return null
  return <span className={`tag gen-${value.label}`} title={`${value.made} of ${plural(value.total, 'image')} made in the last run`}>{labelWords[value.label]}{value.total > 1 && value.label !== 'generated' ? ` · ${value.made}/${value.total}` : ''}</span>
}

/** The row of label chips under the stage tiles; a chip filters the scene cards. */
export function LabelChips({ data, value, onChange }: { data: SceneLabels; value: string | null; onChange: (next: (typeof LABELS)[number] | null) => void }) {
  if (!data.run) return null
  const when = new Date(data.run.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
  return <div className="label-row" role="group" aria-label="Filter by the last run with images">
    <span className="label-row-title">Last {data.run.kind === 'generate' ? 'Generate all' : 'Run everything'} <small>{when}</small></span>
    {LABELS.map(l => <button key={l} type="button" className={`label-chip chip-${l} ${data.counts[l] ? '' : 'empty'}`} aria-pressed={value === l} onClick={() => onChange(value === l ? null : l)}>
      <span className="chip-dot" aria-hidden="true" />{labelWords[l]}<strong>{data.counts[l]}</strong></button>)}
  </div>
}
