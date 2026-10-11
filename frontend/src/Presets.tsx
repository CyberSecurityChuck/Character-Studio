import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError, request, send } from './api'
import { Glyph, InfoTip } from './Controls'

/** Saved generation presets (Phase 6B): scene changes and negative additions for the prompt,
 *  and how many images one click makes. Applying one only fills fields; you still save and
 *  approve the prompt yourself. */
export type Preset = { id: string; name: string; scene_changes: string; negative_additions: string; images: number; revision: number; created_at: string; updated_at: string }

export function usePresets() {
  const [presets, setPresets] = useState<Preset[]>([])
  const load = useCallback(() => request<Preset[]>('/api/presets').then(setPresets, () => undefined), [])
  useEffect(() => { void load() }, [load])
  return { presets, reload: load }
}

/** Add lines that are not there yet (case-insensitive), keeping the existing text as it is. */
export function appendLines(text: string, additions: string) {
  const have = new Set(text.split(/\r?\n/).map(l => l.trim().toLocaleLowerCase()).filter(Boolean))
  const extra = additions.split(/\r?\n/).map(l => l.trim()).filter(l => l && !have.has(l.toLocaleLowerCase()))
  if (!extra.length) return text
  return `${text.replace(/\s+$/, '')}${text.trim() ? '\n' : ''}${extra.join('\n')}`
}

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`

export function PresetDialog({ preset, initial, token, onClose, onSaved }: {
  preset?: Preset; initial?: Partial<Preset>; token: string; onClose: () => void; onSaved: (preset: Preset | null, message: string) => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const [form, setForm] = useState({ name: preset?.name ?? initial?.name ?? '', scene_changes: preset?.scene_changes ?? initial?.scene_changes ?? '', negative_additions: preset?.negative_additions ?? initial?.negative_additions ?? '', images: preset?.images ?? initial?.images ?? 1 })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { ref.current?.showModal() }, [])
  async function save(e: FormEvent) {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      const saved = preset
        ? await send<Preset>(`/api/presets/${preset.id}`, 'PUT', token, { ...form, revision: preset.revision })
        : await send<Preset>('/api/presets', 'POST', token, form)
      onSaved(saved, preset ? `Preset “${saved.name}” saved.` : `Preset “${saved.name}” created.`); onClose()
    } catch (err) { setError(err instanceof Error ? err.message : 'The preset could not be saved.'); setBusy(false) }
  }
  async function remove() {
    if (!preset || !window.confirm(`Delete the preset “${preset.name}”? Prompts and results made with it are not changed.`)) return
    setBusy(true); setError('')
    try { await send(`/api/presets/${preset.id}`, 'DELETE', token); onSaved(null, `Preset “${preset.name}” deleted.`); onClose() }
    catch (err) { setError(err instanceof Error ? err.message : 'The preset could not be deleted.'); setBusy(false) }
  }
  return <dialog ref={ref} className="image-dialog text-dialog preset-dialog" aria-labelledby="preset-title" onClose={onClose}>
    <form className="text-dialog-form" onSubmit={e => void save(e)}><fieldset disabled={busy}>
      <h2 id="preset-title">{preset ? 'Edit preset' : 'New preset'}</h2>
      <label htmlFor="preset-name">Name</label>
      <input id="preset-name" autoFocus required maxLength={60} value={form.name} placeholder="For example: Golden hour" onChange={e => setForm({ ...form, name: e.target.value })} />
      <div className="label-row"><label htmlFor="preset-changes">Scene changes</label><InfoTip label="Scene changes">Put into the prompt step’s Scene changes field; the prompt draft is rebuilt with them. Leave empty to keep the scene as it is.</InfoTip></div>
      <textarea id="preset-changes" rows={3} maxLength={4000} value={form.scene_changes} placeholder="For example: warm golden-hour light, soft shadows" onChange={e => setForm({ ...form, scene_changes: e.target.value })} />
      <div className="label-row"><label htmlFor="preset-negative">Add to the negative prompt</label><InfoTip label="Negative additions">One item per line. Lines that are already in the negative prompt are not added twice.</InfoTip></div>
      <textarea id="preset-negative" rows={3} maxLength={2000} value={form.negative_additions} placeholder={'For example: harsh flash\nlens flare'} onChange={e => setForm({ ...form, negative_additions: e.target.value })} />
      <div className="label-row"><label htmlFor="preset-images">Images per click</label><InfoTip label="Images per click">Sets the − / + count on the Generate step (and in batches, up to 5 per scene) when you choose this preset. Each image is one run.</InfoTip></div>
      <input id="preset-images" type="number" min={1} max={10} required value={form.images} onChange={e => setForm({ ...form, images: Number(e.target.value) })} />
      {error && <p className="frame-error" role="alert">{error}</p>}
      <div className="dialog-actions">
        {preset && <button type="button" className="danger secondary" onClick={() => void remove()}>Delete</button>}
        <span className="spacer" />
        <button type="button" className="secondary" onClick={onClose}>Cancel</button>
        <button disabled={!form.name.trim()}>{busy ? 'Saving…' : preset ? 'Save preset' : 'Create preset'}</button>
      </div>
    </fieldset></form>
  </dialog>
}

/** Studio settings: the list of presets. */
export function PresetsPanel({ token }: { token: string }) {
  const { presets, reload } = usePresets()
  const [editing, setEditing] = useState<Preset | 'new' | null>(null)
  const [message, setMessage] = useState('')
  return <section className="panel provider-panel presets-panel" aria-labelledby="presets-title">
    <div className="panel-head"><div><span className="tiny-label">REUSE WHAT WORKS</span><h2 id="presets-title">Generation presets</h2></div>
      <button type="button" onClick={() => setEditing('new')}>+ New preset</button></div>
    <p>A preset fills the Scene changes and negative prompt on a scene’s Prompt step and sets how many images one click makes. You still save and approve each prompt; nothing is sent when you apply a preset.</p>
    {presets.length ? <ul className="preset-list">{presets.map(p => <li key={p.id}>
      <div><strong>{p.name}</strong><p className="hint">{[p.scene_changes.trim() && `Changes: ${p.scene_changes.trim().replace(/\s+/g, ' ').slice(0, 90)}`, p.negative_additions.trim() && `Avoid: ${p.negative_additions.trim().split(/\r?\n/).join(', ').slice(0, 60)}`, plural(p.images, 'image')].filter(Boolean).join(' · ')}</p></div>
      <button type="button" className="secondary compact" onClick={() => setEditing(p)}><Glyph name="edit" />Edit</button>
    </li>)}</ul> : <p className="hint">No presets yet. Create one here, or use “Save as preset” on a scene’s Prompt step.</p>}
    <p className="library-status" role="status">{message}</p>
    {editing && <PresetDialog preset={editing === 'new' ? undefined : editing} token={token} onClose={() => setEditing(null)} onSaved={(_p, note) => { setMessage(note); void reload() }} />}
  </section>
}

export function PresetSelect({ id, presets, value, onChange, disabled, label = 'Preset' }: { id: string; presets: Preset[]; value: string; onChange: (preset: Preset | null) => void; disabled?: boolean; label?: string }) {
  if (!presets.length) return null
  return <div className="preset-select"><label htmlFor={id}>{label}</label>
    <select id={id} value={value} disabled={disabled} onChange={e => onChange(presets.find(p => p.id === e.target.value) ?? null)}>
      <option value="">None</option>{presets.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
    </select></div>
}

export const isConflict = (error: unknown) => error instanceof ApiError && error.status === 409
