import { useCallback, useEffect, useRef, useState, type CSSProperties, type FormEvent, type ReactNode } from 'react'
import { request, send, type Bootstrap } from './api'
import type { SceneDetail } from './Scenes'

export type ResultMapping = { subject: string; action: string; character_name: string | null; images: number[] }
export type Result = {
  id: string; scene_id: string; version: number; approval_id: string; approval_current: boolean; job_id: string | null
  source: 'codex_cli' | 'manual_import'; mode: 'generate' | 'variation' | 'import'; note: string; media_type: string; width: number; height: number
  engine_version: string | null; recovered: boolean; is_preferred: boolean; created_at: string; image_url: string; thumbnail_url: string
  prompt_version: number | null; analysis_version: number | null; is_polished: boolean; mappings: ResultMapping[]
  scene_title?: string; scene_image_url?: string; scene_width?: number; scene_height?: number
}
export type ExportPackage = { id: string; number: number; created_at: string; approval_id: string; approval_current: boolean; result_count: number; photos_removed: number; job_folder: string | null; download_url: string }
type Base = { url: string; width: number; height: number }

const formatDate = (value: string) => new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`
const imageList = (images: number[]) => images.map(n => `Image ${n}`).join(', ')

export function sourceLabel(result: Result) {
  if (result.source === 'manual_import') return result.note ? `Imported · ${result.note}` : 'Imported'
  return `${result.mode === 'variation' ? 'Codex variation' : 'Codex'}${result.recovered ? ' · recovered' : ''}`
}

function copyText(text: string, done: (message: string) => void) {
  navigator.clipboard.writeText(text).then(() => done('Copied to the clipboard.'), () => done('Copy failed. Select the text and copy it yourself.'))
}

const extensions: Record<string, string> = { 'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp' }

function useModal() {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => { if (!ref.current?.open) ref.current?.showModal() }, [])
  return ref
}

/** One result in a grid: thumbnail, version and where it came from. */
export function ResultCard({ result, onOpen, title }: { result: Result; onOpen: () => void; title?: string }) {
  return <div className="result-card">
    <button type="button" className="card-main" onClick={onOpen} aria-label={`Open result ${result.version}${title ? ` of ${title}` : ''}`}>
      <span className="result-thumb"><img src={result.thumbnail_url} alt="" loading="lazy" />{result.is_preferred && <span className="preferred-badge" aria-label="Preferred">★ Preferred</span>}</span>
      <span className="result-copy">
        {title && <strong className="result-scene">{title}</strong>}
        <span className="result-line"><strong>Result {result.version}</strong><span className="hint">{formatDate(result.created_at)}</span></span>
        <span className="result-line"><span className="source-chip">{sourceLabel(result)}</span>{!result.approval_current && <span className="hint">Earlier approval</span>}</span>
      </span>
    </button>
  </div>
}

type View = 'result' | 'side' | 'slider'

/** Compare a result with the Base Image: side by side or with a slider. */
function Compare({ result, base, view }: { result: Result; base: Base; view: View }) {
  const [position, setPosition] = useState(50)
  if (view === 'result') return <div className="viewer-stage"><img src={result.image_url} alt={`Result ${result.version}`} /></div>
  if (view === 'side') return <div className="compare-side">
    <figure><img src={base.url} alt="Base Image" /><figcaption>Image 1 · Base Image</figcaption></figure>
    <figure><img src={result.image_url} alt={`Result ${result.version}`} /><figcaption>Result {result.version}</figcaption></figure>
  </div>
  return <div className="compare-slider-wrap">
    <div className="compare-slider" style={{ aspectRatio: `${base.width} / ${base.height}`, '--ratio': String(base.width / base.height) } as CSSProperties}>
      <img src={base.url} alt="Base Image" />
      <div className="compare-top" style={{ clipPath: `inset(0 0 0 ${position}%)` }}><img src={result.image_url} alt={`Result ${result.version}`} /></div>
      <span className="compare-line" style={{ left: `${position}%` }} aria-hidden="true" />
      <span className="compare-tag left">Base Image</span><span className="compare-tag right">Result {result.version}</span>
    </div>
    <label className="visually-hidden" htmlFor="compare-position">Compare position</label>
    <input id="compare-position" type="range" min={0} max={100} value={position} onChange={e => setPosition(Number(e.target.value))} />
    <p className="hint">Drag to reveal more of the Base Image (left) or the result (right). If the result has a different shape, both are fitted to the Base Image frame.</p>
  </div>
}

/** View a result, compare it with the Base Image, choose it as preferred, download or delete it. */
export function ResultViewer({ result, base, sceneTitle, token, onClose, onChanged, onOpenScene }: {
  result: Result; base: Base; sceneTitle: string; token: string; onClose: () => void
  onChanged: (detail: SceneDetail, message: string) => void; onOpenScene?: () => void
}) {
  const ref = useModal()
  const [view, setView] = useState<View>('side')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function act(action: () => Promise<void>) {
    setBusy(true); setError('')
    try { await action() } catch (e) { setError(e instanceof Error ? e.message : 'That did not work. Try again.') } finally { setBusy(false) }
  }
  const prefer = () => act(async () => {
    const detail = await send<SceneDetail>(`/api/results/${result.id}/preferred`, 'PUT', token, { preferred: !result.is_preferred })
    onChanged(detail, result.is_preferred ? `Result ${result.version} is no longer preferred.` : `Result ${result.version} is now the preferred result.`)
  })
  const remove = () => {
    if (!window.confirm(`Permanently delete result ${result.version}? Its image file is removed from this computer. Other results are kept.`)) return
    void act(async () => {
      const done = await send<{ scene: SceneDetail; cleanup_pending: boolean }>(`/api/results/${result.id}`, 'DELETE', token)
      onChanged(done.scene, done.cleanup_pending ? `Result ${result.version} removed. Its file is locked and will be deleted after a restart.` : `Result ${result.version} deleted.`)
      onClose()
    })
  }
  return <dialog ref={ref} className="image-dialog viewer-dialog" aria-labelledby="viewer-title" onClose={onClose}>
    <div className="viewer-body">
      <div className="viewer-head">
        <div><h2 id="viewer-title">Result {result.version}{result.is_preferred && <span className="preferred-badge inline">★ Preferred</span>}</h2>
          <p className="hint">{sceneTitle} · {formatDate(result.created_at)} · {sourceLabel(result)}{result.engine_version ? ` · ${result.engine_version}` : ''} · {result.width} × {result.height}</p></div>
        <div className="segmented" role="radiogroup" aria-label="How to show the result">
          {([['result', 'Result'], ['side', 'Side by side'], ['slider', 'Slider']] as [View, string][]).map(([id, label]) => <label key={id} className={`segment ${view === id ? 'selected' : ''}`}>
            <input type="radio" name="result-view" checked={view === id} onChange={() => setView(id)} />{label}</label>)}
        </div>
      </div>
      <Compare result={result} base={base} view={view} />
      <section className="viewer-inputs" aria-label="Inputs">
        <p><strong>Made from</strong> {result.prompt_version ? `prompt version ${result.prompt_version}${result.is_polished ? ' (polished)' : ''}, analysis version ${result.analysis_version}` : 'an approval that is no longer available'} · {result.approval_current ? 'the current approval' : 'an earlier approval'}</p>
        <ul className="plain-list">{result.mappings.map(m => <li key={m.subject}><strong>{m.subject}</strong>: {m.action === 'replace' ? `${m.character_name ?? 'Deleted character'} (${imageList(m.images)})` : m.action === 'keep' ? 'Kept original' : 'Not assigned'}</li>)}</ul>
        {result.source === 'manual_import' && <p className="hint">Imported by you{result.note ? ` from ${result.note}` : ''}. The studio did not make this image, so its source is as you described it.</p>}
        {result.recovered && <p className="hint">Found in the run’s own Codex folder after the run did not finish normally.</p>}
      </section>
      {error && <p className="frame-error" role="alert">{error}</p>}
      <div className="dialog-actions viewer-actions">
        <button type="button" className="danger secondary" disabled={busy} onClick={remove}>Delete</button>
        <span className="spacer" />
        {onOpenScene && <button type="button" className="secondary" onClick={onOpenScene}>Open scene</button>}
        <a className="button-link secondary" href={result.image_url} download={`${sceneTitle} - result ${result.version}.${extensions[result.media_type] ?? 'png'}`}>Download</a>
        <button type="button" className="secondary" onClick={onClose}>Close</button>
        <button type="button" className={result.is_preferred ? 'secondary' : ''} disabled={busy} onClick={() => void prefer()}>{result.is_preferred ? 'Remove preferred' : 'Mark as preferred'}</button>
      </div>
    </div>
  </dialog>
}

/** Manual bridge: export the approved package, use any app, then import the image. */
export function ExportDialog({ scene, token, onClose, onChanged, onImport }: {
  scene: SceneDetail; token: string; onClose: () => void; onChanged: (detail: SceneDetail, message: string) => void; onImport: (exportId: string | null) => void
}) {
  const ref = useModal()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const approval = scene.approval.current
  const packaged = scene.exports.find(e => e.approval_current)
  const prompt = scene.prompts.find(p => p.id === approval?.prompt_id)
  async function create() {
    if (!approval) return
    setBusy(true); setError('')
    try {
      const made = await send<{ export_id: string; scene: SceneDetail }>(`/api/scenes/${scene.id}/exports`, 'POST', token, { approval_id: approval.id })
      onChanged(made.scene, 'Package created. Download it to use the files in another app.')
    } catch (e) { setError(e instanceof Error ? e.message : 'The package could not be created.') }
    finally { setBusy(false) }
  }
  return <dialog ref={ref} className="image-dialog manual-dialog" aria-labelledby="export-title" onClose={onClose}>
    <div className="manual-analysis">
      <h2 id="export-title">Export for manual use</h2>
      <p className="hint">Make the image in ChatGPT or any app you use. The package holds exactly the approved inputs: numbered images without location data, the prompt, the negative prompt and who is who. Nothing is sent from the studio.</p>
      {!approval ? <p className="notice-line">Approve the scene first. A package always matches an approval.</p> : <ol className="manual-steps">
        <li><strong>{packaged ? `Package ${packaged.number} is ready.` : 'Create the package.'}</strong> {packaged ? `Made ${formatDate(packaged.created_at)} from the current approval.` : 'It is saved in this scene’s run folders.'}
          <div className="step-actions">{packaged ? <><a className="button-link" href={packaged.download_url} download>Download package (.zip)</a>
            {packaged.job_folder && <button type="button" className="secondary" onClick={() => copyText(packaged.job_folder!, setNote)}>Copy folder path</button>}</>
            : <button type="button" disabled={busy} onClick={() => void create()}>{busy ? 'Creating…' : 'Create package'}</button>}</div></li>
        <li><strong>Attach the images in number order</strong> (image-1.jpg first), then paste the prompt. The README in the package explains each file.
          <div className="step-actions"><button type="button" className="secondary" disabled={!prompt} onClick={() => prompt && copyText(prompt.prompt_text, setNote)}>Copy prompt</button></div></li>
        <li><strong>Import the image you made</strong> so it is saved with this scene and linked to the package.
          <div className="step-actions"><button type="button" className="secondary" onClick={() => onImport(packaged?.id ?? null)}>Import result</button></div></li>
      </ol>}
      <p className="library-status" role="status">{note}</p>
      {error && <p className="frame-error" role="alert">{error}</p>}
      <div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Close</button></div>
    </div>
  </dialog>
}

/** Import an image made elsewhere; it is linked to a package or the current approval. */
export function ImportDialog({ scene, token, data, preselect, onClose, onImported }: {
  scene: SceneDetail; token: string; data: Bootstrap; preselect: string | null; onClose: () => void; onImported: (detail: SceneDetail) => void
}) {
  const ref = useModal()
  const approved = scene.approval.state === 'approved'
  const fallback = preselect ?? scene.exports.find(e => e.approval_current)?.id ?? (approved ? 'approval' : scene.exports[0]?.id ?? '')
  const [link, setLink] = useState(fallback)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState('')
  const [madeWith, setMadeWith] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { if (!file) return; const url = URL.createObjectURL(file); setPreview(url); return () => URL.revokeObjectURL(url) }, [file])
  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!file || !link || busy) return
    if (file.size > data.max_upload_bytes) { setError(`This image is too large. Limit: ${Math.floor(data.max_upload_bytes / 1048576)} MB.`); return }
    setBusy(true); setError('')
    const params = new URLSearchParams()
    if (link !== 'approval') params.set('export_id', link)
    if (madeWith.trim()) params.set('note', madeWith.trim())
    try {
      onImported(await request<SceneDetail>(`/api/scenes/${scene.id}/results?${params}`, {
        method: 'POST', headers: { 'X-Studio-Token': token, 'Content-Type': 'application/octet-stream' }, body: file,
      }, 'Check the image and try again.'))
    } catch (e) { setError(e instanceof Error ? e.message : 'The image could not be imported.') }
    finally { setBusy(false) }
  }
  const options = [...(approved ? [{ id: 'approval', label: `The current approval (${formatDate(scene.approval.current!.approved_at)})` }] : []),
    ...scene.exports.map(e => ({ id: e.id, label: `Package ${e.number} · ${formatDate(e.created_at)}${e.approval_current ? ' · current approval' : ' · earlier approval'}` }))]
  return <dialog ref={ref} className="image-dialog new-scene-dialog" aria-labelledby="import-title" onClose={onClose}>
    <form className="new-scene" onSubmit={e => void submit(e)}>
      <h2 id="import-title">Import result</h2>
      <p className="hint">Add an image you made in another app. It is saved as a new result; earlier results are never replaced.</p>
      {!options.length ? <p className="notice-line">Approve the scene, or export a package first, so the result can be linked to the inputs it was made from.</p> : <fieldset disabled={busy}>
        <div className="new-scene-body">
          <label className={`drop-zone ${preview ? 'has-image' : ''}`}>
            <input className="visually-hidden" type="file" accept="image/jpeg,image/png,image/webp" required onChange={e => { setFile(e.target.files?.[0] ?? null); setError('') }} />
            {preview ? <img src={preview} alt="Selected result" /> : <span><strong>Choose the image</strong><small>JPEG, PNG or WebP · up to {Math.floor(data.max_upload_bytes / 1048576)} MB</small></span>}
          </label>
          <div className="import-fields">
            <div><label htmlFor="import-link">Made from</label>
              <select id="import-link" value={link} onChange={e => setLink(e.target.value)}>{options.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}</select>
              <p className="hint">Choose the package you used, so the result keeps the exact inputs.</p></div>
            <div><label htmlFor="import-note">Made with (optional)</label>
              <input id="import-note" maxLength={120} value={madeWith} placeholder="For example: ChatGPT Images" onChange={e => setMadeWith(e.target.value)} /></div>
          </div>
        </div>
      </fieldset>}
      {error && <p className="frame-error" role="alert">{error}</p>}
      <div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Cancel</button><button disabled={!file || !link || busy}>{busy ? 'Importing…' : 'Import result'}</button></div>
    </form>
  </dialog>
}

/** Step 05: generate from the approval, then compare and keep results. */
export function GeneratePanel({ scene, data, generationEngine, busy, runStatus, exportOpen, onExportOpen, onGenerate, onChanged, onGo }: {
  scene: SceneDetail; data: Bootstrap; generationEngine: string; busy: boolean; runStatus: ReactNode; exportOpen: boolean; onExportOpen: (open: boolean) => void
  onGenerate: (mode: 'generate' | 'variation') => void; onChanged: (detail: SceneDetail, message: string) => void; onGo: () => void
}) {
  const token = data.session_token
  const [viewing, setViewing] = useState<string | null>(null)
  const [importing, setImporting] = useState<string | null | false>(false)
  const [note, setNote] = useState('')
  const approval = scene.approval.state === 'approved' ? scene.approval.current : null
  const codex = generationEngine === 'codex_cli'
  const fromApproval = scene.results.filter(r => r.approval_current)
  const references = scene.subjects.reduce((sum, s) => sum + (s.action === 'replace' ? s.images.length : 0), 0)
  const running = !!scene.active_job
  const shown = scene.results.find(r => r.id === viewing)
  const again = (mode: 'generate' | 'variation') => {
    const what = mode === 'variation' ? 'Make a variation' : 'Generate again'
    if (window.confirm(`${what}? This sends the approved images to OpenAI via Codex once more and uses your ChatGPT plan’s image allowance. Earlier results are kept.`)) onGenerate(mode)
  }
  return <>
    {runStatus}
    {!approval ? <div className="analyse-start">
      <p>{scene.approval.ended_reason ? `${scene.approval.ended_reason} ` : ''}Approve the scene to generate. Approval locks the exact prompt and photos that will be sent.</p>
      <div className="save-row"><button type="button" onClick={onGo}>Go to review</button></div>
    </div> : <div className="generate-card">
      <div className="generate-copy">
        <strong>{fromApproval.length ? `${plural(fromApproval.length, 'result')} from this approval` : 'Ready to generate'}</strong>
        <p>{codex ? <>Generate sends the Base Image and {plural(references, 'reference photo')} to OpenAI via Codex, using your own ChatGPT sign-in. Each attempt uses your plan’s image allowance. It runs once per click and is never retried on its own.</>
          : <>Manual generation is selected in Studio settings. Export the package, make the image in any app, then import it here. Nothing is sent from the studio.</>}</p>
        <p className="hint">Approved {formatDate(approval.approved_at)} · prompt version {approval.prompt_version}{approval.is_polished ? ' (polished)' : ''} · {scene.total_images} {scene.total_images === 1 ? 'image' : 'images'} attached</p>
      </div>
      {codex ? <>
        <div className="generate-actions">
          {fromApproval.length ? <>
            <button type="button" disabled={busy || running} onClick={() => again('generate')}><Spark /> Generate again</button>
            <button type="button" className="secondary" disabled={busy || running} onClick={() => again('variation')}>Variation</button>
          </> : <button type="button" disabled={busy || running} onClick={() => onGenerate('generate')}><Spark /> Generate image</button>}
        </div>
        <p className="manual-links">Prefer another app? <button type="button" className="link-button" disabled={busy} onClick={() => onExportOpen(true)}>Export for manual use</button> · <button type="button" className="link-button" disabled={busy} onClick={() => setImporting(null)}>Import result</button></p>
      </> : <div className="generate-actions">
        <button type="button" disabled={busy} onClick={() => onExportOpen(true)}>Export for manual use</button>
        <button type="button" className="secondary" disabled={busy} onClick={() => setImporting(null)}>Import result</button>
      </div>}
    </div>}

    <div className="results-head"><h4>Results {scene.results.length > 0 && <span className="hint">({scene.results.length})</span>}</h4>
      {!approval && scene.results.length > 0 && <button type="button" className="link-button" disabled={busy} onClick={() => setImporting(null)}>Import result</button>}</div>
    {!scene.results.length ? <p className="hint">No results yet. Every image you generate or import is kept here as its own version, linked to the inputs it was made from.</p>
      : <div className="result-grid">{scene.results.map(r => <ResultCard key={r.id} result={r} onOpen={() => setViewing(r.id)} />)}</div>}

    {scene.exports.length > 0 && <details className="package-list"><summary>Manual packages ({scene.exports.length})</summary>
      <ul>{scene.exports.map(e => <li key={e.id}>
        <div><strong>Package {e.number}</strong> <span className="hint">{formatDate(e.created_at)} · {e.approval_current ? 'current approval' : 'earlier approval'}{e.photos_removed ? ` · ${plural(e.photos_removed, 'photo')} removed` : ''}</span></div>
        <span className={`run-status ${e.result_count ? 'completed' : ''}`}>{e.result_count ? `${plural(e.result_count, 'result')} imported` : 'Waiting for import'}</span>
        <span className="package-actions"><a className="link-button" href={e.download_url} download>Download</a>
          <button type="button" className="link-button" onClick={() => setImporting(e.id)}>Import result</button>
          {e.job_folder && <button type="button" className="link-button" onClick={() => copyText(e.job_folder!, setNote)}>Copy folder path</button>}</span>
      </li>)}</ul></details>}
    <p className="library-status" role="status">{note}</p>

    {shown && <ResultViewer key={shown.id} result={shown} base={{ url: scene.original_url, width: scene.width, height: scene.height }} sceneTitle={scene.title} token={token}
      onClose={() => setViewing(null)} onChanged={(detail, message) => { onChanged(detail, message) }} />}
    {exportOpen && <ExportDialog scene={scene} token={token} onClose={() => onExportOpen(false)} onChanged={onChanged} onImport={id => { onExportOpen(false); setImporting(id) }} />}
    {importing !== false && <ImportDialog scene={scene} token={token} data={data} preselect={importing} onClose={() => setImporting(false)}
      onImported={detail => { setImporting(false); onChanged(detail, `Result ${detail.results[0]?.version} imported.`) }} />}
  </>
}

function Spark() {
  return <svg className="inline-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"><path d="M12 3l1.8 4.6L18.5 9.5l-4.7 1.9L12 16l-1.8-4.6L5.5 9.5l4.7-1.9z" /></svg>
}

/** The Results page: every result from every scene, newest first. */
export default function ResultsGallery({ data, onOpenScene }: { data: Bootstrap; onOpenScene: (sceneId: string) => void }) {
  const [results, setResults] = useState<Result[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [query, setQuery] = useState('')
  const [preferred, setPreferred] = useState(false)
  const [viewing, setViewing] = useState<string | null>(null)
  const load = useCallback(() => request<Result[]>('/api/results').then(list => { setResults(list); setError('') }, e => setError(e.message)).finally(() => setLoading(false)), [])
  useEffect(() => { void load() }, [load])
  const filtered = results.filter(r => (r.scene_title ?? '').toLocaleLowerCase().includes(query.toLocaleLowerCase()) && (!preferred || r.is_preferred))
  const shown = results.find(r => r.id === viewing)
  return <div className="results-page">
    <div className="library-toolbar filters">
      <div><label htmlFor="result-search">Search results</label><input id="result-search" type="search" value={query} placeholder="Search by scene title" onChange={e => setQuery(e.target.value)} /></div>
      <label className="checkbox-label"><input type="checkbox" checked={preferred} onChange={e => setPreferred(e.target.checked)} /> Preferred only</label>
    </div>
    {error && <div className="error" role="alert"><strong>Your results could not be loaded.</strong><p>{error}</p><button className="secondary" onClick={() => void load()}>Try again</button></div>}
    <p className="library-status" role="status">{message}</p>
    {loading ? <p role="status">Loading your results…</p> : !filtered.length ? <div className="empty-library panel"><span className="tiny-label">EVERY VERSION HAS A HOME.</span>
      <h2>{results.length ? 'No matching results' : 'Your results will appear here'}</h2>
      <p>{results.length ? 'Try another title or show all results.' : 'Approve a scene, then generate it with Codex or import an image you made elsewhere. Every result is kept with the exact inputs it was made from.'}</p></div>
      : <div className="result-grid gallery">{filtered.map(r => <ResultCard key={r.id} result={r} title={r.scene_title} onOpen={() => setViewing(r.id)} />)}</div>}
    {shown && <ResultViewer key={shown.id} result={shown} base={{ url: shown.scene_image_url!, width: shown.scene_width!, height: shown.scene_height! }} sceneTitle={shown.scene_title ?? ''} token={data.session_token}
      onClose={() => setViewing(null)} onChanged={(_detail, note) => { setMessage(note); void load() }} onOpenScene={() => onOpenScene(shown.scene_id)} />}
  </div>
}
