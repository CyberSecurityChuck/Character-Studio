import { useCallback, useEffect, useRef, useState } from 'react'
import { request, send } from './api'

/** Optional API engines (Phase 6A): keys, model lists and the charge confirmation. */
export type ApiEngine = {
  id: string; name: string; company: string; key_help: string; pricing_url: string
  suggested_model: string | null; charge_note: string
  key: { saved: boolean; saved_at: string | null }
  typical_usage: Usage | null
  models: string[]; models_checked_at: string | null; models_error: string | null
  // Phase 6C: engines whose key can also make images, with their own models and figures.
  makes_images: boolean; image_name: string | null; suggested_image_model: string | null
  image_charge_note: string | null; typical_image_usage: Usage | null; image_models: string[]
}
type Usage = { runs: number; input_tokens: number; output_tokens: number }

export const apiEngineIds = ['gemini_api', 'anthropic_api', 'openai_api']
export const isApiEngine = (engine: string) => apiEngineIds.includes(engine)
// Short names for every engine, used across scenes, batches and settings.
export const engineNames: Record<string, string> = { claude_cli: 'Claude', codex_cli: 'Codex', manual: 'Manual', gemini_api: 'Gemini API', anthropic_api: 'Anthropic API', openai_api: 'OpenAI API' }
export const sendsTo: Record<string, string> = { claude_cli: 'Anthropic via Claude Code', codex_cli: 'OpenAI via Codex', gemini_api: 'Google with your API key', anthropic_api: 'Anthropic with your API key', openai_api: 'OpenAI with your API key' }
// Generation engines (Phase 6C): the same keys, shown under their image names.
export const imageEngineIds = ['gemini_api', 'openai_api']
export const isImageEngine = (engine: string) => imageEngineIds.includes(engine)
export const generationNames: Record<string, string> = { codex_cli: 'Codex', manual: 'Manual', gemini_api: 'Gemini image', openai_api: 'OpenAI Images' }

export function useApiEngines() {
  const [engines, setEngines] = useState<ApiEngine[]>([])
  const load = useCallback(() => request<ApiEngine[]>('/api/api-engines').then(setEngines, () => undefined), [])
  useEffect(() => { void load() }, [load])
  return { engines, byId: Object.fromEntries(engines.map(e => [e.id, e])) as Record<string, ApiEngine>, reload: load }
}

const thousands = (n: number) => n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)

/** What a confirmed API run sends, to whom, and what it may cost.
 *  `image` describes an image run (Phase 6C): its own note, figures and settings. */
export function ChargeSummary({ engine, model, runs, what, image }: { engine: ApiEngine; model: string | null; runs: number; what?: string; image?: { size: string; quality?: string } }) {
  // Earlier figures come from analyses or image runs; a quality check (`what` given, no image) sends several images.
  const typical = image ? engine.typical_image_usage : what ? null : engine.typical_usage
  const settings = image ? `, ${image.size}${image.quality ? `, ${image.quality} quality` : ''}` : ''
  return <div className="check-box warning charge-box">
    <strong>{runs === 1 ? 'This run may be charged' : `These ${runs} runs may be charged`} to your {engine.company} account</strong>
    <ul>
      <li>Sends {what ?? 'the Base Image (without location data) and the analysis instruction'} to {engine.company}{model ? `, model ${model}` : ''}{settings}, once per run. Character names are never sent.</li>
      <li>{typical ? `Earlier runs here used about ${thousands(typical.input_tokens)} input and ${thousands(typical.output_tokens)} output tokens each (${typical.runs} ${typical.runs === 1 ? 'run' : 'runs'}).`
        : image ? `${engine.company} charges per image; larger sizes${image.quality ? ' and higher quality' : ''} cost more. The studio records the reported figures after each run.`
        : what ? 'Several images use more input tokens than one analysis; the studio records the real figures after the run.'
        : 'A typical analysis is a few thousand tokens in and out; the studio records the real figures after each run.'}{' '}
        <a href={engine.pricing_url} target="_blank" rel="noreferrer">{engine.company} prices</a></li>
      <li>{image ? engine.image_charge_note : engine.charge_note}</li>
      <li>Nothing is retried on its own. A cancelled request may still be charged if {engine.company} already received it.</li>
    </ul>
  </div>
}

/** Ask before an API run. Resolves only on the user's explicit choice. */
export function ChargeDialog({ engine, model, runs, note, title, action = 'Analyse', what, image, onConfirm, onClose }: { engine: ApiEngine; model: string | null; runs: number; note?: string; title?: string; action?: string; what?: string; image?: { size: string; quality?: string }; onConfirm: () => void; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => { ref.current?.showModal() }, [])
  return <dialog ref={ref} className="image-dialog text-dialog charge-dialog" aria-labelledby="charge-title" onClose={onClose}>
    <div className="text-dialog-form">
      <h2 id="charge-title">{title ?? `Analyse with the ${engine.name}?`}</h2>
      {note && <p className="hint">{note}</p>}
      <ChargeSummary engine={engine} model={model} runs={runs} what={what} image={image} />
      <div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Cancel</button>
        <button type="button" autoFocus onClick={() => { onConfirm(); onClose() }}>{action} and accept charges</button></div>
    </div>
  </dialog>
}

/** The selected API engine's key: saved, replaced, tested or removed here, never shown again.
 *  Saving a key also fetches its model list once; the list is kept for later visits. */
export function ApiKeyBox({ engine, token, selected, onChanged }: { engine: ApiEngine; token: string; selected: boolean; onChanged: () => void }) {
  const [key, setKey] = useState('')
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  async function act(label: string, work: () => Promise<void>) {
    setBusy(label); setError(''); setMessage('')
    try { await work() } catch (e) { setError(e instanceof Error ? e.message : 'That did not work. Try again.') } finally { setBusy('') }
  }
  const listed = (item: ApiEngine) => item.models.length ? `${item.models.length} ${item.models.length === 1 ? 'model' : 'models'} available.` : 'No suitable models were listed.'
  const save = () => void act('save', async () => {
    const saved = await send<ApiEngine>(`/api/api-engines/${engine.id}/key`, 'PUT', token, { key })
    setKey(''); setEditing(false); onChanged()
    if (saved.models_error) setError(`Key saved, but checking it failed: ${saved.models_error}`)
    else setMessage(`Key saved and working. ${listed(saved)}`)
  })
  const test = () => void act('test', async () => {
    const result = await send<ApiEngine>(`/api/api-engines/${engine.id}/models`, 'POST', token)
    onChanged(); setMessage(`Key works. ${listed(result)}`)
  })
  const remove = () => {
    if (!window.confirm(`Remove the saved ${engine.name} key from this computer? The key stays valid at ${engine.company}; revoke it there if you no longer need it.`)) return
    void act('remove', async () => { await send(`/api/api-engines/${engine.id}/key`, 'DELETE', token); setMessage('Key removed.'); onChanged() })
  }
  const showForm = editing || !engine.key.saved
  return <div className="api-key-box">
    <div className="api-key-head">
      <span className={`status-dot ${engine.key.saved ? 'ready' : ''}`} aria-hidden="true" />
      <div><strong>API key</strong><span className="engine-state">{engine.key.saved ? 'Saved on this computer' : 'Not added yet'}</span>
        <p className="hint">{engine.key_help}</p></div>
      {engine.key.saved && !editing && <div className="api-key-actions">
        <button type="button" className="secondary compact" disabled={!!busy} onClick={test}>{busy === 'test' ? 'Testing…' : 'Test key'}</button>
        <button type="button" className="secondary compact" disabled={!!busy} onClick={() => setEditing(true)}>Replace</button>
        <button type="button" className="danger secondary compact" disabled={!!busy || selected} title={selected ? 'This key is in use. Choose and save another engine first' : undefined} onClick={remove}>Remove</button>
      </div>}
    </div>
    {showForm && <div className="api-key-form">
      <label htmlFor={`key-${engine.id}`} className="visually-hidden">{engine.name} key</label>
      <input id={`key-${engine.id}`} type="password" autoComplete="off" spellCheck={false} placeholder={`Paste your ${engine.company} API key`} value={key} disabled={!!busy}
        onChange={e => setKey(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && key.trim()) { e.preventDefault(); save() } }} />
      {editing && <button type="button" className="secondary" onClick={() => { setEditing(false); setKey('') }}>Cancel</button>}
      <button type="button" disabled={!!busy || !key.trim()} onClick={save}>{busy === 'save' ? 'Saving…' : 'Save key'}</button>
    </div>}
    {message && <p className="hint" role="status">{message}</p>}
    {error && <p className="frame-error" role="alert">{error}</p>}
    <p className="hint">Billed by {engine.company}, separately from your plans; every run asks you first. The key stays on this computer, protected for your Windows account, is never shown again or included in backups, and is only sent to {engine.company}.</p>
  </div>
}
