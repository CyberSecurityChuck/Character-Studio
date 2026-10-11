import { useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent } from 'react'

/** Advanced comparison (Phase 6B): side by side, slider, overlay and difference, with
 *  zoom and pan shared by every pane and optional subject boxes from the analysis. */
export type CompareImage = { id: string; label: string; url: string; width: number; height: number }
export type CompareBox = { label: string; bounding_box: { x: number; y: number; width: number; height: number } }
export type CompareMode = 'single' | 'side' | 'slider' | 'overlay' | 'difference'

const modeLabels: Record<CompareMode, string> = { single: 'Result', side: 'Side by side', slider: 'Slider', overlay: 'Overlay', difference: 'Difference' }
const zooms = [1, 1.5, 2, 3, 4]
const clamp = (value: number, limit: number) => Math.max(-limit, Math.min(limit, value))

/** Fill the frame when the shapes nearly match (so boxes and overlays line up); else fit. */
function fit(image: CompareImage, frame: { width: number; height: number }) {
  const ratio = image.width / image.height, target = frame.width / frame.height
  return Math.abs(ratio - target) / target < 0.05 ? 'fill' : 'contain'
}

function Layer({ image, frame, style, className = '' }: { image: CompareImage; frame: { width: number; height: number }; style?: CSSProperties; className?: string }) {
  return <img className={`cmp-layer ${className}`} src={image.url} alt={image.label} draggable={false} style={{ objectFit: fit(image, frame), ...style }} />
}

function Boxes({ boxes }: { boxes: CompareBox[] }) {
  return <svg className="cmp-boxes" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
    {boxes.map(b => {
      const box = { x: b.bounding_box.x * 100, y: b.bounding_box.y * 100, width: b.bounding_box.width * 100, height: b.bounding_box.height * 100 }
      // A dark outline under a white dashed one stays visible on light and dark images.
      return <g key={b.label}><rect className="under" {...box} vectorEffect="non-scaling-stroke" /><rect className="over" {...box} vectorEffect="non-scaling-stroke" /></g>
    })}
  </svg>
}

function BoxLabels({ boxes }: { boxes: CompareBox[] }) {
  return <>{boxes.map(b => <span key={b.label} className="cmp-box-label" style={{ left: `${b.bounding_box.x * 100}%`, top: `${b.bounding_box.y * 100}%` }}>{b.label.replace('Subject ', 'S')}</span>)}</>
}

export function Comparison({ images, frame, boxes, modes, initialMode, initialA, initialB, sideIds }: {
  images: CompareImage[]; frame: { width: number; height: number }; boxes: CompareBox[]
  modes: CompareMode[]; initialMode: CompareMode; initialA: string; initialB: string
  /** Side by side shows these images (several results); otherwise the two chosen ones. */
  sideIds?: string[]
}) {
  const [mode, setMode] = useState<CompareMode>(initialMode)
  const [aId, setA] = useState(initialA)
  const [bId, setB] = useState(initialB)
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [showBoxes, setShowBoxes] = useState(false)
  const [position, setPosition] = useState(50)
  const [opacity, setOpacity] = useState(50)
  const drag = useRef<{ x: number; y: number; pan: { x: number; y: number }; width: number; height: number } | null>(null)
  const byId = Object.fromEntries(images.map(i => [i.id, i]))
  const a = byId[aId] ?? images[0], b = byId[bId] ?? images[0]
  const limit = (zoom - 1) * 50
  const setZoomTo = (value: number) => { setZoom(value); const l = (value - 1) * 50; setPan(p => ({ x: clamp(p.x, l), y: clamp(p.y, l) })) }
  const step = (direction: 1 | -1) => setZoomTo(zooms[Math.max(0, Math.min(zooms.length - 1, zooms.indexOf(zoom) + direction))])
  const move: CSSProperties = { transform: `translate(${pan.x}%, ${pan.y}%) scale(${zoom})` }
  const frameStyle = { aspectRatio: `${frame.width} / ${frame.height}`, '--ratio': String(frame.width / frame.height) } as CSSProperties

  function down(e: PointerEvent<HTMLDivElement>) {
    if (zoom === 1) return
    const rect = e.currentTarget.getBoundingClientRect()
    drag.current = { x: e.clientX, y: e.clientY, pan, width: rect.width, height: rect.height }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  function moveTo(e: PointerEvent<HTMLDivElement>) {
    const d = drag.current
    if (!d) return
    // Translate percentages are of the unscaled pane, so a pixel moves 100/size percent.
    setPan({ x: clamp(d.pan.x + ((e.clientX - d.x) / d.width) * 100, limit), y: clamp(d.pan.y + ((e.clientY - d.y) / d.height) * 100, limit) })
  }
  function key(e: KeyboardEvent<HTMLDivElement>) {
    const moves: Record<string, [number, number]> = { ArrowLeft: [5, 0], ArrowRight: [-5, 0], ArrowUp: [0, 5], ArrowDown: [0, -5] }
    if (e.key === '+' || e.key === '=') { e.preventDefault(); step(1) }
    else if (e.key === '-') { e.preventDefault(); step(-1) }
    else if (e.key === '0') { e.preventDefault(); setZoomTo(1) }
    else if (moves[e.key] && zoom > 1) { e.preventDefault(); setPan(p => ({ x: clamp(p.x + moves[e.key][0], limit), y: clamp(p.y + moves[e.key][1], limit) })) }
  }
  const stageProps = { onPointerDown: down, onPointerMove: moveTo, onPointerUp: () => { drag.current = null }, onPointerCancel: () => { drag.current = null } }
  const pane = (image: CompareImage, caption?: string) => <figure key={image.id} className="cmp-figure">
    <div className={`cmp-frame ${zoom > 1 ? 'zoomed' : ''}`} style={frameStyle} {...stageProps}>
      <div className="cmp-move" style={move}><Layer image={image} frame={frame} />{showBoxes && <><Boxes boxes={boxes} /><BoxLabels boxes={boxes} /></>}</div>
    </div>
    {caption !== undefined && <figcaption>{caption}</figcaption>}
  </figure>
  const sideImages = sideIds ? sideIds.map(id => byId[id]).filter(Boolean) : [b, a]
  const paired = mode === 'slider' || mode === 'overlay' || mode === 'difference'

  return <div className="comparison">
    <div className="cmp-toolbar">
      <div className="segmented" role="radiogroup" aria-label="How to compare">
        {modes.map(m => <label key={m} className={`segment ${mode === m ? 'selected' : ''}`}><input type="radio" name="compare-mode" checked={mode === m} onChange={() => setMode(m)} />{modeLabels[m]}</label>)}
      </div>
      <div className="cmp-tools">
        {/* Several results (sideIds): "Compare [A] with [B]"; one result: "Compare with [B]". */}
        {paired && sideIds && <label className="cmp-pick">Compare
          <select value={aId} onChange={e => setA(e.target.value)}>{images.filter(i => i.id !== bId).map(i => <option key={i.id} value={i.id}>{i.label}</option>)}</select></label>}
        {(paired || (mode === 'side' && !sideIds)) && images.length > 2 && <label className="cmp-pick">{paired && sideIds ? 'with' : 'Compare with'}
          <select value={bId} onChange={e => setB(e.target.value)}>{images.filter(i => i.id !== aId).map(i => <option key={i.id} value={i.id}>{i.label}</option>)}</select></label>}
        <div className="cmp-zoom" role="group" aria-label="Zoom">
          <button type="button" className="secondary compact icon-only" aria-label="Zoom out" disabled={zoom === 1} onClick={() => step(-1)}>−</button>
          <button type="button" className="link-button cmp-zoom-value" title="Back to fit" onClick={() => setZoomTo(1)}>{zoom === 1 ? 'Fit' : `${zoom}×`}</button>
          <button type="button" className="secondary compact icon-only" aria-label="Zoom in" disabled={zoom === zooms[zooms.length - 1]} onClick={() => step(1)}>+</button>
        </div>
        {boxes.length > 0 && <label className="checkbox-label cmp-boxes-toggle"><input type="checkbox" checked={showBoxes} onChange={e => setShowBoxes(e.target.checked)} /> Subject boxes</label>}
      </div>
    </div>

    <div className="cmp-stage" tabIndex={0} aria-label="Comparison. Plus and minus zoom, arrow keys move, 0 fits." onKeyDown={key}>
      {mode === 'single' && <div className="cmp-single">{pane(a)}</div>}
      {mode === 'side' && <div className={`cmp-side count-${Math.min(sideImages.length, 4)}`}>{sideImages.map(i => pane(i, i.label))}</div>}
      {paired && <div className="cmp-single">
        <div className={`cmp-frame stacked ${zoom > 1 ? 'zoomed' : ''}`} style={frameStyle} {...stageProps}>
          <div className="cmp-move" style={move}><Layer image={b} frame={frame} /></div>
          {/* Clip and blend outside the moving layer, so the slider line stays put when zoomed
              and the difference blends with the image below (a transform isolates blending). */}
          <div className="cmp-clip" style={mode === 'slider' ? { clipPath: `inset(0 0 0 ${position}%)` } : mode === 'difference' ? { mixBlendMode: 'difference' } : undefined}>
            <div className="cmp-move" style={move}>
              <Layer image={a} frame={frame} style={mode === 'overlay' ? { opacity: opacity / 100 } : undefined} />
            </div>
          </div>
          {showBoxes && <div className="cmp-move" style={move}><Boxes boxes={boxes} /><BoxLabels boxes={boxes} /></div>}
          {mode === 'slider' && <span className="compare-line" style={{ left: `${position}%` }} aria-hidden="true" />}
          <span className="compare-tag left">{b.label}</span><span className="compare-tag right">{a.label}</span>
        </div>
        {mode === 'slider' && <><label className="visually-hidden" htmlFor="compare-position">Slider position</label>
          <input id="compare-position" type="range" min={0} max={100} value={position} onChange={e => setPosition(Number(e.target.value))} /></>}
        {mode === 'overlay' && <><label className="visually-hidden" htmlFor="compare-opacity">{a.label} opacity</label>
          <input id="compare-opacity" type="range" min={0} max={100} value={opacity} onChange={e => setOpacity(Number(e.target.value))} /></>}
      </div>}
    </div>
    <p className="hint cmp-hint">{mode === 'slider' ? `Drag the slider to reveal more of ${b.label} (left) or ${a.label} (right).`
      : mode === 'overlay' ? `${a.label} is laid over ${b.label}; the slider sets how see-through it is.`
      : mode === 'difference' ? 'Areas that match turn dark; bright areas differ. Small shifts in position show as bright outlines.'
      : mode === 'side' ? 'Zoom and pan apply to every image at once.' : ''}
      {zoom > 1 ? ' Drag an image to move around.' : ''}{showBoxes ? ' Boxes come from the Base Image analysis.' : ''}
      {images.some(i => fit(i, frame) === 'contain') ? ' An image with a different shape is fitted inside the Base Image frame.' : ''}</p>
  </div>
}
