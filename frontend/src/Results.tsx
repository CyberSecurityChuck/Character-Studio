import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { request, send, type Bootstrap } from './api'
import { Comparison, type CompareBox, type CompareImage } from './Compare'
import { CardMenu, Glyph, SelectionBar, type MenuItem } from './Controls'
import { PresetSelect, usePresets } from './Presets'
import { QualityPanel, checkBadge, type QualityCheck } from './Quality'
import type { SceneDetail } from './Scenes'

export type ResultMapping = { subject: string; action: string; character_name: string | null; images: number[] }
export type Result = {
  id: string; scene_id: string; version: number; approval_id: string; approval_current: boolean; job_id: string | null
  source: 'codex_cli' | 'manual_import'; mode: 'generate' | 'variation' | 'import'; note: string; media_type: string; width: number; height: number
  engine_version: string | null; recovered: boolean; seconds: number | null; is_preferred: boolean; created_at: string; image_url: string; thumbnail_url: string
  preset: string | null; check: QualityCheck | null
  prompt_version: number | null; analysis_version: number | null; is_polished: boolean; mappings: ResultMapping[]
  scene_title?: string; scene_image_url?: string; scene_width?: number; scene_height?: number
}
export type ExportPackage = { id: string; number: number; created_at: string; approval_id: string; approval_current: boolean; result_count: number; photos_removed: number; job_folder: string | null; download_url: string }
export type Base = { url: string; width: number; height: number }

const formatDate = (value: string) => new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`
const imageList = (images: number[]) => images.map(n => `Image ${n}`).join(', ')
/** "48 s" or "1 min 12 s": how long a Codex run took. */
export const duration = (seconds: number) => seconds < 60 ? `${seconds} s` : `${Math.floor(seconds / 60)} min${seconds % 60 ? ` ${seconds % 60} s` : ''}`

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
export function ResultCard({ result, onOpen, title, selecting, picked, menu, disabled }: { result: Result; onOpen: () => void; title?: string; selecting?: boolean; picked?: boolean; menu?: MenuItem[]; disabled?: boolean }) {
  const label = `result ${result.version}${title ? ` of ${title}` : ''}`
  const side = [result.seconds != null ? duration(result.seconds) : '', result.approval_current ? '' : 'Earlier approval'].filter(Boolean).join(' · ')
  const badge = checkBadge(result.check)
  return <div className={`result-card ${picked ? 'picked' : ''}`}>
    <button type="button" className="card-main" disabled={disabled} aria-pressed={selecting ? !!picked : undefined} onClick={onOpen} aria-label={selecting ? `Select ${label}` : `Open ${label}`}>
      {selecting && <span className="pick-box" aria-hidden="true" />}
      <span className="result-thumb"><img src={result.thumbnail_url} alt="" loading="lazy" />{result.is_preferred && <span className="preferred-badge" aria-label="Preferred">★ Preferred</span>}</span>
      <span className="result-copy">
        {title && <strong className="result-scene">{title}</strong>}
        <span className="result-line"><strong>Result {result.version}</strong><span className="hint">{formatDate(result.created_at)}</span></span>
        <span className="result-line"><span className="source-chip">{sourceLabel(result)}</span>{side && <span className="hint" title={result.seconds != null ? 'How long Codex took to make it' : undefined}>{side}</span>}</span>
        {badge && <span className="result-line"><span className={`check-chip ${badge.tone}`} title="Latest quality check (the weaker of composition and identity)">Check: {badge.label}</span></span>}
      </span>
    </button>
    {!selecting && menu && <CardMenu label={`Result ${result.version}${title ? ` of ${title}` : ''}`} items={menu} disabled={disabled} />}
  </div>
}

/** Results with a ⋯ menu each and a Select mode for several at once (like Scenes and Characters). */
export function ResultsGrid({ results, token, titleOf, showTitles, selecting, onSelecting, onOpen, onChanged, baseOf, boxes = [], className = '' }: {
  results: Result[]; token: string; titleOf: (r: Result) => string; showTitles?: boolean; selecting: boolean; onSelecting: (on: boolean) => void
  onOpen: (id: string) => void; onChanged: (detail: SceneDetail | null, message: string) => void; baseOf: (r: Result) => Base; boxes?: CompareBox[]; className?: string
}) {
  const [picked, setPicked] = useState<string[]>([])
  const [comparing, setComparing] = useState<Result[] | null>(null)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { if (!selecting) setPicked([]) }, [selecting])
  useEffect(() => { setPicked(old => old.filter(id => results.some(r => r.id === id))) }, [results])
  const chosen = results.filter(r => picked.includes(r.id))
  const name = (r: Result) => `${titleOf(r)} - result ${r.version}.${extensions[r.media_type] ?? 'png'}`
  const what = (list: Result[]) => list.length === 1 ? `result ${list[0].version}` : `${list.length} results`

  function download(list: Result[]) {
    // One image downloads as itself; several come as one zip.
    const link = document.createElement('a')
    link.href = list.length === 1 ? list[0].image_url : `/api/results/download?${list.map(r => `id=${r.id}`).join('&')}`
    link.download = list.length === 1 ? name(list[0]) : 'Character Studio results.zip'
    document.body.append(link); link.click(); link.remove()
  }
  // Each item goes through the single-result endpoint; failures are reported by name.
  async function each(list: Result[], call: (r: Result) => Promise<SceneDetail>, done: string) {
    setWorking(true); setError('')
    let last: SceneDetail | null = null
    const failed: string[] = []
    for (const r of list) {
      try { last = await call(r) } catch { failed.push(`Result ${r.version}${showTitles ? ` (${titleOf(r)})` : ''}`) }
    }
    setWorking(false)
    if (failed.length) setError(`Not done for ${failed.join(', ')}. The others were done. Reload and try again.`)
    onChanged(last, failed.length ? '' : done)
  }
  const prefer = (list: Result[], value: boolean) => each(list,
    r => send<SceneDetail>(`/api/results/${r.id}/preferred`, 'PUT', token, { preferred: value }),
    value ? `${list.length === 1 ? `Result ${list[0].version} is` : `${list.length} results are`} now preferred.` : `${list.length === 1 ? `Result ${list[0].version} is` : `${list.length} results are`} no longer preferred.`)
  function remove(list: Result[]) {
    if (!window.confirm(`Permanently delete ${what(list)}? ${list.length === 1 ? 'Its image file is' : 'Their image files are'} removed from this computer. Other results keep their numbers.`)) return
    void each(list, async r => (await send<{ scene: SceneDetail }>(`/api/results/${r.id}`, 'DELETE', token)).scene,
      `${what(list).charAt(0).toUpperCase()}${what(list).slice(1)} deleted.`).then(() => onSelecting(false))
  }
  const menuFor = (r: Result): MenuItem[] => [
    { label: 'Download', onSelect: () => download([r]) },
    { label: r.is_preferred ? 'Remove preferred' : 'Mark as preferred', onSelect: () => void prefer([r], !r.is_preferred) },
    { label: 'Delete', danger: true, onSelect: () => remove([r]) },
  ]
  return <>
    {selecting && <SelectionBar count={chosen.length} total={results.length} onAll={() => setPicked(results.map(r => r.id))} onNone={() => setPicked([])} onDone={() => onSelecting(false)}>
      <button type="button" className="secondary" disabled={working || !chosen.length} onClick={() => download(chosen)}>Download</button>
      <button type="button" className="secondary" disabled={working || !chosen.length} onClick={() => void prefer(chosen, true)}>Mark as preferred</button>
      {chosen.some(r => r.is_preferred) && <button type="button" className="secondary" disabled={working} onClick={() => void prefer(chosen.filter(r => r.is_preferred), false)}>Remove preferred</button>}
      <button type="button" className="secondary" disabled={working || chosen.length < 2 || chosen.length > 4 || new Set(chosen.map(r => r.scene_id)).size > 1}
        title={new Set(chosen.map(r => r.scene_id)).size > 1 ? 'Choose results of one scene' : 'Choose 2 to 4 results'} onClick={() => setComparing(chosen)}><Glyph name="compare" />Compare</button>
      <button type="button" className="danger secondary" disabled={working || !chosen.length} onClick={() => remove(chosen)}>Delete</button>
    </SelectionBar>}
    {comparing && <CompareDialog results={comparing} base={baseOf(comparing[0])} boxes={boxes} title={titleOf(comparing[0])} onClose={() => setComparing(null)} />}
    {error && <p className="frame-error" role="alert">{error}</p>}
    <div className={`result-grid ${className}`}>{results.map(r => <ResultCard key={r.id} result={r} title={showTitles ? titleOf(r) : undefined} selecting={selecting} picked={picked.includes(r.id)} disabled={working}
      menu={menuFor(r)} onOpen={() => selecting ? setPicked(old => old.includes(r.id) ? old.filter(x => x !== r.id) : [...old, r.id]) : onOpen(r.id)} />)}</div>
  </>
}

const baseImage = (base: Base): CompareImage => ({ id: 'base', label: 'Base Image', ...base })
const resultImage = (r: Result): CompareImage => ({ id: r.id, label: `Result ${r.version}`, url: r.image_url, width: r.width, height: r.height })

/** Several results of one scene next to the Base Image, with shared zoom and pan. */
function CompareDialog({ results, base, boxes, title, onClose }: { results: Result[]; base: Base; boxes: CompareBox[]; title: string; onClose: () => void }) {
  const ref = useModal()
  const sorted = [...results].sort((a, b) => a.version - b.version)
  const images = [baseImage(base), ...sorted.map(resultImage)]
  return <dialog ref={ref} className="image-dialog viewer-dialog" aria-labelledby="compare-title" onClose={onClose}>
    <div className="viewer-body">
      <div className="viewer-head"><div><h2 id="compare-title">Compare {sorted.length} results</h2><p className="hint">{title} · {sorted.map(r => `Result ${r.version}${r.check ? ` (${checkBadge(r.check)?.label})` : ''}`).join(', ')}</p></div></div>
      <Comparison images={images} frame={base} boxes={boxes} modes={['side', 'slider', 'overlay', 'difference']} initialMode="side"
        initialA={sorted[0].id} initialB="base" sideIds={images.map(i => i.id)} />
      <div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Close</button></div>
    </div>
  </dialog>
}

/** View a result, compare it with the Base Image, choose it as preferred, download or delete it. */
export function ResultViewer({ result, base, sceneTitle, token, others = [], boxes = [], runningCheck, onClose, onChanged, onCheckDone, onOpenScene }: {
  result: Result; base: Base; sceneTitle: string; token: string; others?: Result[]; boxes?: CompareBox[]; runningCheck?: string | null; onClose: () => void
  onChanged: (detail: SceneDetail, message: string) => void; onCheckDone?: () => void; onOpenScene?: () => void
}) {
  const ref = useModal()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function act(action: () => Promise<void>) {
    setBusy(true); setError('')
    try { await action() } catch (e) { setError(e instanceof Error ? e.message : 'That did not work. Try again.') } finally { setBusy(false) }
  }
  const prefer = () => act(async () => {
    const detail = await send<SceneDetail>(`/api/results/${result.id}/preferred`, 'PUT', token, { preferred: !result.is_preferred })
    onChanged(detail, result.is_preferred ? `Result ${result.version} is no longer preferred.` : `Result ${result.version} is now marked as preferred.`)
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
          <p className="hint">{sceneTitle} · {formatDate(result.created_at)} · {sourceLabel(result)}{result.engine_version ? ` · ${result.engine_version}` : ''}{result.seconds != null ? ` · generated in ${duration(result.seconds)}` : ''}{result.preset ? ` · preset “${result.preset}”` : ''} · {result.width} × {result.height}</p></div>
      </div>
      <Comparison images={[baseImage(base), resultImage(result), ...others.filter(o => o.id !== result.id).sort((a, b) => a.version - b.version).map(resultImage)]} frame={base} boxes={boxes}
        modes={['single', 'side', 'slider', 'overlay', 'difference']} initialMode="side" initialA={result.id} initialB="base" />
      <div className="viewer-columns">
      <section className="viewer-inputs" aria-label="Inputs">
        <p><strong>Made from</strong> {result.prompt_version ? `prompt version ${result.prompt_version}${result.is_polished ? ' (polished)' : ''}, analysis version ${result.analysis_version}` : 'an approval that is no longer available'} · {result.approval_current ? 'the current approval' : 'an earlier approval'}</p>
        <ul className="plain-list">{result.mappings.map(m => <li key={m.subject}><strong>{m.subject}</strong>: {m.action === 'replace' ? `${m.character_name ?? 'Deleted character'} (${imageList(m.images)})` : m.action === 'keep' ? 'Kept original' : 'Not assigned'}</li>)}</ul>
        {result.source === 'manual_import' && <p className="hint">Imported by you{result.note ? ` from ${result.note}` : ''}. The studio did not make this image, so its source is as you described it.</p>}
        {result.recovered && <p className="hint">Found in the run’s own Codex folder after the run did not finish normally.</p>}
      </section>
      <QualityPanel resultId={result.id} resultVersion={result.version} token={token} runningJobId={runningCheck}
        references={result.mappings.reduce((sum, m) => sum + (m.action === 'replace' ? m.images.length : 0), 0)}
        onStarted={detail => onChanged(detail, `Checking result ${result.version}…`)} onDone={onCheckDone} />
      </div>
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
export function GeneratePanel({ scene, data, generationEngine, busy, runStatus, exportOpen, onExportOpen, onGenerate, onChanged, onRefresh, onGo }: {
  scene: SceneDetail; data: Bootstrap; generationEngine: string; busy: boolean; runStatus: ReactNode; exportOpen: boolean; onExportOpen: (open: boolean) => void
  onGenerate: (mode: 'generate' | 'variation', count: number, presetId: string | null) => void; onChanged: (detail: SceneDetail, message: string) => void; onRefresh: (message: string) => void; onGo: () => void
}) {
  const { presets } = usePresets()
  const [presetId, setPresetId] = useState('')
  const [selecting, setSelecting] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)
  // Several images from this approval run as a small batch, one after another (Phase 5.5).
  const [count, setCount] = useState(1)
  const timing = scene.generation_timing
  async function removePackage(e: ExportPackage) {
    const imported = e.result_count ? ` The ${plural(e.result_count, 'result')} you imported from it ${e.result_count === 1 ? 'is' : 'are'} kept and stay${e.result_count === 1 ? 's' : ''} linked to ${e.result_count === 1 ? 'its' : 'their'} approval.` : ''
    if (!window.confirm(`Delete package ${e.number}? Its folder is removed from this computer: the copies of the approved photos, the prompt files and the zip.${imported} Packages you already downloaded are not affected.`)) return
    setDeleting(e.id)
    try {
      const done = await send<{ scene: SceneDetail; cleanup_pending: boolean }>(`/api/exports/${e.id}`, 'DELETE', token)
      onChanged(done.scene, done.cleanup_pending ? `Package ${e.number} removed from the list. Some files are locked and will be deleted after a restart.` : `Package ${e.number} deleted.`)
    } catch (err) { setNote(err instanceof Error ? err.message : 'The package could not be deleted.') }
    finally { setDeleting(null) }
  }
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
  const base = { url: scene.original_url, width: scene.width, height: scene.height }
  const boxes = scene.analyses[0]?.analysis.subjects.map(s => ({ label: s.label, bounding_box: s.bounding_box })) ?? []
  const estimate = timing.average_seconds != null && count > 1 ? ` (about ${duration(timing.average_seconds * count)} in all)` : ''
  const again = (mode: 'generate' | 'variation') => {
    const what = count > 1 ? (mode === 'variation' ? `Make ${count} variations` : `Generate ${count} more images`) : mode === 'variation' ? 'Make a variation' : 'Generate again'
    const runs = count > 1 ? `This makes ${count} runs, one after another${estimate}, each sending the approved images to OpenAI via Codex` : 'This sends the approved images to OpenAI via Codex once more'
    if (window.confirm(`${what}? ${runs} and using your ChatGPT plan’s image allowance. Earlier results are kept.`)) onGenerate(mode, count, presetId || null)
  }
  const first = () => {
    if (count === 1 || window.confirm(`Generate ${count} images? This makes ${count} runs, one after another${estimate}, each sending the approved images to OpenAI via Codex and using your ChatGPT plan’s image allowance.`)) onGenerate('generate', count, presetId || null)
  }
  return <>
    {runStatus}
    {!approval ? <div className="analyse-start">
      <p>{scene.approval.ended_reason ? `${scene.approval.ended_reason} ` : ''}Approve the scene to generate. Approval locks the exact prompt and photos that will be sent.</p>
      <div className="save-row"><button type="button" onClick={onGo}>Go to review</button></div>
    </div> : <div className="generate-card">
      <div className="generate-copy">
        <strong>{fromApproval.length ? `${plural(fromApproval.length, 'result')} from this approval` : 'Ready to generate'}</strong>
        <p>{codex ? <>Generate sends the Base Image and {plural(references, 'reference photo')} to OpenAI via Codex, using your own ChatGPT sign-in. Each image is one run from your plan’s image allowance; several images run one after another. Nothing is retried on its own.</>
          : <>Manual generation is selected in Studio settings. Export the package, make the image in any app, then import it here. Nothing is sent from the studio.</>}</p>
        <p className="hint">Approved {formatDate(approval.approved_at)} · prompt version {approval.prompt_version}{approval.is_polished ? ' (polished)' : ''} · {scene.total_images} {scene.total_images === 1 ? 'image' : 'images'} attached</p>
        {timing.average_seconds != null && <p className="hint">Codex has taken about {duration(timing.average_seconds)} per image on this computer ({plural(timing.runs, 'finished run')}).</p>}
      </div>
      {codex ? <>
        {presets.length > 0 && <div className="generate-preset"><PresetSelect id="generate-preset" presets={presets} value={presetId} disabled={busy || running} label="Preset"
          onChange={p => { setPresetId(p?.id ?? ''); if (p) setCount(p.images) }} /></div>}
        <div className="generate-actions">
          <div className="image-count" role="group" aria-label="Images per click">
            <button type="button" className="secondary compact icon-only" aria-label="Fewer images" disabled={busy || running || count <= 1} onClick={() => setCount(c => c - 1)}>−</button>
            <span aria-live="polite">{count} {count === 1 ? 'image' : 'images'}</span>
            <button type="button" className="secondary compact icon-only" aria-label="More images" disabled={busy || running || count >= 10} onClick={() => setCount(c => c + 1)}>+</button>
          </div>
          {fromApproval.length ? <>
            <button type="button" disabled={busy || running} onClick={() => again('generate')}><Spark /> {count > 1 ? `Generate ${count} more` : 'Generate again'}</button>
            <button type="button" className="secondary" disabled={busy || running} onClick={() => again('variation')}>{count > 1 ? `${count} variations` : 'Variation'}</button>
          </> : <button type="button" disabled={busy || running} onClick={first}><Spark /> {count > 1 ? `Generate ${count} images` : 'Generate image'}</button>}
        </div>
        <p className="manual-links">Prefer another app? <button type="button" className="link-button" disabled={busy} onClick={() => onExportOpen(true)}>Export for manual use</button> · <button type="button" className="link-button" disabled={busy} onClick={() => setImporting(null)}>Import result</button></p>
      </> : <div className="generate-actions">
        <button type="button" disabled={busy} onClick={() => onExportOpen(true)}>Export for manual use</button>
        <button type="button" className="secondary" disabled={busy} onClick={() => setImporting(null)}>Import result</button>
      </div>}
    </div>}

    <div className="results-head"><h4>Results {scene.results.length > 0 && <span className="hint">({scene.results.length})</span>}</h4>
      <span className="results-head-actions">
        {!approval && scene.results.length > 0 && <button type="button" className="link-button" disabled={busy} onClick={() => setImporting(null)}>Import result</button>}
        {scene.results.length > 0 && !selecting && <button type="button" className="secondary compact" disabled={busy} onClick={() => setSelecting(true)}>Select</button>}
      </span></div>
    {!scene.results.length ? <p className="hint">No results yet. Every image you generate or import is kept here as its own version, linked to the inputs it was made from.</p>
      : <ResultsGrid results={scene.results} token={token} titleOf={() => scene.title} selecting={selecting} onSelecting={setSelecting} onOpen={setViewing}
        baseOf={() => base} boxes={boxes}
        onChanged={(detail, message) => { if (detail) onChanged(detail, message); else onRefresh(message) }} />}

    {scene.exports.length > 0 && <details className="package-list"><summary>Manual packages ({scene.exports.length})</summary>
      <ul>{scene.exports.map(e => <li key={e.id}>
        <div><strong>Package {e.number}</strong> <span className="hint">{formatDate(e.created_at)} · {e.approval_current ? 'current approval' : 'earlier approval'}{e.photos_removed ? ` · ${plural(e.photos_removed, 'photo')} removed` : ''}</span></div>
        <span className={`run-status ${e.result_count ? 'completed' : ''}`}>{e.result_count ? `${plural(e.result_count, 'result')} imported` : 'Waiting for import'}</span>
        <span className="package-actions"><a className="button-link compact" href={e.download_url} download><Glyph name="download" />Download</a>
          <button type="button" className="secondary compact" disabled={busy || deleting === e.id} onClick={() => setImporting(e.id)}><Glyph name="import" />Import result</button>
          {e.job_folder && <button type="button" className="secondary compact" onClick={() => copyText(e.job_folder!, setNote)}><Glyph name="folder" />Copy folder path</button>}
          <button type="button" className="danger secondary compact" disabled={busy || deleting === e.id} onClick={() => void removePackage(e)}><Glyph name="trash" />{deleting === e.id ? 'Deleting…' : 'Delete'}</button></span>
      </li>)}</ul></details>}
    <p className="library-status" role="status">{note}</p>

    {shown && <ResultViewer key={shown.id} result={shown} base={base} sceneTitle={scene.title} token={token} others={scene.results} boxes={boxes}
      runningCheck={scene.active_job?.kind === 'check' && scene.active_job.input_id === shown.id ? scene.active_job.id : null}
      onClose={() => setViewing(null)} onChanged={(detail, message) => { onChanged(detail, message) }} onCheckDone={() => onRefresh('')} />}
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
  const [selecting, setSelecting] = useState(false)
  const load = useCallback(() => request<Result[]>('/api/results').then(list => { setResults(list); setError('') }, e => setError(e.message)).finally(() => setLoading(false)), [])
  useEffect(() => { void load() }, [load])
  const filtered = results.filter(r => (r.scene_title ?? '').toLocaleLowerCase().includes(query.toLocaleLowerCase()) && (!preferred || r.is_preferred))
  const shown = results.find(r => r.id === viewing)
  return <div className="results-page">
    <div className="library-toolbar filters">
      <div><label htmlFor="result-search">Search results</label><input id="result-search" type="search" value={query} placeholder="Search by scene title" onChange={e => setQuery(e.target.value)} /></div>
      <label className="checkbox-label"><input type="checkbox" checked={preferred} onChange={e => setPreferred(e.target.checked)} /> Preferred only</label>
      {!selecting && filtered.length > 0 && <button type="button" className="secondary" onClick={() => setSelecting(true)}>Select</button>}
    </div>
    {error && <div className="error" role="alert"><strong>Your results could not be loaded.</strong><p>{error}</p><button className="secondary" onClick={() => void load()}>Try again</button></div>}
    <p className="library-status" role="status">{message}</p>
    {loading ? <p role="status">Loading your results…</p> : !filtered.length ? <div className="empty-library panel"><span className="tiny-label">EVERY VERSION HAS A HOME.</span>
      <h2>{results.length ? 'No matching results' : 'Your results will appear here'}</h2>
      <p>{results.length ? 'Try another title or show all results.' : 'Approve a scene, then generate it with Codex or import an image you made elsewhere. Every result is kept with the exact inputs it was made from.'}</p></div>
      : <ResultsGrid className="gallery" results={filtered} token={data.session_token} titleOf={r => r.scene_title ?? 'Scene'} showTitles selecting={selecting} onSelecting={setSelecting} onOpen={setViewing}
        baseOf={r => ({ url: r.scene_image_url!, width: r.scene_width!, height: r.scene_height! })}
        onChanged={(_detail, note) => { setMessage(note); void load() }} />}
    {shown && <ResultViewer key={shown.id} result={shown} base={{ url: shown.scene_image_url!, width: shown.scene_width!, height: shown.scene_height! }} sceneTitle={shown.scene_title ?? ''} token={data.session_token}
      others={results.filter(r => r.scene_id === shown.scene_id)}
      onClose={() => setViewing(null)} onChanged={(_detail, note) => { setMessage(note); void load() }} onCheckDone={() => void load()} onOpenScene={() => onOpenScene(shown.scene_id)} />}
  </div>
}
