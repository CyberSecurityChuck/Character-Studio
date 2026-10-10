import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { request, send, type Bootstrap } from './api'
import { CardMenu, SelectionBar, TextDialog, sentence } from './Controls'
import { replaceRoute, routeParts } from './route'

type Box = { x: number; y: number; width: number; height: number }
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
type Prompt = { id: string; version: number; analysis_id: string | null; prompt_text: string; negative_prompt: string; scene_changes: string; source: string; created_at: string }
export type Job = { id: string; engine: string; engine_name: string; engine_version: string | null; status: string; error_kind: string | null; error_details: string | null; job_folder: string | null; timeout_seconds: number; result_id: string | null; created_at: string; started_at: string | null; finished_at: string | null }
export type SceneSummary = { id: string; title: string; workflow_state: string; width: number; height: number; revision: number; created_at: string; updated_at: string; last_opened_at: string | null; thumbnail_url: string; original_url: string; analysis_version: number | null; prompt_version: number | null; active_job: Job | null }
type SceneDetail = SceneSummary & { analyses: Analysis[]; prompts: Prompt[]; jobs: Job[] }
type EngineSettings = { analysis_engine: string; generation_engine: string; claude_timeout: number; codex_timeout: number; revision: number }

type SubjectField = 'position' | 'pose_summary' | 'body_direction' | 'torso_orientation' | 'shoulder_alignment' | 'head_direction' | 'facial_viewing_angle' | 'eye_direction' | 'expression' | 'arms_and_hands' | 'legs_and_feet' | 'outfit' | 'hairstyle' | 'accessories'
type CameraField = 'height' | 'direction' | 'shot_type' | 'framing' | 'perspective'
const subjectFields: [SubjectField, string][] = [['position', 'Position'], ['pose_summary', 'Pose'], ['body_direction', 'Body direction'], ['torso_orientation', 'Torso'], ['shoulder_alignment', 'Shoulders'], ['head_direction', 'Head direction'], ['facial_viewing_angle', 'Face angle'], ['eye_direction', 'Eyes and gaze'], ['expression', 'Expression'], ['arms_and_hands', 'Arms and hands'], ['legs_and_feet', 'Legs and feet'], ['outfit', 'Outfit'], ['hairstyle', 'Hairstyle'], ['accessories', 'Accessories']]
const cameraFields: [CameraField, string][] = [['height', 'Height'], ['direction', 'Direction'], ['shot_type', 'Shot type'], ['framing', 'Framing'], ['perspective', 'Perspective']]
const sceneFields: ['environment' | 'lighting' | 'color_palette' | 'atmosphere', string][] = [['environment', 'Environment'], ['lighting', 'Lighting and shadows'], ['color_palette', 'Colour palette'], ['atmosphere', 'Atmosphere']]
export const stageLabels: Record<string, string> = { needs_analysis: 'Needs analysis', analysing: 'Analysing…', review_analysis: 'Review analysis', analysis_ready: 'Ready for prompt', prompt_saved: 'Prompt saved' }
const sourceLabels: Record<string, string> = { claude_cli: 'Claude', codex_cli: 'Codex', manual_import: 'Manual import', user_edit: 'Your edit' }
const engineLabels: Record<string, string> = { claude_cli: 'Claude', codex_cli: 'Codex', manual: 'Manual' }
const statusLabels: Record<string, string> = { not_started: 'Waiting', running: 'Running', completed: 'Completed', failed: 'Failed', cancelled: 'Cancelled', interrupted: 'Interrupted' }
const sendsTo: Record<string, string> = { claude_cli: 'Anthropic via Claude Code', codex_cli: 'OpenAI via Codex' }
const formatDate = (value: string) => new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value))
const fieldName = (field: string) => field.replace(/_/g, ' ').split(/\s*\.\s*/).map(part => sentence(part.trim())).join(' · ')

function Icon({ name }: { name: 'back' | 'copy' | 'spark' | 'edit' | 'clock' | 'folder' }) {
  const paths = {
    back: <path d="M15 5l-7 7 7 7" />,
    copy: <><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V6a2 2 0 0 1 2-2h8" /></>,
    spark: <path d="M12 3l1.8 4.6L18.5 9.5l-4.7 1.9L12 16l-1.8-4.6L5.5 9.5l4.7-1.9z" />,
    edit: <path d="M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4" />,
    clock: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></>,
    folder: <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />,
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

function BaseImage({ scene, subjects, show }: { scene: SceneSummary; subjects: Subject[]; show: boolean }) {
  return <div className="base-image" style={{ aspectRatio: `${scene.width} / ${scene.height}` }}>
    <img src={scene.original_url} alt={`Base Image for ${scene.title}`} />
    {show && subjects.map(s => <span key={s.label} className="subject-box" style={{ left: `${s.bounding_box.x * 100}%`, top: `${s.bounding_box.y * 100}%`, width: `${s.bounding_box.width * 100}%`, height: `${s.bounding_box.height * 100}%` }}><span>{s.label}</span></span>)}
  </div>
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

function NewSceneForm({ data, onCreated, onCancel }: { data: Bootstrap; onCreated: (scene: SceneDetail) => void; onCancel: () => void }) {
  const [title, setTitle] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { if (!file) return; const url = URL.createObjectURL(file); setPreview(url); return () => URL.revokeObjectURL(url) }, [file])
  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!file || busy) return
    if (file.size > data.max_upload_bytes) { setError(`This image is too large. Limit: ${Math.floor(data.max_upload_bytes / 1048576)} MB.`); return }
    setBusy(true); setError('')
    try {
      onCreated(await request<SceneDetail>(`/api/scenes?title=${encodeURIComponent(title.trim() || file.name.replace(/\.[^.]+$/, '') || 'Untitled scene')}`, {
        method: 'POST', headers: { 'X-Studio-Token': data.session_token, 'Content-Type': 'application/octet-stream' }, body: file,
      }, 'Check the title and image, then try again.'))
    } catch (e) { setError(e instanceof Error ? e.message : 'The scene could not be created.') }
    finally { setBusy(false) }
  }
  return <form className="new-scene" onSubmit={e => void submit(e)}>
    <h2 id="new-scene-title">New scene</h2>
    <p className="hint">Choose the Base Image whose composition you want to recreate. It stays on this computer until you choose to analyse it.</p>
    <fieldset disabled={busy}>
      <div className="new-scene-body">
        <label className={`drop-zone ${preview ? 'has-image' : ''}`}>
          <input className="visually-hidden" type="file" accept="image/jpeg,image/png,image/webp" required onChange={e => { setFile(e.target.files?.[0] ?? null); setError('') }} />
          {preview ? <img src={preview} alt="Selected Base Image" /> : <span><strong>Choose a Base Image</strong><small>JPEG, PNG or WebP · up to {Math.floor(data.max_upload_bytes / 1048576)} MB</small></span>}
        </label>
        <div><label htmlFor="scene-title">Scene title</label><input id="scene-title" maxLength={120} value={title} placeholder={file ? file.name.replace(/\.[^.]+$/, '') : 'For example: Garden bench'} onChange={e => setTitle(e.target.value)} />
          <p className="hint">Optional. The file name is used if you leave it empty.</p></div>
      </div>
    </fieldset>
    {error && <p className="frame-error" role="alert">{error}</p>}
    <div className="dialog-actions"><button type="button" className="secondary" onClick={onCancel}>Cancel</button><button disabled={!file || busy}>{busy ? 'Creating…' : 'Create scene'}</button></div>
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

function JobNotice({ job, onRetry, onManual, onDismiss, busy }: { job: Job; onRetry: () => void; onManual: () => void; onDismiss: () => void; busy: boolean }) {
  const [note, setNote] = useState('')
  const titles: Record<string, string> = { failed: `${job.engine_name} could not finish the analysis`, cancelled: 'Analysis cancelled', interrupted: 'The analysis was interrupted' }
  return <div className={`job-notice ${job.status}`} role="alert">
    <strong>{titles[job.status] ?? 'The analysis did not finish'}</strong>
    <p>{job.error_details}</p>
    {job.status === 'interrupted' && job.job_folder && <p className="folder-line"><Icon name="folder" /> <code>{job.job_folder}</code> <button type="button" className="link-button" onClick={() => copyText(job.job_folder!, setNote)}>Copy path</button></p>}
    <span className="library-status" role="status">{note}</span>
    <div className="notice-actions">
      <button type="button" disabled={busy} onClick={onRetry}>{job.status === 'interrupted' ? 'I checked — try again' : 'Try again'}</button>
      <button type="button" className="secondary" onClick={onManual}>Do it manually</button>
      <button type="button" className="link-button" onClick={onDismiss}>Dismiss</button>
    </div>
  </div>
}

function Workspace({ data, sceneId, onBack, onOpen, onDirty, onBusy, onChanged }: { data: Bootstrap; sceneId: string; onBack: () => void; onOpen: (id: string) => void; onDirty: (dirty: boolean) => void; onBusy: (busy: boolean) => void; onChanged: () => void }) {
  const token = data.session_token
  const [scene, setScene] = useState<SceneDetail | null>(null)
  const [engines, setEngines] = useState<EngineSettings | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [viewing, setViewing] = useState<string | null>(null)
  const [editing, setEditing] = useState<AnalysisData | null>(null)
  const [confirmed, setConfirmed] = useState<Uncertainty[]>([])
  const [showBoxes, setShowBoxes] = useState(true)
  const [manual, setManual] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [title, setTitle] = useState('')
  const [dismissed, setDismissed] = useState<string | null>(null)
  const [stopping, setStopping] = useState<string | null>(null)
  const [promptText, setPromptText] = useState('')
  const [negative, setNegative] = useState('')
  const [changes, setChanges] = useState('')
  const [promptBase, setPromptBase] = useState<{ text: string; negative: string; changes: string; analysisId: string | null; source: 'template' | 'user_edit' | 'restored'; saved: boolean } | null>(null)
  // Where the editor text came from, so an unchanged template draft or restore is labelled honestly.
  const [origin, setOrigin] = useState<{ text: string; source: 'template' | 'restored' } | null>(null)
  const manualRef = useRef<HTMLDialogElement>(null)
  const lock = useRef(false)

  const current = scene?.analyses[0] ?? null
  const shown = scene?.analyses.find(a => a.id === viewing) ?? current
  const latestPrompt = scene?.prompts[0] ?? null
  const promptDirty = !!promptBase && (promptText !== promptBase.text || negative !== promptBase.negative || changes !== promptBase.changes)
  const dirty = !!editing || promptDirty || renaming && title !== scene?.title
  const promptDirtyRef = useRef(false)
  promptDirtyRef.current = promptDirty
  useEffect(() => { onDirty(dirty); return () => onDirty(false) }, [dirty, onDirty])
  useEffect(() => { onBusy(busy); return () => onBusy(false) }, [busy, onBusy])
  useEffect(() => { if (manual) { if (!manualRef.current?.open) manualRef.current?.showModal() } else manualRef.current?.close() }, [manual])

  const loadPrompt = useCallback(async (detail: SceneDetail) => {
    const saved = detail.prompts[0]
    if (saved) {
      setPromptText(saved.prompt_text); setNegative(saved.negative_prompt); setChanges(saved.scene_changes)
      setPromptBase({ text: saved.prompt_text, negative: saved.negative_prompt, changes: saved.scene_changes, analysisId: saved.analysis_id, source: 'user_edit', saved: true })
      setOrigin(null)
    } else if (detail.analyses[0]) {
      const draft = await send<{ prompt_text: string; negative_prompt: string }>(`/api/scenes/${detail.id}/prompts/draft`, 'POST', token, { analysis_id: detail.analyses[0].id, scene_changes: '' })
      setPromptText(draft.prompt_text); setNegative(draft.negative_prompt); setChanges('')
      setPromptBase({ text: draft.prompt_text, negative: draft.negative_prompt, changes: '', analysisId: detail.analyses[0].id, source: 'template', saved: false })
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
        if (job.status === 'not_started' || job.status === 'running') { setScene(s => s && { ...s, active_job: job }); return }
        const detail = await request<SceneDetail>(`/api/scenes/${sceneId}`)
        await accept(detail, !promptDirtyRef.current)
        if (job.status === 'completed') setMessage(`Analysis version ${detail.analyses[0]?.version} saved.`)
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
  function guard() { return !dirty || window.confirm('Discard unsaved edits?') }

  if (!scene) return <div>{error ? <div className="error" role="alert"><strong>This scene could not be opened.</strong><p>{error}</p><button className="secondary" onClick={onBack}>Back to scenes</button></div> : <p role="status">Opening scene…</p>}</div>

  const engine = engines?.analysis_engine ?? 'claude_cli'
  const lastJob = scene.jobs[0]
  const showJobNotice = !scene.active_job && lastJob && lastJob.status !== 'completed' && lastJob.id !== dismissed && (!current || lastJob.created_at > current.created_at)
  const flagged = new Set((shown?.analysis.uncertainties ?? []).map(u => u.field))
  const promptStale = !!latestPrompt && !!current && latestPrompt.analysis_id !== current.id && promptBase?.saved

  const analyse = () => run(async () => {
    setDismissed(null)
    const detail = await send<SceneDetail>(`/api/scenes/${scene.id}/analyse`, 'POST', token)
    setScene(detail); onChanged()
  })
  const cancel = () => {
    const job = scene.active_job
    if (!job) return
    // Show "Stopping…" at once; the server stops the CLI and the poll picks up the result.
    setStopping(job.id)
    void run(async () => { await send(`/api/jobs/${job.id}/cancel`, 'POST', token) })
  }
  const startEdit = () => { if (shown) { setEditing(clone(shown.analysis)); setConfirmed(shown.confirmed_uncertainties) } }
  const saveRevision = (analysis: AnalysisData, confirmedList: Uncertainty[], base: Analysis, success: string) => run(async () => {
    await accept(await send<SceneDetail>(`/api/scenes/${scene.id}/analyses/${base.id}/revise`, 'POST', token, { analysis, confirmed_uncertainties: confirmedList }), !promptDirty)
    setEditing(null)
  }, success)
  const confirmUncertainty = (item: Uncertainty) => {
    if (!current) return
    const next = clone(current.analysis)
    next.uncertainties = next.uncertainties.filter(u => !(u.field === item.field && u.note === item.note))
    void saveRevision(next, [...current.confirmed_uncertainties, item], current, `Confirmed. Saved as analysis version ${current.version + 1}.`)
  }
  const rebuild = (analysisId: string, sceneChanges: string) => run(async () => {
    const draft = await send<{ prompt_text: string; negative_prompt: string }>(`/api/scenes/${scene.id}/prompts/draft`, 'POST', token, { analysis_id: analysisId, scene_changes: sceneChanges })
    setPromptText(draft.prompt_text); setNegative(draft.negative_prompt)
    setPromptBase(b => b && { ...b, analysisId })
    setOrigin({ text: draft.prompt_text, source: 'template' })
  }, 'Draft rebuilt from the analysis. Save it to keep it.')
  const savePrompt = () => run(async () => {
    const source = origin && promptText === origin.text ? origin.source : 'user_edit'
    const detail = await send<SceneDetail>(`/api/scenes/${scene.id}/prompts`, 'POST', token, { analysis_id: promptBase?.analysisId ?? current?.id ?? null, prompt_text: promptText, negative_prompt: negative, scene_changes: changes, source })
    await accept(detail)
  }, 'Prompt version saved.')
  const restorePrompt = (prompt: Prompt) => {
    if (!guard()) return
    setPromptText(prompt.prompt_text); setNegative(prompt.negative_prompt); setChanges(prompt.scene_changes)
    setPromptBase({ text: prompt.prompt_text, negative: prompt.negative_prompt, changes: prompt.scene_changes, analysisId: prompt.analysis_id, source: 'restored', saved: false })
    setOrigin({ text: prompt.prompt_text, source: 'restored' })
    setMessage(`Version ${prompt.version} loaded into the editor. Save to make it the current prompt.`)
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
      <button className="danger secondary" disabled={busy || !!scene.active_job} title={scene.active_job ? 'Cancel the running analysis first' : undefined} onClick={() => { if (window.confirm(`Permanently delete “${scene.title}”, its Base Image, analyses, prompts and run folders? This cannot be undone.`)) void run(async () => { await send(`/api/scenes/${scene.id}?revision=${scene.revision}`, 'DELETE', token); onDirty(false); onBack() }) }}>Delete</button>
    </div>}
  </div>

  return <div className="scene-workspace">
    {header}
    {error && <div className="error" role="alert"><strong>Could not finish that action.</strong><p>{error}</p></div>}
    <p className="library-status" role="status">{busy ? 'Working…' : message}</p>
    <div className="workspace-columns">
      <aside className="image-column">
        <div className="panel image-panel">
          <BaseImage scene={scene} subjects={shown?.analysis.subjects ?? []} show={showBoxes} />
          <div className="image-meta"><span>Image 1 · Base Image · {scene.width} × {scene.height}</span>
            {!!shown?.analysis.subjects.length && <label className="checkbox-label"><input type="checkbox" checked={showBoxes} onChange={e => setShowBoxes(e.target.checked)} /> Show subjects</label>}</div>
        </div>
      </aside>
      <div className="steps-column">
        <section className="panel step-panel" aria-labelledby="analysis-heading">
          <div className="step-head"><span className="step-number">01</span><div><h3 id="analysis-heading">Scene analysis</h3><p className="hint">What the camera sees: people, poses, framing, light. Saved as versions.</p></div></div>

          {scene.active_job ? <div className="progress-card" role="status">
            <span className="spinner" aria-hidden="true" />
            {stopping === scene.active_job.id ? <div><strong>Stopping…</strong><p>Stopping {scene.active_job.engine_name}. This takes a moment.</p></div>
              : <div><strong>{scene.active_job.status === 'not_started' ? `Waiting to analyse with ${scene.active_job.engine_name}…` : `Analysing with ${scene.active_job.engine_name}…`}</strong>
              <p><Icon name="clock" /> <Elapsed since={scene.active_job.started_at} /> · stops after {Math.round(scene.active_job.timeout_seconds / 60)} min. You can leave this page; the run continues.</p></div>}
            <button className="secondary" disabled={busy || stopping === scene.active_job.id} onClick={cancel}>{stopping === scene.active_job.id ? 'Stopping…' : 'Cancel'}</button>
          </div> : showJobNotice ? <JobNotice job={lastJob} busy={busy || engine === 'manual'} onRetry={() => void analyse()} onManual={() => setManual(true)} onDismiss={() => setDismissed(lastJob.id)} /> : null}

          {!current && !scene.active_job && !showJobNotice && <div className="analyse-start">
            <p>{engine === 'manual' ? 'Manual analysis is selected in Studio settings. Copy the instruction into another app, then paste its reply here.' : <>Analyse sends the Base Image to {sendsTo[engine]}, using your own sign-in and your plan's allowance. It runs once, only when you click.</>}</p>
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
                {engine !== 'manual' && !showJobNotice && <button className="secondary" disabled={busy || !!scene.active_job} onClick={() => { if (window.confirm(`Analyse again with ${engineLabels[engine]}? This sends the Base Image again and uses your plan's allowance. The current analysis is kept as a version.`)) void analyse() }}>Analyse again</button>}
                {!showJobNotice && <button className="secondary" disabled={busy || !!scene.active_job} onClick={() => setManual(true)}>Import</button>}
              </> : <button className="secondary" disabled={busy} onClick={() => current && void saveRevision(shown.analysis, shown.confirmed_uncertainties, current, `Version ${shown.version} restored as the current analysis.`)}>Restore as current</button>}
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
            <div className="panel-actions"><span className="spacer">Unsaved edits</span><button type="button" className="secondary" onClick={() => { if (window.confirm('Discard your edits to the analysis?')) setEditing(null) }}>Cancel</button><button type="button" disabled={busy} onClick={() => void saveRevision(editing, confirmed, current, `Saved as analysis version ${current.version + 1}.`)}>Save as new version</button></div>
          </>}
        </section>

        <section className="panel step-panel" aria-labelledby="prompt-heading">
          <div className="step-head"><span className="step-number">02</span><div><h3 id="prompt-heading">Generation prompt</h3><p className="hint">Built by the studio from the analysis. Edit freely; every save is a version.</p></div></div>
          {!current || !promptBase ? <p className="hint">The prompt appears once the scene has an analysis.</p> : <>
            {promptStale && <p className="notice-line">This prompt was built from an earlier analysis. <button className="link-button" disabled={busy} onClick={() => { if (!promptDirty || window.confirm('Replace your unsaved prompt edits with a new draft?')) void rebuild(current.id, changes) }}>Rebuild from version {current.version}</button></p>}
            {!promptBase.saved && <p className="notice-line">{promptBase.source === 'restored' ? 'Restored version — not saved yet.' : 'Draft from the studio template — not saved yet.'}</p>}
            <label htmlFor="prompt-text">Prompt</label>
            <textarea id="prompt-text" className="prompt-area" rows={16} maxLength={40000} value={promptText} onChange={e => setPromptText(e.target.value)} />
            <div className="prompt-grid">
              <div><label htmlFor="negative-prompt">Negative prompt</label><textarea id="negative-prompt" rows={5} maxLength={8000} value={negative} onChange={e => setNegative(e.target.value)} /></div>
              <div><label htmlFor="scene-changes">Scene changes (optional)</label><textarea id="scene-changes" rows={3} maxLength={4000} value={changes} placeholder="For example: make it golden hour" onChange={e => setChanges(e.target.value)} />
                <button type="button" className="link-button" disabled={busy} onClick={() => { if (!promptDirty || promptText === promptBase.text || window.confirm('Rebuilding replaces your edits to the prompt text. Continue?')) void rebuild(current.id, changes) }}>Rebuild draft with these changes</button></div>
            </div>
            <div className="panel-actions">
              <button type="button" className="secondary" onClick={() => copyText(promptText, setMessage)}><Icon name="copy" /> Copy prompt</button>
              {scene.prompts.length > 0 && <><label htmlFor="prompt-version" className="visually-hidden">Saved prompt versions</label>
                <select id="prompt-version" className="inline-select" value="" onChange={e => { const p = scene.prompts.find(x => x.id === e.target.value); if (p) restorePrompt(p) }}>
                  <option value="">Saved versions ({scene.prompts.length})</option>
                  {scene.prompts.map(p => <option key={p.id} value={p.id}>Version {p.version} · {p.source === 'template' ? 'Template' : p.source === 'restored' ? 'Restored' : 'Edited'} · {formatDate(p.created_at)}</option>)}
                </select></>}
              <span className="spacer">{promptDirty ? 'Unsaved edits' : promptBase.saved && latestPrompt ? `Version ${latestPrompt.version} saved` : ''}</span>
              <button type="button" disabled={busy || !promptText.trim() || (promptBase.saved && !promptDirty)} onClick={() => void savePrompt()}>Save prompt version</button>
            </div>
          </>}
        </section>

        {scene.jobs.length > 0 && <details className="panel run-history"><summary>Engine runs ({scene.jobs.length})</summary>
          <ul>{scene.jobs.map(j => <li key={j.id}><span className={`run-status ${j.status}`}>{statusLabels[j.status] ?? j.status}</span><span>{j.engine_name}{j.engine_version ? ` · ${j.engine_version}` : ''}</span><span className="hint">{formatDate(j.created_at)}</span>
            {j.job_folder && <button type="button" className="link-button" onClick={() => copyText(j.job_folder!, setMessage)}><Icon name="folder" /> Copy folder path</button>}</li>)}</ul>
        </details>}
      </div>
    </div>
    <dialog ref={manualRef} className="image-dialog manual-dialog" aria-labelledby="manual-title" onClose={() => setManual(false)}>
      {manual && <ManualAnalysis scene={scene} token={token} onClose={() => setManual(false)} onImported={detail => { setManual(false); setDismissed(lastJob?.id ?? null); void accept(detail, !promptDirty).then(() => setMessage(`Analysis version ${detail.analyses[0].version} imported.`)) }} />}
    </dialog>
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
  const dialogRef = useRef<HTMLDialogElement>(null)

  const load = useCallback(() => request<SceneSummary[]>('/api/scenes').then(list => { setScenes(list); setError('') }, e => setError(e.message)).finally(() => setLoading(false)), [])
  useEffect(() => { void load() }, [load])
  useEffect(() => { replaceRoute(open ? `scenes/${open}` : 'scenes') }, [open])
  useEffect(() => { if (creating) { if (!dialogRef.current?.open) dialogRef.current?.showModal() } else dialogRef.current?.close() }, [creating])
  useEffect(() => { if (!open) onBusy(busy) }, [busy, open, onBusy])
  // Keep list cards current while any run is in progress.
  useEffect(() => {
    if (open || !scenes.some(s => s.active_job)) return
    const timer = window.setInterval(() => void load(), 3000)
    return () => window.clearInterval(timer)
  }, [open, scenes, load])

  if (open) return <Workspace key={open} data={data} sceneId={open} onBack={() => { setOpen(null); void load() }} onOpen={setOpen} onDirty={onDirty} onBusy={onBusy} onChanged={() => void load()} />

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
    if (!window.confirm(`Permanently delete “${s.title}”, its Base Image, analyses, prompts and run folders? This cannot be undone.`)) return
    void act(async () => {
      const result = await remove(s)
      if (result.cleanup_pending) throw new Error('Scene removed. Some locked files are pending deletion; restart the studio to retry cleanup.')
    }, `“${s.title}” deleted.`)
  }
  function deleteSelected() {
    const chosen = scenes.filter(s => picked.includes(s.id))
    const running = chosen.filter(s => s.active_job)
    const deletable = chosen.filter(s => !s.active_job)
    if (!deletable.length) { setActionError('The selected scenes have analyses running. Cancel them first.'); return }
    const count = `${deletable.length} ${deletable.length === 1 ? 'scene' : 'scenes'}`
    if (!window.confirm(`Permanently delete ${count} with their Base Images, analyses, prompts and run folders? This cannot be undone.${running.length ? ` ${running.length} with a running analysis will be skipped.` : ''}`)) return
    void act(async () => {
      const failed: string[] = running.map(s => `${s.title} (analysis running)`)
      for (const s of deletable) { try { await remove(s) } catch { failed.push(s.title) } }
      stopSelecting()
      if (failed.length) throw new Error(`Not deleted: ${failed.join(', ')}. The others were deleted.`)
    }, `${count} deleted.`)
  }

  const filtered = scenes.filter(s => s.title.toLocaleLowerCase().includes(query.toLocaleLowerCase()))
  return <div className="scenes">
    <div className="library-toolbar filters">
      <div><label htmlFor="scene-search">Search scenes</label><input id="scene-search" type="search" value={query} placeholder="Search by title" onChange={e => setQuery(e.target.value)} /></div>
      {!selecting && !!filtered.length && <button className="secondary" disabled={busy} onClick={() => setSelecting(true)}>Select</button>}
      <button disabled={busy || selecting} onClick={() => setCreating(true)}>+ New scene</button>
    </div>
    {selecting && <SelectionBar count={picked.length} total={filtered.length} onAll={() => setPicked(filtered.map(s => s.id))} onNone={() => setPicked([])} onDone={stopSelecting}>
      <button type="button" className="danger secondary" disabled={busy || !picked.length} onClick={deleteSelected}>Delete</button>
    </SelectionBar>}
    {error && <div className="error" role="alert"><strong>Your scenes could not be loaded.</strong><p>{error}</p><button className="secondary" onClick={() => void load()}>Try again</button></div>}
    {actionError && <div className="error" role="alert"><strong>Could not finish that action.</strong><p>{actionError}</p></div>}
    <p className="library-status" role="status">{busy ? 'Working…' : notice}</p>
    {loading ? <p role="status">Loading your scenes…</p> : !filtered.length ? <div className="empty-library panel"><span className="tiny-label">A REFERENCE. A NEW POSSIBILITY.</span><h2>{query ? 'No matching scenes' : 'Your first scene starts here'}</h2><p>{query ? 'Try another title.' : 'Add a Base Image whose pose, framing and light you want to recreate. The studio analyses it and drafts a prompt you can edit.'}</p></div>
      : <div className="scene-grid">{filtered.map(s => {
        const isPicked = picked.includes(s.id)
        return <div key={s.id} className={`scene-card ${isPicked ? 'picked' : ''}`}>
          <button className="card-main" aria-pressed={selecting ? isPicked : undefined} disabled={busy} onClick={() => selecting ? togglePick(s.id) : setOpen(s.id)}>
            {selecting && <span className="pick-box" aria-hidden="true" />}
            <span className="scene-thumb"><img src={s.thumbnail_url} alt="" loading="lazy" /></span>
            <span className="scene-card-copy"><strong>{s.title}</strong><span className="scene-card-meta"><StageChip state={s.workflow_state} /><span>{new Date(s.updated_at).toLocaleDateString()}</span></span></span>
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
      {creating && <NewSceneForm data={data} onCancel={() => setCreating(false)} onCreated={scene => { setCreating(false); setScenes(old => [scene, ...old]); setOpen(scene.id) }} />}
    </dialog>
  </div>
}
