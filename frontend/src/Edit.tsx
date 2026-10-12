import { useEffect, useRef, useState, type PointerEvent } from 'react'
import { request, send } from './api'
import { ChargeDialog, useApiEngines } from './ApiEngines'
import { Glyph, InfoTip } from './Controls'
import type { Result } from './Results'
import type { SceneDetail } from './Scenes'

/** Region edits (Phase 6C-2): mark an area of a result, then fix it or replace one person
 *  with that subject's approved photos. Only the marked area is pasted back. */
type EditOption = {
  id: string; name: string; engine: string; company: string; kinds: string[]; area: 'mask' | 'guided' | 'box' | 'words'
  charged: boolean; model: string | null; options: { size?: string; quality?: string }; available: boolean; reason: string | null
}
type Tool = 'brush' | 'erase' | 'rect'
type Point = { x: number; y: number }

const areaNotes: Record<EditOption['area'], string> = {
  mask: 'follows the marked area exactly',
  guided: 'uses the marked area as a guide',
  box: 'works on a box around the marked area',
  words: 'is told where the area is in words',
}
const PAINT = 'rgb(214, 92, 50)'
const MAX_UNDO = 20

export function EditDialog({ result, token, onClose, onQueued }: {
  result: Result; token: string; onClose: () => void; onQueued: (detail: SceneDetail, message: string) => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const [options, setOptions] = useState<EditOption[]>([])
  const replaceable = result.mappings.filter(m => m.action === 'replace' && m.images.length)
  const [kind, setKind] = useState<'fix' | 'replace'>('fix')
  const [subject, setSubject] = useState(replaceable[0]?.subject ?? '')
  const [instruction, setInstruction] = useState('')
  const [optionId, setOptionId] = useState('')
  const [tool, setTool] = useState<Tool>('brush')
  const [brush, setBrush] = useState(Math.max(12, Math.round(Math.min(result.width, result.height) / 18)))
  const [marked, setMarked] = useState(false)
  const [undo, setUndo] = useState<ImageData[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [asking, setAsking] = useState(false)
  const drag = useRef<{ start: Point; last: Point; before: ImageData } | null>(null)
  const [rect, setRect] = useState<{ a: Point; b: Point } | null>(null)
  const api = useApiEngines()

  useEffect(() => { ref.current?.showModal() }, [])
  useEffect(() => {
    request<EditOption[]>('/api/edit-options').then(list => {
      setOptions(list)
      setOptionId(id => id || (list.find(o => o.available && o.kinds.includes('fix'))?.id ?? list[0]?.id ?? ''))
    }, () => setError('The edit engines could not be loaded. Close and try again.'))
  }, [])

  const usable = options.filter(o => o.kinds.includes(kind))
  const option = usable.find(o => o.id === optionId)
  useEffect(() => {
    // A FLUX.1 Fill choice cannot replace a person: move to the first engine that can.
    if (options.length && !usable.some(o => o.id === optionId)) setOptionId(usable.find(o => o.available)?.id ?? usable[0]?.id ?? '')
  }, [kind, options]) // eslint-disable-line react-hooks/exhaustive-deps

  const context = () => canvas.current!.getContext('2d', { willReadFrequently: true })!
  const snapshot = () => context().getImageData(0, 0, result.width, result.height)
  const remember = (before: ImageData) => setUndo(u => [...u.slice(-(MAX_UNDO - 1)), before])
  function refreshMarked() {
    const data = snapshot().data
    let any = false
    for (let i = 3; i < data.length; i += 16) if (data[i] > 127) { any = true; break }
    setMarked(any)
  }
  function point(e: PointerEvent<HTMLCanvasElement>): Point {
    const box = e.currentTarget.getBoundingClientRect()
    return { x: (e.clientX - box.left) * result.width / box.width, y: (e.clientY - box.top) * result.height / box.height }
  }
  function stroke(from: Point, to: Point) {
    const c = context()
    c.globalCompositeOperation = tool === 'erase' ? 'destination-out' : 'source-over'
    c.strokeStyle = PAINT; c.lineWidth = brush; c.lineCap = 'round'; c.lineJoin = 'round'
    c.beginPath(); c.moveTo(from.x, from.y); c.lineTo(to.x, to.y); c.stroke()
  }
  function fillBox(x0: number, y0: number, x1: number, y1: number) {
    const c = context()
    c.globalCompositeOperation = 'source-over'; c.fillStyle = PAINT
    c.fillRect(Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0))
  }
  function down(e: PointerEvent<HTMLCanvasElement>) {
    if (busy) return
    e.currentTarget.setPointerCapture(e.pointerId)
    const p = point(e)
    drag.current = { start: p, last: p, before: snapshot() }
    if (tool === 'rect') setRect({ a: p, b: p })
    else stroke(p, p)
  }
  function move(e: PointerEvent<HTMLCanvasElement>) {
    if (!drag.current) return
    const p = point(e)
    if (tool === 'rect') setRect({ a: drag.current.start, b: p })
    else stroke(drag.current.last, p)
    drag.current.last = p
  }
  function up() {
    if (!drag.current) return
    if (tool === 'rect' && rect) fillBox(rect.a.x, rect.a.y, rect.b.x, rect.b.y)
    remember(drag.current.before)
    drag.current = null; setRect(null); refreshMarked()
  }
  /** Mark a subject's approved box, a little larger so hair and edges are included. */
  function markSubject(label: string) {
    const box = result.mappings.find(m => m.subject === label)?.box
    if (!box) return
    remember(snapshot())
    const padX = box.width * 0.06, padY = box.height * 0.04
    fillBox(Math.max(0, box.x - padX) * result.width, Math.max(0, box.y - padY) * result.height,
      Math.min(1, box.x + box.width + padX) * result.width, Math.min(1, box.y + box.height + padY) * result.height)
    refreshMarked()
  }
  function stepBack() {
    const last = undo[undo.length - 1]
    if (!last) return
    context().putImageData(last, 0, 0); setUndo(u => u.slice(0, -1)); refreshMarked()
  }
  function clear() {
    remember(snapshot()); context().clearRect(0, 0, result.width, result.height); refreshMarked()
  }
  function maskData() {
    const out = document.createElement('canvas')
    out.width = result.width; out.height = result.height
    const c = out.getContext('2d')!
    const source = snapshot(), mask = c.createImageData(result.width, result.height)
    for (let i = 0; i < source.data.length; i += 4) {
      const v = source.data[i + 3] > 127 ? 255 : 0
      mask.data[i] = mask.data[i + 1] = mask.data[i + 2] = v; mask.data[i + 3] = 255
    }
    c.putImageData(mask, 0, 0)
    return out.toDataURL('image/png')
  }
  function chooseKind(next: 'fix' | 'replace') {
    setKind(next)
    if (next === 'replace' && subject && !marked) markSubject(subject)
  }

  const ready = !!option?.available && marked && (kind === 'replace' ? !!subject : instruction.trim().length >= 3)
  const references = kind === 'replace' ? result.mappings.find(m => m.subject === subject)?.images.length ?? 0 : 0
  const sends = `result ${result.version}${kind === 'replace' ? ` and ${references} approved ${references === 1 ? 'photo' : 'photos'} of ${subject}` : ''}${option?.area === 'mask' || option?.area === 'guided' ? ' with the marked area' : ''} (without location data)`
  async function submit(confirmed: boolean) {
    if (!option) return
    setBusy(true); setError('')
    try {
      const detail = await send<SceneDetail>(`/api/results/${result.id}/edit`, 'POST', token, {
        kind, option: option.id, subject: kind === 'replace' ? subject : null, instruction, mask: maskData(), confirm_charges: confirmed,
      })
      onQueued(detail, `Editing result ${result.version} with ${option.name}…`)
      onClose()
    } catch (e) { setError(e instanceof Error ? e.message : 'The edit could not be started.'); setBusy(false) }
  }
  function start() {
    if (!option || !ready) return
    if (option.charged) { setAsking(true); return }
    if (window.confirm(`Edit with Codex? This sends ${sends} to OpenAI via Codex once and uses your ChatGPT plan’s image allowance.`)) void submit(false)
  }

  const overlay = rect ? { left: `${Math.min(rect.a.x, rect.b.x) / result.width * 100}%`, top: `${Math.min(rect.a.y, rect.b.y) / result.height * 100}%`,
    width: `${Math.abs(rect.b.x - rect.a.x) / result.width * 100}%`, height: `${Math.abs(rect.b.y - rect.a.y) / result.height * 100}%` } : null
  const tools: [Tool, string, string][] = [['brush', 'Brush', 'brush'], ['erase', 'Eraser', 'eraser'], ['rect', 'Rectangle', 'rect']]
  return <dialog ref={ref} className="image-dialog edit-dialog" aria-labelledby="edit-title" onClose={onClose}>
    <div className="edit-body">
      <div className="edit-head"><h2 id="edit-title">Edit result {result.version}</h2>
        <p className="hint">Mark the area to change. Only that area is pasted back onto this result; every pixel outside it stays exactly as it is. The edit becomes a new result; result {result.version} is kept.</p></div>
      <div className="edit-layout">
        <div className="edit-stage-wrap">
          <div className="edit-toolbar" role="toolbar" aria-label="Marking tools">
            <div className="segmented" role="radiogroup" aria-label="Tool">{tools.map(([id, label, glyph]) => <label key={id} className={`segment ${tool === id ? 'selected' : ''}`}>
              <input type="radio" name="edit-tool" checked={tool === id} onChange={() => setTool(id)} /><Glyph name={glyph as 'brush'} />{label}</label>)}</div>
            {tool !== 'rect' && <label className="brush-size"><span>Size</span><input type="range" min={4} max={Math.round(Math.min(result.width, result.height) / 4)} value={brush} onChange={e => setBrush(Number(e.target.value))} aria-label="Brush size" /></label>}
            <span className="spacer" />
            <button type="button" className="secondary compact" disabled={!undo.length || busy} onClick={stepBack}><Glyph name="undo" />Undo</button>
            <button type="button" className="secondary compact" disabled={!marked || busy} onClick={clear}>Clear</button>
          </div>
          <div className="edit-stage" style={{ aspectRatio: `${result.width} / ${result.height}`, width: `min(100%, calc(62vh * ${(result.width / result.height).toFixed(4)}))` }}>
            <img src={result.image_url} alt={`Result ${result.version}`} draggable={false} />
            <canvas ref={canvas} width={result.width} height={result.height} className={`edit-mask tool-${tool}`} aria-label="Marked area: draw on the image to mark what to change"
              onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} />
            {overlay && <span className="edit-rect" style={overlay} aria-hidden="true" />}
          </div>
          {result.mappings.some(m => m.box) && <div className="edit-subjects"><span className="field-label">Use a person’s area</span>
            {result.mappings.filter(m => m.box).map(m => <button key={m.subject} type="button" className="secondary compact" disabled={busy} onClick={() => markSubject(m.subject)}>{m.subject}</button>)}</div>}
        </div>
        <div className="edit-form">
          <span className="field-label" id="edit-kind-label">What to do</span>
          <div className="segmented" role="radiogroup" aria-labelledby="edit-kind-label">
            <label className={`segment ${kind === 'fix' ? 'selected' : ''}`}><input type="radio" name="edit-kind" checked={kind === 'fix'} onChange={() => chooseKind('fix')} />Fix an area</label>
            <label className={`segment ${kind === 'replace' ? 'selected' : ''} ${replaceable.length ? '' : 'disabled'}`}><input type="radio" name="edit-kind" disabled={!replaceable.length} checked={kind === 'replace'} onChange={() => chooseKind('replace')} />Replace a person</label>
          </div>
          {kind === 'replace' ? <>
            <div className="label-row"><label htmlFor="edit-subject">Person</label><InfoTip label="Person">Only people who were replaced with approved photos can be replaced again. Their approved photos are sent; to use someone else, duplicate the scene and approve it.</InfoTip></div>
            <select id="edit-subject" value={subject} disabled={busy} onChange={e => { setSubject(e.target.value); if (!marked) markSubject(e.target.value) }}>
              {replaceable.map(m => <option key={m.subject} value={m.subject}>{m.subject}{m.character_name ? ` · ${m.character_name}` : ''} ({m.images.length} {m.images.length === 1 ? 'photo' : 'photos'})</option>)}</select>
            <label htmlFor="edit-instruction">Anything else <span className="hint">(optional)</span></label>
          </> : <label htmlFor="edit-instruction">Change the marked area to…</label>}
          <textarea id="edit-instruction" rows={3} maxLength={1000} value={instruction} disabled={busy}
            placeholder={kind === 'replace' ? 'For example: keep the smile from the original' : 'For example: remove the sign on the wall'} onChange={e => setInstruction(e.target.value)} />
          <span className="field-label" id="edit-engine-label">Engine</span>
          <div className="edit-engines" role="radiogroup" aria-labelledby="edit-engine-label">{usable.map(o => <label key={o.id} className={`engine-card compact ${optionId === o.id ? 'selected' : ''} ${o.available ? '' : 'unavailable'}`}>
            <input type="radio" name="edit-engine" checked={optionId === o.id} disabled={!o.available || busy} onChange={() => setOptionId(o.id)} />
            <span className="engine-card-body"><span className="engine-card-top"><strong>{o.name}</strong><span className={`engine-tag ${o.charged ? 'api' : ''}`}>{o.charged ? 'API key' : 'Subscription'}</span></span>
              <span className="engine-card-line">{o.available ? `${o.charged ? 'Charged per edit' : 'Your ChatGPT plan'} · ${areaNotes[o.area]}` : o.reason}</span></span>
          </label>)}</div>
          {option && <p className="hint">{option.name} {areaNotes[option.area]}. Sends {sends} to {option.company}{option.charged ? '' : ' via Codex'}. The studio then pastes back only the marked area.</p>}
          {error && <p className="frame-error" role="alert">{error}</p>}
        </div>
      </div>
      <div className="dialog-actions">
        <span className="spacer" role="status">{!marked ? 'Mark the area to change' : kind === 'fix' && instruction.trim().length < 3 ? 'Describe the change' : option && !option.available ? option.reason : ''}</span>
        <button type="button" className="secondary" onClick={onClose}>Cancel</button>
        <button type="button" disabled={!ready || busy} onClick={start}><Glyph name="edit" />{busy ? 'Starting…' : 'Edit result'}</button>
      </div>
    </div>
    {asking && option && api.byId[option.engine] && <ChargeDialog engine={api.byId[option.engine]} model={option.model} runs={1} title={`Edit with ${option.name}?`} action="Edit"
      what={sends} image={option.options.size ? { size: option.options.size, quality: option.options.quality } : undefined}
      costLine={option.engine === 'bfl_api' ? 'Black Forest Labs charges per image in credits and reports the cost; the studio records it after the edit.' : undefined}
      onConfirm={() => void submit(true)} onClose={() => setAsking(false)} />}
  </dialog>
}
