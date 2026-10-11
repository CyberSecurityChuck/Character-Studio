import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from 'react'
import { request, send, type Bootstrap } from './api'
import { ChargeDialog, engineNames, isApiEngine, sendsTo, useApiEngines } from './ApiEngines'
import { BatchDialog, BatchList, GroupDialog, MAX_ANALYSIS_RUNS, type BatchStart } from './Batches'
import { CardMenu, SelectionBar, TextDialog, sentence } from './Controls'
import type { Character, Group } from './Library'
import { MappingPanel, PolishDialog, PromptHistory, ReviewPanel, SubjectCanvas, type BoxDraft } from './Mapping'
import { GeneratePanel, duration, type ExportPackage, type Result } from './Results'
import { replaceRoute, routeParts } from './route'

export type Box = { x: number; y: number; width: number; height: number }
type Uncertainty = { field: string; note: string }
type Subject = { label: string; bounding_box: Box } & Record<SubjectField, string>
export type AnalysisData = {
  schema_version: number
  image_properties: { orientation: string; approximate_aspect_ratio: string; style: string }
  scene_description: string
  camera: Record<CameraField, string>
  subjects: Subject[]
  environment: string; lighting: string; color_palette: string; atmosphere: string
  composition_constraints: string[]
  uncertainties: Uncertainty[]
}
type Analysis = { id: string; version: number; source: string; engine_version: string | null; has_raw_output: boolean; based_on_id: string | null; created_at: string; analysis: AnalysisData; confirmed_uncertainties: Uncertainty[] }
export type Prompt = { id: string; version: number; analysis_id: string | null; mapping_hash: string | null; prompt_text: string; negative_prompt: string; scene_changes: string; source: string; is_polished: boolean; polished_from_version_id: string | null; engine_version: string | null; created_at: string }
export type BatchPlace = { id: string; status: string; pause_kind: string | null; position: number; total: number; scene_items: number }
export type Job = { id: string; kind: string; engine: string; engine_name: string; engine_version: string | null; usage?: { input_tokens: number | null; output_tokens: number | null } | null; mode: string | null; batch: BatchPlace | null; batch_id: string | null; recoverable: boolean; seconds: number | null; status: string; error_kind: string | null; error_details: string | null; job_folder: string | null; timeout_seconds: number; result_id: string | null; input_id: string | null; decision: string | null; created_at: string; started_at: string | null; finished_at: string | null }
export type SceneSummary = { id: string; title: string; workflow_state: string; width: number; height: number; revision: number; created_at: string; updated_at: string; last_opened_at: string | null; thumbnail_url: string; original_url: string; analysis_version: number | null; prompt_version: number | null; result_count: number; active_job: Job | null }
export type SubjectAssignment = { label: string; bounding_box: Box; position: string; summary: string; action: 'replace' | 'keep' | 'unresolved'; character_id: string | null; reference_ids: string[]; references_auto: boolean; confirmed: boolean; suggested: boolean; images: number[]; problems: string[] }
export type ApprovalRecord = { id: string; approved_at: string; invalidated_at: string | null; invalidated_reason: string | null; snapshot_hash: string; analysis_version: number; prompt_id: string; prompt_version: number; is_polished: boolean; mappings: { subject: string; action: string; character_name: string | null; images: number[] }[] }
export type PendingPolish = { job_id: string; prompt_id: string; prompt_version: number; polished_text: string; engine_version: string | null; missing: string[] }
export type SceneDetail = SceneSummary & {
  analyses: Analysis[]; prompts: Prompt[]; jobs: Job[]
  mapping_group_id: string | null; mapping_hash: string | null; subjects: SubjectAssignment[]; total_images: number
  review: { blockers: string[]; warnings: string[]; notes: string[]; prompt_id: string | null }
  approval: { state: 'approved' | 'none'; current: ApprovalRecord | null; ended_reason: string | null }
  approvals: ApprovalRecord[]; pending_polish: PendingPolish | null
  results: Result[]; exports: ExportPackage[]; generation_timing: { runs: number; average_seconds: number | null }
}
type EngineSettings = { analysis_engine: string; generation_engine: string; claude_timeout: number; codex_timeout: number; api_timeout: number; api_models: Record<string, { analysis?: string }>; revision: number }
type Step = 'analysis' | 'characters' | 'prompt' | 'review' | 'generate'

type SubjectField = 'position' | 'pose_summary' | 'body_direction' | 'torso_orientation' | 'shoulder_alignment' | 'head_direction' | 'facial_viewing_angle' | 'eye_direction' | 'expression' | 'arms_and_hands' | 'legs_and_feet' | 'outfit' | 'hairstyle' | 'accessories'
type CameraField = 'height' | 'direction' | 'shot_type' | 'framing' | 'perspective'
const subjectFields: [SubjectField, string][] = [['position', 'Position'], ['pose_summary', 'Pose'], ['body_direction', 'Body direction'], ['torso_orientation', 'Torso'], ['shoulder_alignment', 'Shoulders'], ['head_direction', 'Head direction'], ['facial_viewing_angle', 'Face angle'], ['eye_direction', 'Eyes and gaze'], ['expression', 'Expression'], ['arms_and_hands', 'Arms and hands'], ['legs_and_feet', 'Legs and feet'], ['outfit', 'Outfit'], ['hairstyle', 'Hairstyle'], ['accessories', 'Accessories']]
const cameraFields: [CameraField, string][] = [['height', 'Height'], ['direction', 'Direction'], ['shot_type', 'Shot type'], ['framing', 'Framing'], ['perspective', 'Perspective']]
const sceneFields: ['environment' | 'lighting' | 'color_palette' | 'atmosphere', string][] = [['environment', 'Environment'], ['lighting', 'Lighting and shadows'], ['color_palette', 'Colour palette'], ['atmosphere', 'Atmosphere']]
export const stageLabels: Record<string, string> = { needs_analysis: 'Needs analysis', analysing: 'Analysing…', review_analysis: 'Review analysis', needs_mapping: 'Assign characters', analysis_ready: 'Ready for prompt', prompt_saved: 'Ready to approve', polishing: 'Polishing…', approved: 'Approved', generating: 'Generating…', generated: 'Results ready', waiting_analysis: 'Waiting to analyse', waiting_generation: 'Waiting to generate' }
const sourceLabels: Record<string, string> = { ...engineNames, manual_import: 'Manual import', user_edit: 'Your edit' }
const engineLabels = engineNames
const statusLabels: Record<string, string> = { not_started: 'Waiting', running: 'Running', completed: 'Completed', failed: 'Failed', cancelled: 'Cancelled', interrupted: 'Interrupted' }
const kindLabels: Record<string, string> = { analysis: 'Analysis', polish: 'Polish', generation: 'Generation', export: 'Manual export' }
const steps: { id: Step; number: string; label: string }[] = [{ id: 'analysis', number: '01', label: 'Analysis' }, { id: 'characters', number: '02', label: 'Characters' }, { id: 'prompt', number: '03', label: 'Prompt' }, { id: 'review', number: '04', label: 'Review' }, { id: 'generate', number: '05', label: 'Generate' }]
const stepFor: Record<string, Step> = { needs_analysis: 'analysis', analysing: 'analysis', review_analysis: 'analysis', needs_mapping: 'characters', analysis_ready: 'prompt', polishing: 'prompt', prompt_saved: 'review', approved: 'generate', generating: 'generate', generated: 'generate', waiting_analysis: 'analysis', waiting_generation: 'generate' }
const formatDate = (value: string) => new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value))
const fieldName = (field: string) => field.replace(/_/g, ' ').split(/\s*\.\s*/).map(part => sentence(part.trim())).join(' · ')

function Icon({ name }: { name: 'back' | 'copy' | 'spark' | 'edit' | 'clock' | 'folder' | 'arrow' }) {
  const paths = {
    back: <path d="M15 5l-7 7 7 7" />,
    copy: <><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V6a2 2 0 0 1 2-2h8" /></>,
    spark: <path d="M12 3l1.8 4.6L18.5 9.5l-4.7 1.9L12 16l-1.8-4.6L5.5 9.5l4.7-1.9z" />,
    edit: <path d="M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4" />,
    clock: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></>,
    folder: <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />,
    arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  }
  return <svg className="inline-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>
}

export function StageChip({ state }: { state: string }) {
  return <span className={`stage-chip stage-${state}`}>{stageLabels[state] ?? state}</span>
}

function copyText(text: string, done: (message: string) => void) {
  navigator.clipboard.writeText(text).then(() => done('Copied to the clipboard.'), () => done('Copy failed. Select the text and copy it yourself.'))
}

function Elapsed({ since }: { since: string | null }) {
  const [, tick] = useState(0)
  useEffect(() => { const timer = window.setInterval(() => tick(t => t + 1), 1000); return () => window.clearInterval(timer) }, [])
  if (!since) return <span>Starting…</span>
  const seconds = Math.max(0, Math.round((Date.now() - new Date(since).getTime()) / 1000))
  return <span>{Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}</span>
}

function Field({ label, value, flagged }: { label: string; value: string; flagged?: boolean }) {
  return <div className={`analysis-field ${flagged ? 'flagged' : ''}`}><dt>{label}{flagged && <span className="flag-dot" title="Needs your confirmation" />}</dt><dd>{sentence(value) || '—'}</dd></div>
}

// Engines name uncertain fields freely ("Subject 1.eye_direction", "subjects[0].eye direction"),
// so match on the field words plus the subject or camera they mention.
function flagMatcher(fields: string[], subjectCount: number) {
  const names = fields.map(f => f.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim())
  return (key: string, scope: 'camera' | 'scene' | number) => names.some(f => {
    if (!f.includes(key.replace(/_/g, ' '))) return false
    if (scope === 'camera') return f.includes('camera')
    if (scope === 'scene') return !f.includes('subject')
    return f.includes(`subject ${scope + 1}`) || f.includes(`subjects ${scope}`) || (subjectCount === 1 && !f.includes('subject') && !f.includes('camera'))
  })
}

function AnalysisView({ data, flagged }: { data: AnalysisData; flagged: Set<string> }) {
  const isFlagged = flagMatcher([...flagged], data.subjects.length)
  return <div className="analysis-view">
    <p className="analysis-summary">{sentence(data.scene_description)}</p>
    <dl className="field-grid compact">
      <Field label="Orientation" value={`${data.image_properties.orientation} · ${data.image_properties.approximate_aspect_ratio}`} />
      <Field label="Style" value={data.image_properties.style} />
    </dl>
    <h4>Camera</h4>
    <dl className="field-grid">{cameraFields.map(([key, label]) => <Field key={key} label={label} value={data.camera[key]} flagged={isFlagged(key, 'camera')} />)}</dl>
    {data.subjects.map(s => <section key={s.label} className="subject-card" aria-label={s.label}>
      <h4>{s.label}</h4>
      <dl className="field-grid">{subjectFields.map(([key, label]) => <Field key={key} label={label} value={s[key]} flagged={isFlagged(key, data.subjects.indexOf(s))} />)}</dl>
    </section>)}
    {!data.subjects.length && <p className="hint">No people were found in this image.</p>}
    <h4>Scene</h4>
    <dl className="field-grid">{sceneFields.map(([key, label]) => <Field key={key} label={label} value={data[key]} flagged={isFlagged(key, 'scene')} />)}</dl>
    {!!data.composition_constraints.length && <><h4>Must preserve</h4><ul className="plain-list">{data.composition_constraints.map((c, i) => <li key={i}>{sentence(c)}</li>)}</ul></>}
  </div>
}

function AnalysisEditor({ draft, onChange }: { draft: AnalysisData; onChange: (next: AnalysisData) => void }) {
  const update = (change: (next: AnalysisData) => void) => { const next = clone(draft); change(next); onChange(next) }
  const area = (id: string, label: string, value: string, set: (v: string, next: AnalysisData) => void, rows = 2) => <div key={id}><label htmlFor={id}>{label}</label><textarea id={id} rows={rows} maxLength={4000} value={value} onChange={e => update(next => set(e.target.value, next))} /></div>
  return <div className="analysis-editor">
    {area('edit-summary', 'Scene description', draft.scene_description, (v, n) => { n.scene_description = v }, 3)}
    <h4>Camera</h4>
    <div className="edit-grid">{cameraFields.map(([key, label]) => area(`edit-camera-${key}`, label, draft.camera[key], (v, n) => { n.camera[key] = v }))}</div>
    {draft.subjects.map((s, i) => <section key={s.label} className="subject-card"><h4>{s.label}</h4>
      <div className="edit-grid">{subjectFields.map(([key, label]) => area(`edit-${i}-${key}`, label, s[key], (v, n) => { n.subjects[i][key] = v }))}</div></section>)}
    <h4>Scene</h4>
    <div className="edit-grid">{sceneFields.map(([key, label]) => area(`edit-${key}`, label, draft[key], (v, n) => { n[key] = v }))}</div>
    {area('edit-constraints', 'Must preserve (one per line)', draft.composition_constraints.join('\n'), (v, n) => { n.composition_constraints = v.split('\n').map(x => x.trim()).filter(Boolean) }, 3)}
  </div>
}

const MAX_NEW_SCENES = 30
const titleFrom = (file: File) => file.name.replace(/\.[^.]+$/, '').trim().slice(0, 120) || 'Untitled scene'

/** One Base Image opens its new scene; several become one scene each (Phase 5.5). */
function NewSceneForm({ data, onCreated, onCreatedMany, onCancel }: { data: Bootstrap; onCreated: (scene: SceneDetail) => void; onCreatedMany: (created: SceneDetail[], failed: string[]) => void; onCancel: () => void }) {
  const [files, setFiles] = useState<File[]>([])
  const [titles, setTitles] = useState<string[]>([])
  const [previews, setPreviews] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(0)
  const [error, setError] = useState('')
  useEffect(() => { const urls = files.map(f => URL.createObjectURL(f)); setPreviews(urls); return () => urls.forEach(u => URL.revokeObjectURL(u)) }, [files])
  const limitMb = Math.floor(data.max_upload_bytes / 1048576)
  function choose(list: FileList | null) {
    const chosen = [...(list ?? [])]
    if (!chosen.length) return
    setError(chosen.length > MAX_NEW_SCENES ? `You chose ${chosen.length} images. Up to ${MAX_NEW_SCENES} are added at a time, so the first ${MAX_NEW_SCENES} are listed.` : '')
    const kept = chosen.slice(0, MAX_NEW_SCENES)
    setFiles(kept); setTitles(kept.length === 1 ? [''] : kept.map(titleFrom))
  }
  const remove = (index: number) => { setFiles(f => f.filter((_, i) => i !== index)); setTitles(t => t.filter((_, i) => i !== index)) }
  const create = (file: File, title: string) => request<SceneDetail>(`/api/scenes?title=${encodeURIComponent(title.trim() || titleFrom(file))}`, {
    method: 'POST', headers: { 'X-Studio-Token': data.session_token, 'Content-Type': 'application/octet-stream' }, body: file,
  }, 'Check the title and image, then try again.')
  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!files.length || busy) return
    const large = files.filter(f => f.size > data.max_upload_bytes)
    if (large.length) { setError(`${large.map(f => f.name).join(', ')} ${large.length === 1 ? 'is' : 'are'} larger than ${limitMb} MB. Remove ${large.length === 1 ? 'it' : 'them'} first.`); return }
    setBusy(true); setError(''); setDone(0)
    if (files.length === 1) {
      try { onCreated(await create(files[0], titles[0] ?? '')) }
      catch (e) { setError(e instanceof Error ? e.message : 'The scene could not be created.') }
      finally { setBusy(false) }
      return
    }
    // One at a time, like single uploads, so every file passes the same checks.
    const created: SceneDetail[] = [], failed: string[] = []
    for (const [index, file] of files.entries()) {
      try { created.push(await create(file, titles[index])) } catch (e) { failed.push(`${file.name} (${e instanceof Error ? e.message : 'not added'})`) }
      setDone(index + 1)
    }
    setBusy(false)
    onCreatedMany(created, failed)
  }
  const many = files.length > 1
  return <form className="new-scene" onSubmit={e => void submit(e)}>
    <h2 id="new-scene-title">{many ? `${files.length} new scenes` : 'New scene'}</h2>
    <p className="hint">Choose the Base Image whose composition you want to recreate, or several to make a scene from each. Images stay on this computer until you choose to analyse them.</p>
    <fieldset disabled={busy}>
      {many ? <div className="new-scenes">
        <ol className="new-scene-list">{files.map((file, index) => <li key={`${file.name}-${index}`} className={file.size > data.max_upload_bytes ? 'too-large' : ''}>
          <img src={previews[index]} alt="" />
          <div><label htmlFor={`new-title-${index}`} className="visually-hidden">Title for {file.name}</label>
            <input id={`new-title-${index}`} maxLength={120} value={titles[index] ?? ''} placeholder={titleFrom(file)} onChange={e => setTitles(t => t.map((x, i) => i === index ? e.target.value : x))} />
            {file.size > data.max_upload_bytes && <small className="frame-error">Larger than {limitMb} MB</small>}</div>
          <button type="button" className="secondary compact icon-only" aria-label={`Remove ${file.name}`} onClick={() => remove(index)}>×</button>
        </li>)}</ol>
        <label className="link-button change-files">Choose other images<input className="visually-hidden" type="file" multiple accept="image/jpeg,image/png,image/webp" onChange={e => choose(e.target.files)} /></label>
      </div> : <div className="new-scene-body">
        <label className={`drop-zone ${previews[0] ? 'has-image' : ''}`}>
          <input className="visually-hidden" type="file" multiple accept="image/jpeg,image/png,image/webp" required={!files.length} onChange={e => choose(e.target.files)} />
          {previews[0] ? <img src={previews[0]} alt="Selected Base Image" /> : <span><strong>Choose Base Images</strong><small>One or several · JPEG, PNG or WebP · up to {limitMb} MB each</small></span>}
        </label>
        <div><label htmlFor="scene-title">Scene title</label><input id="scene-title" maxLength={120} value={titles[0] ?? ''} placeholder={files[0] ? titleFrom(files[0]) : 'For example: Garden bench'} onChange={e => setTitles([e.target.value])} />
          <p className="hint">Optional. The file name is used if you leave it empty.</p></div>
      </div>}
    </fieldset>
    {error && <p className="frame-error" role="alert">{error}</p>}
    <div className="dialog-actions">{busy && many && <span className="spacer hint" role="status">Adding {Math.min(done + 1, files.length)} of {files.length}…</span>}
      <button type="button" className="secondary" disabled={busy} onClick={onCancel}>Cancel</button>
      <button disabled={!files.length || busy}>{busy ? 'Creating…' : many ? `Create ${files.length} scenes` : 'Create scene'}</button></div>
  </form>
}

function ManualAnalysis({ scene, token, onImported, onClose }: { scene: SceneSummary; token: string; onImported: (scene: SceneDetail) => void; onClose: () => void }) {
  const [instruction, setInstruction] = useState('')
  const [text, setText] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { request<{ manual_instruction: string }>('/api/analysis/instructions').then(r => setInstruction(r.manual_instruction), e => setError(e.message)) }, [])
  async function submit() {
    setBusy(true); setError('')
    try { onImported(await send<SceneDetail>(`/api/scenes/${scene.id}/analyses`, 'POST', token, { text })) }
    catch (e) { setError(e instanceof Error ? e.message : 'The analysis could not be imported.') }
    finally { setBusy(false) }
  }
  return <div className="manual-analysis">
    <h2 id="manual-title">Analyse manually</h2>
    <p className="hint">Use any chat app you already have, such as Claude or ChatGPT. Nothing is sent from the studio.</p>
    <ol className="manual-steps">
      <li><strong>Copy the instruction.</strong> It includes the exact format the studio expects.
        <div className="step-actions"><button type="button" className="secondary" disabled={!instruction} onClick={() => copyText(instruction, setNote)}><Icon name="copy" /> Copy instruction</button></div></li>
      <li><strong>Attach the Base Image</strong> in the other app together with the instruction.
        <div className="step-actions"><a className="button-link secondary" href={scene.original_url} download={`${scene.title}`}>Save Base Image</a></div></li>
      <li><strong>Paste the whole reply here.</strong>
        <label htmlFor="manual-reply" className="visually-hidden">Analysis reply</label>
        <textarea id="manual-reply" rows={8} value={text} placeholder='{ "schema_version": 1, … }' onChange={e => setText(e.target.value)} /></li>
    </ol>
    <p className="library-status" role="status">{note}</p>
    {error && <p className="frame-error" role="alert">{error}</p>}
    <div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Cancel</button><button type="button" disabled={!text.trim() || busy} onClick={() => void submit()}>{busy ? 'Checking…' : 'Import analysis'}</button></div>
  </div>
}

function JobNotice({ job, onRetry, onManual, manualLabel, onDismiss, busy, extra }: { job: Job; onRetry: () => void; onManual: () => void; manualLabel: string; onDismiss: () => void; busy: boolean; extra?: ReactNode }) {
  const [note, setNote] = useState('')
  const polish = job.kind === 'polish'
  const generation = job.kind === 'generation'
  const titles: Record<string, string> = polish
    ? { failed: `${job.engine_name} could not polish the prompt`, cancelled: 'Polishing cancelled', interrupted: 'Polishing was interrupted' }
    : generation ? { failed: `${job.engine_name} could not generate the image`, cancelled: 'Generation cancelled', interrupted: 'The generation was interrupted' }
      : { failed: `${job.engine_name} could not finish the analysis`, cancelled: 'Analysis cancelled', interrupted: 'The analysis was interrupted' }
  return <div className={`job-notice ${job.status}`} role="alert">
    <strong>{titles[job.status] ?? 'The run did not finish'}</strong>
    <p>{job.error_details}{polish ? ' Your prompt is unchanged.' : ''}{generation && job.status === 'cancelled' ? ' The request may already have reached OpenAI and used some allowance, and Codex may have saved an image.' : ''}</p>
    {(job.status === 'interrupted' || (generation && job.recoverable)) && job.job_folder && <p className="folder-line"><Icon name="folder" /> <code>{job.job_folder}</code> <button type="button" className="link-button" onClick={() => copyText(job.job_folder!, setNote)}>Copy path</button></p>}
    <span className="library-status" role="status">{note}</span>
    <div className="notice-actions">
      <button type="button" disabled={busy} onClick={onRetry}>{job.status === 'interrupted' ? 'I checked — try again' : 'Try again'}</button>
      {extra}
      <button type="button" className="secondary" onClick={onManual}>{manualLabel}</button>
      <button type="button" className="link-button" onClick={onDismiss}>Dismiss</button>
    </div>
  </div>
}

function ProgressCard({ job, stopping, busy, onCancel }: { job: Job; stopping: boolean; busy: boolean; onCancel: () => void }) {
  const verb = job.kind === 'polish' ? 'Polishing' : job.kind === 'generation' ? 'Generating' : 'Analysing'
  const batch = job.batch
  const place = batch ? `Item ${batch.position} of ${batch.total} in a batch` : ''
  if (batch && job.status === 'not_started' && !stopping) {
    const paused = batch.status === 'paused'
    return <div className={`progress-card waiting ${paused ? 'paused' : ''}`} role="status">
      <span className={paused ? 'pause-mark' : 'spinner'} aria-hidden="true" />
      <div><strong>{paused ? 'Waiting in a paused batch' : `Waiting for its turn with ${job.engine_name}…`}</strong>
        <p>{place}. {paused ? 'It starts only when you continue the batch.' : 'Runs go one at a time.'} Nothing has been sent for it yet. Remove it from the batch to edit the scene.</p></div>
      <button className="secondary" disabled={busy} onClick={onCancel}>Remove from batch</button>
    </div>
  }
  return <div className="progress-card" role="status">
    <span className="spinner" aria-hidden="true" />
    {stopping ? <div><strong>Stopping…</strong><p>Stopping {job.engine_name}. This takes a moment.</p></div>
      : <div><strong>{job.status === 'not_started' ? `Waiting to start with ${job.engine_name}…` : `${verb} with ${job.engine_name}…`}</strong>
        <p><Icon name="clock" /> <Elapsed since={job.started_at} /> · stops after {Math.round(job.timeout_seconds / 60)} min{place ? ` · ${place}` : ''}. You can leave this page; the run continues.</p></div>}
    <button className="secondary" disabled={busy || stopping} onClick={onCancel}>{stopping ? 'Stopping…' : 'Cancel'}</button>
  </div>
}

function StepTabs({ step, onStep, status }: { step: Step; onStep: (step: Step) => void; status: Record<Step, 'done' | 'todo' | 'idle'> }) {
  function key(e: KeyboardEvent<HTMLDivElement>) {
    const index = steps.findIndex(s => s.id === step)
    const next = e.key === 'ArrowRight' ? index + 1 : e.key === 'ArrowLeft' ? index - 1 : e.key === 'Home' ? 0 : e.key === 'End' ? steps.length - 1 : -2
    if (next === -2) return
    e.preventDefault()
    const target = steps[(next + steps.length) % steps.length]
    onStep(target.id)
    requestAnimationFrame(() => document.getElementById(`step-tab-${target.id}`)?.focus())
  }
  return <div className="step-tabs" role="tablist" aria-label="Scene steps" onKeyDown={key}>
    {steps.map(s => <button key={s.id} id={`step-tab-${s.id}`} type="button" role="tab" aria-selected={step === s.id} aria-controls={`step-panel-${s.id}`} tabIndex={step === s.id ? 0 : -1}
      className={`step-tab ${step === s.id ? 'active' : ''} ${status[s.id]}`} onClick={() => onStep(s.id)}>
      <span className="step-tab-number">{status[s.id] === 'done' ? '✓' : s.number}</span>{s.label}
    </button>)}
  </div>
}

function Workspace({ data, sceneId, onBack, onOpen, onDirty, onBusy, onChanged }: { data: Bootstrap; sceneId: string; onBack: () => void; onOpen: (id: string) => void; onDirty: (dirty: boolean) => void; onBusy: (busy: boolean) => void; onChanged: () => void }) {
  const token = data.session_token
  const [scene, setScene] = useState<SceneDetail | null>(null)
  const [engines, setEngines] = useState<EngineSettings | null>(null)
  const [characters, setCharacters] = useState<Character[]>([])
  const [groups, setGroups] = useState<Group[]>([])
  const [step, setStepState] = useState<Step | null>(() => { const s = routeParts()[2]; return steps.some(x => x.id === s) ? s as Step : null })
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [viewing, setViewing] = useState<string | null>(null)
  const [editing, setEditing] = useState<AnalysisData | null>(null)
  const [confirmed, setConfirmed] = useState<Uncertainty[]>([])
  const [showBoxes, setShowBoxes] = useState(true)
  const [manual, setManual] = useState(false)
  // API engines: the charge confirmation shown before a run is queued.
  const [chargeAsk, setChargeAsk] = useState<{ note?: string } | null>(null)
  const apiEngines = useApiEngines()
  const [renaming, setRenaming] = useState(false)
  const [title, setTitle] = useState('')
  const [dismissed, setDismissed] = useState<string[]>([])
  const [stopping, setStopping] = useState<string | null>(null)
  const [promptText, setPromptText] = useState('')
  const [negative, setNegative] = useState('')
  const [changes, setChanges] = useState('')
  const [promptBase, setPromptBase] = useState<{ text: string; negative: string; changes: string; analysisId: string | null; mappingHash: string | null; source: 'template' | 'user_edit' | 'restored'; saved: boolean } | null>(null)
  // Where the editor text came from, so an unchanged template draft or restore is labelled honestly.
  const [origin, setOrigin] = useState<{ text: string; source: 'template' | 'restored' } | null>(null)
  const [mappingDirty, setMappingDirty] = useState(false)
  const [highlight, setHighlight] = useState<string | null>(null)
  const [boxes, setBoxes] = useState<BoxDraft[] | null>(null)
  const [polishOpen, setPolishOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const manualRef = useRef<HTMLDialogElement>(null)
  const promptRef = useRef<HTMLTextAreaElement>(null)
  const lock = useRef(false)

  const current = scene?.analyses[0] ?? null
  const shown = scene?.analyses.find(a => a.id === viewing) ?? current
  const latestPrompt = scene?.prompts[0] ?? null
  const promptDirty = !!promptBase && (promptText !== promptBase.text || negative !== promptBase.negative || changes !== promptBase.changes)
  const boxesDirty = !!boxes && !!current && JSON.stringify(boxes) !== JSON.stringify(current.analysis.subjects.map(s => ({ label: s.label, bounding_box: s.bounding_box })))
  const dirty = !!editing || promptDirty || mappingDirty || boxesDirty || renaming && title !== scene?.title
  const promptDirtyRef = useRef(false)
  promptDirtyRef.current = promptDirty
  useEffect(() => { onDirty(dirty); return () => onDirty(false) }, [dirty, onDirty])
  useEffect(() => { onBusy(busy); return () => onBusy(false) }, [busy, onBusy])
  useEffect(() => { if (manual) { if (!manualRef.current?.open) manualRef.current?.showModal() } else manualRef.current?.close() }, [manual])
  const activeStep: Step = step ?? (scene ? stepFor[scene.workflow_state] ?? 'analysis' : 'analysis')
  // Open on the step the saved stage suggests, then stay put: only the user changes steps.
  useEffect(() => { if (scene && step === null) setStepState(activeStep) }, [scene, step, activeStep])
  useEffect(() => { if (scene) replaceRoute(`scenes/${scene.id}/${activeStep}`) }, [scene?.id, activeStep])

  const loadLibrary = useCallback(() => {
    Promise.all([request<Character[]>('/api/characters'), request<Group[]>('/api/groups')]).then(([c, g]) => { setCharacters(c); setGroups(g) }, () => undefined)
  }, [])
  // Names and photos for the image tags and pickers; refreshed when a step that edits them opens.
  useEffect(() => { loadLibrary() }, [loadLibrary])
  useEffect(() => { if (activeStep === 'characters' || activeStep === 'review') loadLibrary() }, [activeStep, loadLibrary])

  const loadPrompt = useCallback(async (detail: SceneDetail) => {
    const saved = detail.prompts[0]
    if (saved) {
      setPromptText(saved.prompt_text); setNegative(saved.negative_prompt); setChanges(saved.scene_changes)
      setPromptBase({ text: saved.prompt_text, negative: saved.negative_prompt, changes: saved.scene_changes, analysisId: saved.analysis_id, mappingHash: saved.mapping_hash, source: 'user_edit', saved: true })
      setOrigin(null)
    } else if (detail.analyses[0]) {
      const draft = await send<{ prompt_text: string; negative_prompt: string; mapping_hash: string }>(`/api/scenes/${detail.id}/prompts/draft`, 'POST', token, { analysis_id: detail.analyses[0].id, scene_changes: '' })
      setPromptText(draft.prompt_text); setNegative(draft.negative_prompt); setChanges('')
      setPromptBase({ text: draft.prompt_text, negative: draft.negative_prompt, changes: '', analysisId: detail.analyses[0].id, mappingHash: draft.mapping_hash, source: 'template', saved: false })
      setOrigin({ text: draft.prompt_text, source: 'template' })
    } else { setPromptBase(null); setPromptText(''); setNegative(''); setChanges('') }
  }, [token])

  const accept = useCallback(async (detail: SceneDetail, refreshPrompt = true) => {
    setScene(detail); setTitle(detail.title); setViewing(null)
    if (refreshPrompt) await loadPrompt(detail)
    onChanged()
  }, [loadPrompt, onChanged])

  useEffect(() => {
    let active = true
    Promise.all([request<SceneDetail>(`/api/scenes/${sceneId}`), request<EngineSettings>('/api/engines/settings')])
      .then(async ([detail, settings]) => { if (!active) return; setEngines(settings); await accept(detail); send(`/api/scenes/${sceneId}/opened`, 'POST', token).catch(() => undefined) })
      .catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [sceneId])

  // Poll only while a run is waiting or running; the run itself lives on the server.
  const activeJob = scene?.active_job ?? null
  useEffect(() => {
    if (!activeJob) return
    const timer = window.setInterval(async () => {
      try {
        const job = await request<Job>(`/api/jobs/${activeJob.id}`)
        if (job.status === 'not_started' || job.status === 'running') {
          // A batch item that has just started leaves its "Waiting" stage.
          const started = job.status === 'running' ? { analysis: 'analysing', polish: 'polishing', generation: 'generating' }[job.kind] : undefined
          setScene(s => s && { ...s, active_job: job, workflow_state: started && s.workflow_state.startsWith('waiting_') ? started : s.workflow_state })
          return
        }
        const detail = await request<SceneDetail>(`/api/scenes/${sceneId}`)
        await accept(detail, !promptDirtyRef.current)
        if (job.status === 'completed' && job.kind === 'polish') { setMessage('The polished prompt is ready to compare.'); if (detail.pending_polish) setPolishOpen(true) }
        else if (job.status === 'completed' && job.kind === 'generation') setMessage(`Result ${detail.results[0]?.version} saved. Open it to compare with the Base Image.`)
        else if (job.status === 'completed') setMessage(`Analysis version ${detail.analyses[0]?.version} saved.`)
      } catch { /* keep polling; the run continues on the server */ }
    }, 1500)
    return () => window.clearInterval(timer)
  }, [activeJob?.id])

  async function run(action: () => Promise<void>, success = '') {
    if (lock.current) return
    lock.current = true; setBusy(true); setError(''); setMessage('')
    try { await action(); setMessage(success) }
    catch (e) { setError(e instanceof Error ? e.message : 'That did not work. Your edits are still here.') }
    finally { lock.current = false; setBusy(false) }
  }
  const runAction = useCallback((action: () => Promise<void>, success: string) => { void run(action, success) }, [])
  function guard() { return !dirty || window.confirm('Discard unsaved edits?') }
  const setStep = (next: Step) => { if (boxes && next !== 'characters' && boxesDirty && !window.confirm('Discard your changes to the subject boxes?')) return; if (next !== 'characters') setBoxes(null); setStepState(next) }

  if (!scene) return <div>{error ? <div className="error" role="alert"><strong>This scene could not be opened.</strong><p>{error}</p><button className="secondary" onClick={onBack}>Back to scenes</button></div> : <p role="status">Opening scene…</p>}</div>

  const engine = engines?.analysis_engine ?? 'claude_cli'
  const lastAnalysisJob = scene.jobs.find(j => j.kind === 'analysis')
  const lastPolishJob = scene.jobs.find(j => j.kind === 'polish')
  const lastGenerationJob = scene.jobs.find(j => j.kind === 'generation')
  // Hidden once an image from that run was recovered: the result answers the notice.
  const showGenerationNotice = !scene.active_job && !!lastGenerationJob && lastGenerationJob.status !== 'completed' && !dismissed.includes(lastGenerationJob.id) && !scene.results.some(r => r.job_id === lastGenerationJob.id)
  const showJobNotice = !scene.active_job && !!lastAnalysisJob && lastAnalysisJob.status !== 'completed' && !dismissed.includes(lastAnalysisJob.id) && (!current || lastAnalysisJob.created_at > current.created_at)
  const showPolishNotice = !scene.active_job && !!lastPolishJob && lastPolishJob.status !== 'completed' && !dismissed.includes(lastPolishJob.id) && lastPolishJob.input_id === latestPrompt?.id
  const flagged = new Set((shown?.analysis.uncertainties ?? []).map(u => u.field))
  const promptStale = !!latestPrompt && !!current && latestPrompt.analysis_id !== current.id && promptBase?.saved
  const mappingStale = !promptStale && !!latestPrompt && promptBase?.saved && latestPrompt.mapping_hash !== scene.mapping_hash && !(latestPrompt.mapping_hash === null && !scene.subjects.length)
  const approved = scene.approval.state === 'approved'
  const byId = Object.fromEntries(characters.map(c => [c.id, c]))
  const names = Object.fromEntries(scene.subjects.map(s => [s.label, s.action === 'replace' && s.character_id ? byId[s.character_id] : undefined]))
  const canvasBoxes: BoxDraft[] = boxes ?? (activeStep === 'analysis' ? shown?.analysis.subjects ?? [] : current?.analysis.subjects ?? []).map(s => ({ label: s.label, bounding_box: s.bounding_box }))
  const status: Record<Step, 'done' | 'todo' | 'idle'> = {
    analysis: !current ? 'todo' : current.analysis.uncertainties.length ? 'todo' : 'done',
    characters: !current ? 'idle' : scene.subjects.every(s => !s.problems.length) && scene.subjects.every(s => s.action === 'unresolved' || s.confirmed) ? 'done' : 'todo',
    prompt: !current ? 'idle' : ['prompt_saved', 'approved', 'generating', 'generated', 'waiting_generation'].includes(scene.workflow_state) ? 'done' : 'todo',
    review: approved ? 'done' : scene.workflow_state === 'prompt_saved' ? 'todo' : 'idle',
    generate: scene.results.some(r => r.approval_current) ? 'done' : approved ? 'todo' : 'idle',
  }
  const confirmApprovedEdit = (what: string) => !approved || window.confirm(`${what} cancels the current approval. Continue?`)

  const analyse = (confirmed = false, note?: string) => {
    if (isApiEngine(engine) && !confirmed) { void apiEngines.reload(); setChargeAsk({ note }); return }
    return run(async () => {
      if (lastAnalysisJob) setDismissed(d => [...d, lastAnalysisJob.id])
      const detail = await send<SceneDetail>(`/api/scenes/${scene.id}/analyse`, 'POST', token, isApiEngine(engine) ? { confirm_charges: true } : undefined)
      setScene(detail); onChanged()
    })
  }
  const againNote = `The current analysis is kept as a version${approved ? ', and the approval is cancelled when the new analysis arrives' : ''}.`
  const cancel = () => {
    const job = scene.active_job
    if (!job) return
    // Show "Stopping…" at once; the server stops the CLI and the poll picks up the result.
    setStopping(job.id)
    void run(async () => { await send(`/api/jobs/${job.id}/cancel`, 'POST', token) })
  }
  const startEdit = () => { if (shown) { setEditing(clone(shown.analysis)); setConfirmed(shown.confirmed_uncertainties) } }
  const saveRevision = (analysis: AnalysisData, confirmedList: Uncertainty[], base: Analysis, success: string) => {
    if (!confirmApprovedEdit('Changing the analysis')) return
    void run(async () => {
      await accept(await send<SceneDetail>(`/api/scenes/${scene.id}/analyses/${base.id}/revise`, 'POST', token, { analysis, confirmed_uncertainties: confirmedList }), !promptDirty)
      setEditing(null)
    }, success)
  }
  const confirmUncertainty = (item: Uncertainty) => {
    if (!current) return
    const next = clone(current.analysis)
    next.uncertainties = next.uncertainties.filter(u => !(u.field === item.field && u.note === item.note))
    saveRevision(next, [...current.confirmed_uncertainties, item], current, `Confirmed. Saved as analysis version ${current.version + 1}.`)
  }
  const rebuild = (analysisId: string, sceneChanges: string) => run(async () => {
    const draft = await send<{ prompt_text: string; negative_prompt: string; mapping_hash: string }>(`/api/scenes/${scene.id}/prompts/draft`, 'POST', token, { analysis_id: analysisId, scene_changes: sceneChanges })
    setPromptText(draft.prompt_text); setNegative(draft.negative_prompt)
    setPromptBase(b => b && { ...b, analysisId, mappingHash: draft.mapping_hash })
    setOrigin({ text: draft.prompt_text, source: 'template' })
  }, 'Draft rebuilt from the analysis and assignments. Save it to keep it.')
  const savePrompt = () => {
    if (!confirmApprovedEdit('Saving a new prompt version')) return
    void run(async () => {
      const source = origin && promptText === origin.text ? origin.source : 'user_edit'
      const detail = await send<SceneDetail>(`/api/scenes/${scene.id}/prompts`, 'POST', token, { analysis_id: promptBase?.analysisId ?? current?.id ?? null, mapping_hash: promptBase?.mappingHash ?? null, prompt_text: promptText, negative_prompt: negative, scene_changes: changes, source })
      await accept(detail)
    }, 'Prompt version saved.')
  }
  const restorePrompt = (prompt: Prompt) => {
    if (!guard()) return false
    if (prompt.id === latestPrompt?.id) {
      // The current version: show it exactly as saved rather than as an unsaved restore.
      setPromptText(prompt.prompt_text); setNegative(prompt.negative_prompt); setChanges(prompt.scene_changes)
      setPromptBase({ text: prompt.prompt_text, negative: prompt.negative_prompt, changes: prompt.scene_changes, analysisId: prompt.analysis_id, mappingHash: prompt.mapping_hash, source: 'user_edit', saved: true })
      setOrigin(null)
      setMessage(`Version ${prompt.version} is the current prompt and is shown in the editor.`)
      return true
    }
    setPromptText(prompt.prompt_text); setNegative(prompt.negative_prompt); setChanges(prompt.scene_changes)
    setPromptBase({ text: prompt.prompt_text, negative: prompt.negative_prompt, changes: prompt.scene_changes, analysisId: prompt.analysis_id, mappingHash: prompt.mapping_hash, source: 'restored', saved: false })
    setOrigin({ text: prompt.prompt_text, source: 'restored' })
    setMessage(`Version ${prompt.version} loaded into the editor. Save to make it the current prompt.`)
    return true
  }
  const polish = () => {
    if (!latestPrompt) return
    if (approved && !window.confirm('Polishing is fine while approved, but using the polished version creates a new prompt version and cancels the approval. Continue?')) return
    void run(async () => {
      if (lastPolishJob) setDismissed(d => [...d, lastPolishJob.id])
      const detail = await send<SceneDetail>(`/api/scenes/${scene.id}/polish`, 'POST', token, { prompt_id: latestPrompt.id })
      setScene(detail); onChanged()
    })
  }
  const generate = (mode: 'generate' | 'variation', count = 1) => run(async () => {
    if (lastGenerationJob) setDismissed(d => [...d, lastGenerationJob.id])
    if (count > 1) {
      // Several images from this one approval: a batch for this scene (Phase 5.5).
      await send<BatchStart>('/api/batches/generation', 'POST', token, { items: [{ scene_id: scene.id, approval_id: scene.approval.current?.id }], count, mode })
      setScene(await request<SceneDetail>(`/api/scenes/${scene.id}`)); onChanged()
      return
    }
    const detail = await send<SceneDetail>(`/api/scenes/${scene.id}/generate`, 'POST', token, { approval_id: scene.approval.current?.id, mode })
    setScene(detail); onChanged()
  }, count > 1 ? `${count} images queued. They run one after another.` : '')
  const recover = (job: Job) => run(async () => {
    const found = await send<{ found: number; scene: SceneDetail }>(`/api/jobs/${job.id}/recover`, 'POST', token)
    await accept(found.scene, false)
    if (!found.found) throw new Error('No saved image was found for this run. Codex probably stopped before the image was finished.')
  }, 'Found the saved image and kept it as a result.')
  const saveBoxes = () => {
    if (!boxes || !current) return
    if (!confirmApprovedEdit('Changing the subjects')) return
    void run(async () => {
      await accept(await send<SceneDetail>(`/api/scenes/${scene.id}/subjects`, 'PUT', token, { analysis_id: current.id, subjects: boxes }), !promptDirty)
      setBoxes(null)
    }, 'Subjects saved as a new analysis version. Assignments stay with their labels.')
  }
  const addSubject = () => {
    if (!boxes) return
    const used = boxes.map(b => Number(b.label.split(' ')[1]))
    const label = `Subject ${Math.max(0, ...used, ...(current?.analysis.subjects ?? []).map(s => Number(s.label.split(' ')[1]))) + 1}`
    setBoxes([...boxes, { label, bounding_box: { x: 0.4, y: 0.25, width: 0.2, height: 0.5 } }]); setHighlight(label)
  }

  const header: ReactNode = <div className="workspace-head">
    <button className="link-button back-link" disabled={busy} onClick={() => { if (guard()) onBack() }}><Icon name="back" /> All scenes</button>
    <div className="workspace-title">
      {renaming ? <form className="rename-form" onSubmit={e => { e.preventDefault(); void run(async () => { await accept(await send<SceneDetail>(`/api/scenes/${scene.id}`, 'PUT', token, { title: title.trim(), revision: scene.revision }), false); setRenaming(false) }, 'Scene renamed.') }}>
        <label htmlFor="rename-scene" className="visually-hidden">Scene title</label>
        <input id="rename-scene" autoFocus maxLength={120} value={title} onChange={e => setTitle(e.target.value)} />
        <button type="button" className="secondary" onClick={() => { setRenaming(false); setTitle(scene.title) }}>Cancel</button><button disabled={!title.trim() || title.trim() === scene.title || busy}>Save</button>
      </form> : <><h2>{scene.title}</h2><StageChip state={scene.workflow_state} /></>}
    </div>
    {!renaming && <div className="workspace-actions">
      <button className="secondary" disabled={busy} onClick={() => setRenaming(true)}>Rename</button>
      <button className="secondary" disabled={busy} onClick={() => { if (guard()) void run(async () => { const copy = await send<SceneDetail>(`/api/scenes/${scene.id}/duplicate`, 'POST', token); setEditing(null); onDirty(false); onChanged(); onOpen(copy.id) }) }}>Duplicate</button>
      <button className="danger secondary" disabled={busy || !!scene.active_job} title={scene.active_job ? 'Cancel the running job first' : undefined} onClick={() => { if (window.confirm(`Permanently delete “${scene.title}”, its Base Image, analyses, prompts, assignments, approvals, results and run folders? This cannot be undone.`)) void run(async () => { await send(`/api/scenes/${scene.id}?revision=${scene.revision}`, 'DELETE', token); onDirty(false); onBack() }) }}>Delete</button>
    </div>}
  </div>

  const next = (target: Step, label: string) => <div className="next-step"><button type="button" className="secondary" onClick={() => setStep(target)}>{label} <Icon name="arrow" /></button></div>

  return <div className="scene-workspace">
    {header}
    {error && <div className="error" role="alert"><strong>Could not finish that action.</strong><p>{error}</p></div>}
    <p className="library-status" role="status">{busy ? 'Working…' : message}</p>
    <div className="workspace-columns">
      <aside className="image-column">
        <div className="panel image-panel">
          <SubjectCanvas scene={scene} boxes={canvasBoxes} names={names} show={showBoxes || !!boxes} editing={!!boxes} selected={highlight}
            onSelect={activeStep === 'characters' ? setHighlight : undefined}
            onChange={(label, box) => setBoxes(old => old && old.map(b => b.label === label ? { ...b, bounding_box: box } : b))} />
          <div className="image-meta"><span>Image 1 · Base Image · {scene.width} × {scene.height}</span>
            {!boxes && !!canvasBoxes.length && <label className="checkbox-label"><input type="checkbox" checked={showBoxes} onChange={e => setShowBoxes(e.target.checked)} /> Show subjects</label>}</div>
          {boxes && <div className="adjust-bar">
            <p className="hint">Click a box to select it, drag it to move, and drag any side or corner handle to make it larger or smaller. With the keyboard: arrow keys move, Shift + arrow keys resize. Labels never renumber, so assignments stay with the same person.</p>
            <div className="adjust-actions">
              <button type="button" className="secondary" disabled={busy || boxes.length >= 20} onClick={addSubject}>+ Add subject</button>
              <button type="button" className="danger secondary" disabled={busy || !highlight || !boxes.some(b => b.label === highlight)} onClick={() => { setBoxes(boxes.filter(b => b.label !== highlight)); setHighlight(null) }}>Remove {highlight && boxes.some(b => b.label === highlight) ? highlight : 'selected'}</button>
            </div>
            <div className="panel-actions"><span className="spacer">{boxesDirty ? 'Unsaved changes' : 'No changes yet'}</span>
              <button type="button" className="secondary" disabled={busy} onClick={() => { if (!boxesDirty || window.confirm('Discard your changes to the subject boxes?')) setBoxes(null) }}>Cancel</button>
              <button type="button" disabled={busy || !boxesDirty} onClick={saveBoxes}>Save subjects</button></div>
          </div>}
        </div>
      </aside>
      <div className="steps-column">
        <StepTabs step={activeStep} onStep={setStep} status={status} />

        <section id="step-panel-analysis" role="tabpanel" aria-labelledby="step-tab-analysis" hidden={activeStep !== 'analysis'} className="panel step-panel">
          <div className="step-head"><span className="step-number">01</span><div><h3 id="analysis-heading">Scene analysis</h3><p className="hint">What the camera sees: people, poses, framing, light. Saved as versions.</p></div></div>

          {scene.active_job?.kind === 'analysis' ? <><ProgressCard job={scene.active_job} stopping={stopping === scene.active_job.id} busy={busy} onCancel={cancel} />{scene.active_job.batch && <BatchList token={token} sceneId={scene.id} />}</>
            : showJobNotice && lastAnalysisJob ? <JobNotice job={lastAnalysisJob} busy={busy || engine === 'manual' || !!scene.active_job} onRetry={() => void analyse()} onManual={() => setManual(true)} manualLabel="Do it manually" onDismiss={() => setDismissed(d => [...d, lastAnalysisJob.id])} /> : null}

          {!current && !scene.active_job && !showJobNotice && <div className="analyse-start">
            <p>{engine === 'manual' ? 'Manual analysis is selected in Studio settings. Copy the instruction into another app, then paste its reply here.' : isApiEngine(engine) ? <>Analyse sends the Base Image to {sendsTo[engine]}. It runs once, only after you confirm that it may be charged.</> : <>Analyse sends the Base Image to {sendsTo[engine]}, using your own sign-in and your plan's allowance. It runs once, only when you click.</>}</p>
            <div className="save-row">{engine !== 'manual' && <button disabled={busy} onClick={() => void analyse()}><Icon name="spark" /> Analyse with {engineLabels[engine]}</button>}
              <button className={engine === 'manual' ? '' : 'secondary'} onClick={() => setManual(true)}>Do it manually</button></div>
          </div>}

          {shown && !editing && <>
            <div className="version-bar">
              <label htmlFor="analysis-version" className="visually-hidden">Analysis version</label>
              <select id="analysis-version" value={shown.id} onChange={e => setViewing(e.target.value === current?.id ? null : e.target.value)}>
                {scene.analyses.map(a => <option key={a.id} value={a.id}>Version {a.version} · {sourceLabels[a.source] ?? a.source}{a.id === current?.id ? ' (current)' : ''}</option>)}
              </select>
              <span className="hint">{formatDate(shown.created_at)}{shown.engine_version ? ` · ${shown.engine_version}` : ''}</span>
              <span className="spacer" />
              {shown.id === current?.id ? <>
                <button className="secondary" disabled={busy || !!scene.active_job} onClick={startEdit}><Icon name="edit" /> Edit</button>
                {engine !== 'manual' && !showJobNotice && <button className="secondary" disabled={busy || !!scene.active_job} onClick={() => { if (isApiEngine(engine)) void analyse(false, `This sends the Base Image again. ${againNote}`); else if (window.confirm(`Analyse again with ${engineLabels[engine]}? This sends the Base Image again and uses your plan's allowance. ${againNote}`)) void analyse() }}>Analyse again</button>}
                {!showJobNotice && <button className="secondary" disabled={busy || !!scene.active_job} onClick={() => setManual(true)}>Import</button>}
              </> : <button className="secondary" disabled={busy || !!scene.active_job} onClick={() => current && saveRevision(shown.analysis, shown.confirmed_uncertainties, current, `Version ${shown.version} restored as the current analysis.`)}>Restore as current</button>}
            </div>
            {shown.id !== current?.id && <p className="notice-line">You are viewing an earlier version. The current one is version {current?.version}.</p>}
            {!!shown.analysis.uncertainties.length && <div className="uncertain-box">
              <strong>Please check {shown.analysis.uncertainties.length === 1 ? 'this detail' : `these ${shown.analysis.uncertainties.length} details`}</strong>
              <p className="hint">The analysis was unsure here. Confirm it as written, or edit the analysis to correct it.</p>
              <ul>{shown.analysis.uncertainties.map((u, i) => <li key={i}><div><span className="field-name">{fieldName(u.field)}</span><span>{sentence(u.note)}</span></div>
                {shown.id === current?.id && <div className="uncertain-actions"><button className="secondary" disabled={busy || !!scene.active_job} onClick={() => confirmUncertainty(u)}>Confirm</button><button className="link-button" disabled={busy || !!scene.active_job} onClick={startEdit}>Correct</button></div>}</li>)}</ul>
            </div>}
            <AnalysisView data={shown.analysis} flagged={flagged} />
            {!!shown.confirmed_uncertainties.length && <details className="confirmed-list"><summary>Confirmed by you ({shown.confirmed_uncertainties.length})</summary><ul>{shown.confirmed_uncertainties.map((u, i) => <li key={i}><span className="field-name">{fieldName(u.field)}</span> {sentence(u.note)}</li>)}</ul></details>}
            {status.analysis === 'done' && next('characters', 'Next: assign characters')}
          </>}

          {editing && current && <>
            <p className="notice-line">Editing creates analysis version {current.version + 1}. Earlier versions are kept.</p>
            {!!editing.uncertainties.length && <div className="uncertain-box"><strong>Unsure details</strong><p className="hint">Untick a detail once you have corrected or checked it.</p>
              <ul>{current.analysis.uncertainties.map((u, i) => { const open = editing.uncertainties.some(x => x.field === u.field && x.note === u.note); return <li key={i}><label className="checkbox-label"><input type="checkbox" checked={open} onChange={() => {
                const next = clone(editing)
                next.uncertainties = open ? next.uncertainties.filter(x => !(x.field === u.field && x.note === u.note)) : [...next.uncertainties, u]
                setEditing(next); setConfirmed(c => open ? [...c, u] : c.filter(x => !(x.field === u.field && x.note === u.note)))
              }} /><span><span className="field-name">{fieldName(u.field)}</span> {sentence(u.note)}</span></label></li> })}</ul></div>}
            <AnalysisEditor draft={editing} onChange={setEditing} />
            <div className="panel-actions"><span className="spacer">Unsaved edits</span><button type="button" className="secondary" onClick={() => { if (window.confirm('Discard your edits to the analysis?')) setEditing(null) }}>Cancel</button><button type="button" disabled={busy} onClick={() => saveRevision(editing, confirmed, current, `Saved as analysis version ${current.version + 1}.`)}>Save as new version</button></div>
          </>}
        </section>

        <section id="step-panel-characters" role="tabpanel" aria-labelledby="step-tab-characters" hidden={activeStep !== 'characters'} className="panel step-panel">
          <div className="step-head"><span className="step-number">02</span><div><h3>Characters</h3><p className="hint">Choose who each person in the Base Image becomes, or keep them as they are. Click a box on the image to find its subject.</p></div></div>
          {boxes ? <p className="notice-line">Adjusting subjects. Save or cancel next to the image to continue assigning characters.</p>
            : <MappingPanel scene={scene} token={token} characters={characters} groups={groups} busy={busy} highlight={highlight} onHighlight={setHighlight} onDirty={setMappingDirty}
              onSaved={detail => accept(detail, !promptDirty)} onRun={runAction}
              onAdjust={() => { if (current) { setBoxes(current.analysis.subjects.map(s => ({ label: s.label, bounding_box: s.bounding_box }))); setShowBoxes(true); setHighlight(h => h ?? current.analysis.subjects[0]?.label ?? null) } }} />}
          {!boxes && status.characters === 'done' && !mappingDirty && next('prompt', 'Next: the prompt')}
        </section>

        <section id="step-panel-prompt" role="tabpanel" aria-labelledby="step-tab-prompt" hidden={activeStep !== 'prompt'} className="panel step-panel">
          <div className="step-head"><span className="step-number">03</span><div><h3 id="prompt-heading">Generation prompt</h3><p className="hint">Built by the studio from the analysis and your assignments. Edit freely; every save is a version.</p></div></div>
          {scene.active_job?.kind === 'polish' ? <ProgressCard job={scene.active_job} stopping={stopping === scene.active_job.id} busy={busy} onCancel={cancel} />
            : showPolishNotice && lastPolishJob ? <JobNotice job={lastPolishJob} busy={busy} onRetry={polish} manualLabel="Edit by hand" onManual={() => { setDismissed(d => [...d, lastPolishJob.id]); promptRef.current?.focus() }} onDismiss={() => setDismissed(d => [...d, lastPolishJob.id])} /> : null}
          {scene.pending_polish && !scene.active_job && <div className="polish-ready"><Icon name="spark" /><div><strong>A polished version is ready</strong><p className="hint">Compare it with version {scene.pending_polish.prompt_version} and choose which to keep. Nothing changes until you do.</p></div><button type="button" onClick={() => setPolishOpen(true)}>Compare</button></div>}
          {!current || !promptBase ? <p className="hint">The prompt appears once the scene has an analysis.</p> : <>
            {promptStale && <p className="notice-line">This prompt was built from an earlier analysis. <button className="link-button" disabled={busy} onClick={() => { if (!promptDirty || window.confirm('Replace your unsaved prompt edits with a new draft?')) void rebuild(current.id, changes) }}>Rebuild from version {current.version}</button></p>}
            {mappingStale && <p className="notice-line">This prompt was built before the current character assignments. <button className="link-button" disabled={busy} onClick={() => { if (!promptDirty || window.confirm('Replace your unsaved prompt edits with a new draft?')) void rebuild(current.id, changes) }}>Rebuild with the assignments</button></p>}
            {!promptBase.saved && <p className="notice-line">{promptBase.source === 'restored' ? 'Restored version — not saved yet.' : 'Draft from the studio template — not saved yet.'}</p>}
            <label htmlFor="prompt-text">Prompt</label>
            <textarea id="prompt-text" ref={promptRef} className="prompt-area" rows={16} maxLength={40000} value={promptText} onChange={e => setPromptText(e.target.value)} />
            <div className="prompt-grid">
              <div><label htmlFor="negative-prompt">Negative prompt</label><textarea id="negative-prompt" rows={5} maxLength={8000} value={negative} onChange={e => setNegative(e.target.value)} /></div>
              <div><label htmlFor="scene-changes">Scene changes (optional)</label><textarea id="scene-changes" rows={3} maxLength={4000} value={changes} placeholder="For example: make it golden hour" onChange={e => setChanges(e.target.value)} />
                <button type="button" className="link-button" disabled={busy} onClick={() => { if (!promptDirty || promptText === promptBase.text || window.confirm('Rebuilding replaces your edits to the prompt text. Continue?')) void rebuild(current.id, changes) }}>Rebuild draft with these changes</button></div>
            </div>
            {!promptDirty && promptBase.saved && scene.review.warnings.length > 0 && <div className="check-box warning"><strong>Check the saved prompt</strong><ul>{scene.review.warnings.map(w => <li key={w}>{w}</li>)}</ul></div>}
            <div className="prompt-tools">
              <button type="button" className="secondary" onClick={() => copyText(promptText, setMessage)}><Icon name="copy" /> Copy prompt</button>
              <button type="button" className="secondary" disabled={busy || !!scene.active_job || !latestPrompt || promptDirty || !promptBase.saved || !!scene.pending_polish}
                title={promptDirty || !promptBase.saved ? 'Save the prompt first; Polish works on the saved version' : scene.pending_polish ? 'Compare the polished version first' : 'Sends the prompt text and analysis to Anthropic via Claude Code. Runs once.'}
                onClick={polish}><Icon name="spark" /> Polish prompt</button>
              {scene.prompts.length > 0 && <button type="button" className="secondary" disabled={busy} onClick={() => setHistoryOpen(true)}><Icon name="clock" /> Version history ({scene.prompts.length})</button>}
            </div>
            <div className="panel-actions">
              <span className="spacer">{promptDirty ? 'Unsaved edits' : promptBase.saved && latestPrompt ? `Version ${latestPrompt.version} saved${latestPrompt.is_polished ? ' · polished' : ''}` : ''}</span>
              <button type="button" disabled={busy || !promptText.trim() || (promptBase.saved && !promptDirty)} onClick={savePrompt}>Save prompt version</button>
            </div>
            <p className="hint polish-note">Polish prompt asks Claude to make the saved prompt read more clearly without adding or dropping anything. It sends the prompt text and the analysis to Anthropic, never your photos, and uses your Claude plan’s allowance.</p>
            {status.prompt === 'done' && !promptDirty && next('review', 'Next: review and approve')}
          </>}
        </section>

        <section id="step-panel-review" role="tabpanel" aria-labelledby="step-tab-review" hidden={activeStep !== 'review'} className="panel step-panel">
          <div className="step-head"><span className="step-number">04</span><div><h3>Review and approve</h3><p className="hint">Everything the image will be made from. Approval locks these exact inputs; nothing can be generated without it.</p></div></div>
          <ReviewPanel scene={scene} characters={characters} generationEngine={engines?.generation_engine ?? 'codex_cli'} busy={busy || !!scene.active_job} unsaved={dirty}
            onGo={target => setStep(target)}
            onApprove={acceptWarnings => void run(async () => { await accept(await send<SceneDetail>(`/api/scenes/${scene.id}/approve`, 'POST', token, { prompt_id: scene.review.prompt_id, accept_warnings: acceptWarnings }), false) }, 'Approved. These exact inputs are now locked for generation.')}
            onWithdraw={id => void run(async () => { await accept(await send<SceneDetail>(`/api/scenes/${scene.id}/approval/withdraw`, 'POST', token, { approval_id: id }), false) }, 'Approval withdrawn.')} />
          {approved && next('generate', 'Next: generate')}
        </section>

        <section id="step-panel-generate" role="tabpanel" aria-labelledby="step-tab-generate" hidden={activeStep !== 'generate'} className="panel step-panel">
          <div className="step-head"><span className="step-number">05</span><div><h3>Generate and results</h3><p className="hint">Make the image from the approved inputs, with Codex or any app you like. Every result is kept and stays linked to what it was made from.</p></div></div>
          <GeneratePanel scene={scene} data={data} generationEngine={engines?.generation_engine ?? 'codex_cli'} busy={busy} exportOpen={exportOpen} onExportOpen={setExportOpen}
            runStatus={scene.active_job?.kind === 'generation' ? <><ProgressCard job={scene.active_job} stopping={stopping === scene.active_job.id} busy={busy} onCancel={cancel} />{scene.active_job.batch && <BatchList token={token} sceneId={scene.id} />}</>
              : showGenerationNotice && lastGenerationJob ? <JobNotice job={lastGenerationJob} busy={busy || !approved || !!scene.active_job}
                onRetry={() => { if (window.confirm('Generate again? This sends the approved images to OpenAI via Codex once more and uses your ChatGPT plan’s image allowance.')) void generate('generate') }}
                extra={lastGenerationJob.recoverable ? <button type="button" className="secondary" disabled={busy} onClick={() => void recover(lastGenerationJob)}>Look for a saved image</button> : undefined}
                manualLabel="Export for manual use" onManual={() => setExportOpen(true)} onDismiss={() => setDismissed(d => [...d, lastGenerationJob.id])} /> : null}
            onGenerate={(mode, count) => void generate(mode, count)} onChanged={(detail, note) => { void accept(detail, false).then(() => setMessage(note)) }}
            onRefresh={note => { void request<SceneDetail>(`/api/scenes/${scene.id}`).then(detail => accept(detail, false)).then(() => setMessage(note)) }} onGo={() => setStep('review')} />
        </section>

        {scene.jobs.length > 0 && <details className="panel run-history"><summary>Engine runs ({scene.jobs.length})</summary>
          <ul>{scene.jobs.map(j => <li key={j.id}><span className={`run-status ${j.status}`}>{statusLabels[j.status] ?? j.status}</span><span>{j.mode === 'variation' ? 'Variation' : kindLabels[j.kind] ?? j.kind} · {j.engine_name}{j.engine_version ? ` · ${j.engine_version}` : ''}{j.seconds != null && j.kind !== 'export' ? ` · ${duration(j.seconds)}` : ''}{j.usage?.input_tokens != null ? ` · ${j.usage.input_tokens.toLocaleString()} in, ${(j.usage.output_tokens ?? 0).toLocaleString()} out tokens` : ''}</span><span className="hint">{formatDate(j.created_at)}</span>
            {j.job_folder && <button type="button" className="link-button" onClick={() => copyText(j.job_folder!, setMessage)}><Icon name="folder" /> Copy folder path</button>}</li>)}</ul>
        </details>}
      </div>
    </div>
    <dialog ref={manualRef} className="image-dialog manual-dialog" aria-labelledby="manual-title" onClose={() => setManual(false)}>
      {manual && <ManualAnalysis scene={scene} token={token} onClose={() => setManual(false)} onImported={detail => { setManual(false); if (lastAnalysisJob) setDismissed(d => [...d, lastAnalysisJob.id]); void accept(detail, !promptDirty).then(() => setMessage(`Analysis version ${detail.analyses[0].version} imported.`)) }} />}
    </dialog>
    {chargeAsk && apiEngines.byId[engine] && <ChargeDialog engine={apiEngines.byId[engine]} model={engines?.api_models[engine]?.analysis ?? null} runs={1} note={chargeAsk.note}
      onConfirm={() => void analyse(true)} onClose={() => setChargeAsk(null)} />}
    {historyOpen && <PromptHistory scene={scene} token={token} editorDirty={promptDirty} onClose={() => setHistoryOpen(false)}
      onLoad={prompt => { if (restorePrompt(prompt)) setHistoryOpen(false) }}
      onDeleted={(detail, wasCurrent, version) => { void accept(detail, wasCurrent).then(() => setMessage(`Prompt version ${version} deleted.`)) }} />}
    {polishOpen && scene.pending_polish && <PolishDialog key={scene.pending_polish.job_id} scene={scene} pending={scene.pending_polish} token={token} onClose={() => setPolishOpen(false)}
      onSaved={(detail, note) => { setPolishOpen(false); void accept(detail).then(() => setMessage(note)) }} />}
  </div>
}

export default function Scenes({ data, onDirty, onBusy }: { data: Bootstrap; onDirty: (dirty: boolean) => void; onBusy: (busy: boolean) => void }) {
  const token = data.session_token
  const [scenes, setScenes] = useState<SceneSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState<string | null>(() => routeParts()[0] === 'scenes' ? routeParts()[1] ?? null : null)
  const [creating, setCreating] = useState(false)
  const [selecting, setSelecting] = useState(false)
  const [picked, setPicked] = useState<string[]>([])
  const [renaming, setRenaming] = useState<SceneSummary | null>(null)
  const [engines, setEngines] = useState<EngineSettings | null>(null)
  const [batching, setBatching] = useState<{ kind: 'analysis' | 'generation'; scenes: SceneSummary[]; all?: boolean } | null>(null)
  const [suggesting, setSuggesting] = useState<SceneSummary[] | null>(null)
  const [batchKey, setBatchKey] = useState(0)
  const dialogRef = useRef<HTMLDialogElement>(null)

  const load = useCallback(() => request<SceneSummary[]>('/api/scenes').then(list => { setScenes(list); setError('') }, e => setError(e.message)).finally(() => setLoading(false)), [])
  useEffect(() => { void load() }, [load])
  useEffect(() => { if (!open) request<EngineSettings>('/api/engines/settings').then(setEngines, () => undefined) }, [open])
  // The open workspace adds its step to the route; keep it when the scene is unchanged.
  useEffect(() => { if (!open) replaceRoute('scenes'); else if (routeParts()[1] !== open) replaceRoute(`scenes/${open}`) }, [open])
  useEffect(() => { if (creating) { if (!dialogRef.current?.open) dialogRef.current?.showModal() } else dialogRef.current?.close() }, [creating])
  useEffect(() => { if (!open) onBusy(busy) }, [busy, open, onBusy])
  // Keep list cards current while any run is in progress.
  useEffect(() => {
    if (open || !scenes.some(s => s.active_job)) return
    const timer = window.setInterval(() => void load(), 3000)
    return () => window.clearInterval(timer)
  }, [open, scenes, load])

  if (open) return <Workspace key={open} data={data} sceneId={open} onBack={() => { setOpen(null); void load() }} onOpen={setOpen} onDirty={onDirty} onBusy={onBusy} onChanged={() => void load()} />

  const openAt = (id: string, step: string) => { replaceRoute(`scenes/${id}/${step}`); setOpen(id) }
  const startBatch = (kind: 'analysis' | 'generation', chosen: SceneSummary[], all = false) => setBatching({ kind, scenes: chosen, all })
  function started(result: BatchStart) {
    setBatching(null); stopSelecting(); setBatchKey(k => k + 1); setActionError('')
    const what = result.batch.kind === 'generation' ? `${result.batch.total} ${result.batch.total === 1 ? 'image' : 'images'}` : `${result.batch.total} ${result.batch.total === 1 ? 'analysis' : 'analyses'}`
    setNotice(`Batch started: ${what}, one after another.${result.skipped.length ? ` Skipped: ${result.skipped.map(s => `${s.title} (${s.reason})`).join(', ')}.` : ''}`)
    void load()
  }

  async function act(action: () => Promise<void>, success: string) {
    if (busy) return
    setBusy(true); setActionError(''); setNotice('')
    try { await action(); setNotice(success) }
    catch (e) { setActionError(e instanceof Error ? e.message : 'That did not work. Reload and try again.') }
    finally { setBusy(false); void load() }
  }
  const togglePick = (id: string) => setPicked(old => old.includes(id) ? old.filter(x => x !== id) : [...old, id])
  const stopSelecting = () => { setSelecting(false); setPicked([]) }
  const remove = (s: SceneSummary) => send<{ cleanup_pending: boolean }>(`/api/scenes/${s.id}?revision=${s.revision}`, 'DELETE', token)
  function deleteOne(s: SceneSummary) {
    if (!window.confirm(`Permanently delete “${s.title}”, its Base Image, analyses, prompts, assignments, approvals, results and run folders? This cannot be undone.`)) return
    void act(async () => {
      const result = await remove(s)
      if (result.cleanup_pending) throw new Error('Scene removed. Some locked files are pending deletion; restart the studio to retry cleanup.')
    }, `“${s.title}” deleted.`)
  }
  function deleteSelected() {
    const chosen = scenes.filter(s => picked.includes(s.id))
    const running = chosen.filter(s => s.active_job)
    const deletable = chosen.filter(s => !s.active_job)
    if (!deletable.length) { setActionError('The selected scenes have engine jobs running. Cancel them first.'); return }
    const count = `${deletable.length} ${deletable.length === 1 ? 'scene' : 'scenes'}`
    if (!window.confirm(`Permanently delete ${count} with their Base Images, analyses, prompts, assignments, approvals, results and run folders? This cannot be undone.${running.length ? ` ${running.length} with a running job will be skipped.` : ''}`)) return
    void act(async () => {
      const failed: string[] = running.map(s => `${s.title} (job running)`)
      for (const s of deletable) { try { await remove(s) } catch { failed.push(s.title) } }
      stopSelecting()
      if (failed.length) throw new Error(`Not deleted: ${failed.join(', ')}. The others were deleted.`)
    }, `${count} deleted.`)
  }

  const filtered = scenes.filter(s => s.title.toLocaleLowerCase().includes(query.toLocaleLowerCase()))
  const chosen = scenes.filter(s => picked.includes(s.id))
  const approvedScenes = scenes.filter(s => ['approved', 'generated'].includes(s.workflow_state) && !s.active_job)
  const manualAnalysis = engines?.analysis_engine === 'manual'
  const manualGeneration = engines?.generation_engine === 'manual'
  return <div className="scenes">
    <div className="library-toolbar filters">
      <div><label htmlFor="scene-search">Search scenes</label><input id="scene-search" type="search" value={query} placeholder="Search by title" onChange={e => setQuery(e.target.value)} /></div>
      {!selecting && approvedScenes.length > 1 && !manualGeneration && <button className="secondary" disabled={busy} onClick={() => startBatch('generation', approvedScenes, false)}>Generate approved scenes</button>}
      {!selecting && !!filtered.length && <button className="secondary" disabled={busy} onClick={() => setSelecting(true)}>Select</button>}
      <button disabled={busy || selecting} onClick={() => setCreating(true)}>+ New scene</button>
    </div>
    {selecting && <SelectionBar count={picked.length} total={filtered.length} onAll={() => setPicked(filtered.map(s => s.id))} onNone={() => setPicked([])} onDone={stopSelecting}>
      <button type="button" className="secondary" disabled={busy || !picked.length || manualAnalysis || picked.length > MAX_ANALYSIS_RUNS} title={manualAnalysis ? 'Manual analysis is selected in Studio settings' : picked.length > MAX_ANALYSIS_RUNS ? `Choose up to ${MAX_ANALYSIS_RUNS} scenes` : 'Analyse the selected scenes one after another'} onClick={() => startBatch('analysis', chosen)}>Analyse</button>
      <button type="button" className="secondary" disabled={busy || !picked.length} onClick={() => setSuggesting(chosen)}>Suggest from group</button>
      <button type="button" className="secondary" disabled={busy || !picked.length || manualGeneration} title={manualGeneration ? 'Manual generation is selected in Studio settings' : 'Generate the selected approved scenes one after another'} onClick={() => startBatch('generation', chosen, true)}>Generate</button>
      <button type="button" className="danger secondary" disabled={busy || !picked.length} onClick={deleteSelected}>Delete</button>
    </SelectionBar>}
    {error && <div className="error" role="alert"><strong>Your scenes could not be loaded.</strong><p>{error}</p><button className="secondary" onClick={() => void load()}>Try again</button></div>}
    {actionError && <div className="error" role="alert"><strong>Could not finish that action.</strong><p>{actionError}</p></div>}
    <p className="library-status" role="status">{busy ? 'Working…' : notice}</p>
    <BatchList token={token} refreshKey={batchKey} onOpenScene={openAt} onProgress={() => void load()} />
    {loading ? <p role="status">Loading your scenes…</p> : !filtered.length ? <div className="empty-library panel"><span className="tiny-label">A REFERENCE. A NEW POSSIBILITY.</span><h2>{query ? 'No matching scenes' : 'Your first scene starts here'}</h2><p>{query ? 'Try another title.' : 'Add a Base Image whose pose, framing and light you want to recreate. The studio analyses it, you choose who appears, then review and approve the prompt.'}</p></div>
      : <div className="scene-grid">{filtered.map(s => {
        const isPicked = picked.includes(s.id)
        return <div key={s.id} className={`scene-card ${isPicked ? 'picked' : ''}`}>
          <button className="card-main" aria-pressed={selecting ? isPicked : undefined} disabled={busy} onClick={() => selecting ? togglePick(s.id) : setOpen(s.id)}>
            {selecting && <span className="pick-box" aria-hidden="true" />}
            <span className="scene-thumb"><img src={s.thumbnail_url} alt="" loading="lazy" /></span>
            <span className="scene-card-copy"><strong>{s.title}</strong><span className="scene-card-meta"><StageChip state={s.workflow_state} /><span>{s.result_count ? `${s.result_count} ${s.result_count === 1 ? 'result' : 'results'} · ` : ''}{new Date(s.updated_at).toLocaleDateString()}</span></span></span>
          </button>
          {!selecting && <CardMenu label={s.title} disabled={busy} items={[
            { label: 'Rename', onSelect: () => setRenaming(s) },
            { label: 'Duplicate', onSelect: () => void act(async () => { await send(`/api/scenes/${s.id}/duplicate`, 'POST', token) }, `Copy of “${s.title}” created.`) },
            { label: 'Delete', danger: true, disabled: !!s.active_job, onSelect: () => deleteOne(s) },
          ]} />}
        </div>
      })}</div>}
    {renaming && <TextDialog title="Rename scene" label="Scene title" initial={renaming.title} maxLength={120} onClose={() => setRenaming(null)}
      onSave={async value => { await send(`/api/scenes/${renaming.id}`, 'PUT', token, { title: value, revision: renaming.revision }); setActionError(''); setNotice('Scene renamed.'); await load() }} />}
    <dialog ref={dialogRef} className="image-dialog new-scene-dialog" aria-labelledby="new-scene-title" onClose={() => setCreating(false)}>
      {creating && <NewSceneForm data={data} onCancel={() => setCreating(false)} onCreated={scene => { setCreating(false); setScenes(old => [scene, ...old]); setOpen(scene.id) }}
        onCreatedMany={(created, failed) => {
          setCreating(false); void load()
          // Keep the new scenes selected so they can be analysed together straight away.
          if (created.length) { setSelecting(true); setPicked(created.map(c => c.id)); setQuery('') }
          setNotice(created.length ? `${created.length} ${created.length === 1 ? 'scene' : 'scenes'} created and selected. Choose Analyse to analyse them one after another, or open one to start.` : '')
          setActionError(failed.length ? `Not added: ${failed.join('; ')}.` : '')
        }} />}
    </dialog>
    {batching && <BatchDialog kind={batching.kind} scenes={batching.scenes} preselectAll={batching.all} token={token}
      engine={batching.kind === 'analysis' ? engines?.analysis_engine ?? 'claude_cli' : 'codex_cli'} onClose={() => setBatching(null)} onStarted={started} />}
    {suggesting && <GroupDialog scenes={suggesting} token={token} onClose={() => setSuggesting(null)}
      onDone={result => {
        setSuggesting(null); stopSelecting(); void load()
        setNotice(result.suggested.length ? `Suggestions saved for ${result.suggested.length} ${result.suggested.length === 1 ? 'scene' : 'scenes'}. Open each one, check the Characters step and save its assignments to confirm.` : 'No suggestions were saved.')
        const notes = [...(result.skipped.length ? [`Skipped: ${result.skipped.map(s => `${s.title} (${s.reason})`).join(', ')}.`] : []), ...(result.left_out.length ? [`Left out (no photos or archived): ${result.left_out.join(', ')}.`] : [])]
        setActionError(notes.join(' '))
      }} />}
  </div>
}
