import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { request, send } from './api'

/** Optional API engines (Phase 6A): keys, model lists and the charge confirmation. */
export type ApiEngine = {
  id: string; name: string; company: string; key_help: string; pricing_url: string
  suggested_model: string | null; charge_note: string
  key: { saved: boolean; saved_at: string | null }
  typical_usage: { runs: number; input_tokens: number; output_tokens: number } | null
}

export const apiEngineIds = ['gemini_api', 'anthropic_api', 'openai_api']
export const isApiEngine = (engine: string) => apiEngineIds.includes(engine)
// Short names for every engine, used across scenes, batches and settings.
export const engineNames: Record<string, string> = { claude_cli: 'Claude', codex_cli: 'Codex', manual: 'Manual', gemini_api: 'Gemini API', anthropic_api: 'Anthropic API', openai_api: 'OpenAI API' }
export const sendsTo: Record<string, string> = { claude_cli: 'Anthropic via Claude Code', codex_cli: 'OpenAI via Codex', gemini_api: 'Google with your API key', anthropic_api: 'Anthropic with your API key', openai_api: 'OpenAI with your API key' }

export function useApiEngines() {
  const [engines, setEngines] = useState<ApiEngine[]>([])
  const load = useCallback(() => request<ApiEngine[]>('/api/api-engines').then(setEngines, () => undefined), [])
  useEffect(() => { void load() }, [load])
  return { engines, byId: Object.fromEntries(engines.map(e => [e.id, e])) as Record<string, ApiEngine>, reload: load }
}

const thousands = (n: number) => n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)

/** What a confirmed API run sends, to whom, and what it may cost. */
export function ChargeSummary({ engine, model, runs, what = 'the Base Image (without location data) and the analysis instruction' }: { engine: ApiEngine; model: string | null; runs: number; what?: string }) {
  const typical = engine.typical_usage
  return <div className="check-box warning charge-box">
    <strong>{runs === 1 ? 'This run may be charged' : `These ${runs} runs may be charged`} to your {engine.company} account</strong>
    <ul>
      <li>Sends {what} to {engine.company}{model ? `, model ${model}` : ''}, once per run. Character names are never sent.</li>
      <li>{typical ? `Earlier runs here used about ${thousands(typical.input_tokens)} input and ${thousands(typical.output_tokens)} output tokens each (${typical.runs} ${typical.runs === 1 ? 'run' : 'runs'}).` : 'A typical analysis is a few thousand tokens in and out; the studio records the real figures after each run.'}{' '}
        <a href={engine.pricing_url} target="_blank" rel="noreferrer">{engine.company} prices</a></li>
      <li>{engine.charge_note}</li>
      <li>Nothing is retried on its own. A cancelled request may still be charged if {engine.company} already received it.</li>
    </ul>
  </div>
}

/** Ask before an API run. Resolves only on the user's explicit choice. */
export function ChargeDialog({ engine, model, runs, note, onConfirm, onClose }: { engine: ApiEngine; model: string | null; runs: number; note?: string; onConfirm: () => void; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => { ref.current?.showModal() }, [])
  return <dialog ref={ref} className="image-dialog text-dialog charge-dialog" aria-labelledby="charge-title" onClose={onClose}>
    <div className="text-dialog-form">
      <h2 id="charge-title">Analyse with the {engine.name}?</h2>
      {note && <p className="hint">{note}</p>}
      <ChargeSummary engine={engine} model={model} runs={runs} />
      <div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Cancel</button>
        <button type="button" autoFocus onClick={() => { onConfirm(); onClose() }}>Analyse and accept charges</button></div>
    </div>
  </dialog>
}

function KeyRow({ engine, token, selected, onChanged, onModels }: { engine: ApiEngine; token: string; selected: boolean; onChanged: () => void; onModels: (models: string[]) => void }) {
  const [key, setKey] = useState('')
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  async function act(label: string, work: () => Promise<void>) {
    setBusy(label); setError(''); setMessage('')
    try { await work() } catch (e) { setError(e instanceof Error ? e.message : 'That did not work. Try again.') } finally { setBusy('') }
  }
  const save = (e: FormEvent) => {
    e.preventDefault()
    void act('save', async () => { await send(`/api/api-engines/${engine.id}/key`, 'PUT', token, { key }); setKey(''); setEditing(false); setMessage('Key saved, protected for your Windows account.'); onChanged() })
  }
  const test = () => void act('test', async () => {
    const result = await send<{ models: string[] }>(`/api/api-engines/${engine.id}/models`, 'POST', token)
    onModels(result.models)
    setMessage(result.models.length ? `Key works. ${result.models.length} models available; choose one above.` : 'Key works, but no suitable models were listed.')
  })
  const remove = () => {
    if (!window.confirm(`Remove the saved ${engine.name} key from this computer? The key stays valid at ${engine.company}; revoke it there if you no longer need it.`)) return
    void act('remove', async () => { await send(`/api/api-engines/${engine.id}/key`, 'DELETE', token); setMessage('Key removed.'); onChanged() })
  }
  const showForm = editing || !engine.key.saved
  return <li className="api-key-row">
    <div className="api-key-head">
      <span className={`status-dot ${engine.key.saved ? 'ready' : ''}`} aria-hidden="true" />
      <div><strong>{engine.name}</strong><span className="engine-state">{engine.key.saved ? 'Key saved' : 'No key'}</span>
        <p className="hint">{engine.key_help}</p></div>
      {engine.key.saved && !editing && <div className="api-key-actions">
        <button type="button" className="secondary compact" disabled={!!busy} onClick={test}>{busy === 'test' ? 'Testing…' : 'Test key'}</button>
        <button type="button" className="secondary compact" disabled={!!busy} onClick={() => setEditing(true)}>Replace</button>
        <button type="button" className="danger secondary compact" disabled={!!busy || selected} title={selected ? 'Choose another analysis engine first' : undefined} onClick={remove}>Remove</button>
      </div>}
    </div>
    {showForm && <form className="api-key-form" onSubmit={save}>
      <label htmlFor={`key-${engine.id}`} className="visually-hidden">{engine.name} key</label>
      <input id={`key-${engine.id}`} type="password" autoComplete="off" spellCheck={false} placeholder={`Paste your ${engine.company} API key`} value={key} disabled={!!busy} onChange={e => setKey(e.target.value)} />
      {editing && <button type="button" className="secondary" onClick={() => { setEditing(false); setKey('') }}>Cancel</button>}
      <button disabled={!!busy || !key.trim()}>{busy === 'save' ? 'Saving…' : 'Save key'}</button>
    </form>}
    {message && <p className="hint" role="status">{message}</p>}
    {error && <p className="frame-error" role="alert">{error}</p>}
  </li>
}

/** Keys are write-only: saved, replaced or removed here, never shown again. */
export function ApiKeysPanel({ engines, token, selectedEngine, onChanged, onModels }: { engines: ApiEngine[]; token: string; selectedEngine: string; onChanged: () => void; onModels: (engine: string, models: string[]) => void }) {
  return <section className="panel provider-panel api-keys-panel" aria-labelledby="api-keys-title">
    <div className="panel-head"><div><span className="tiny-label">OPTIONAL · YOUR KEYS, YOUR BILLING</span><h2 id="api-keys-title">API keys</h2></div></div>
    <p>API engines call Google, Anthropic or OpenAI directly with your own key. They are billed by that company, separately from your Claude and ChatGPT plans, and every run asks you first. Keys are stored only on this computer, protected for your Windows account, never shown again, never included in backups and only sent to their own company.</p>
    <ul className="api-key-list">{engines.map(e => <KeyRow key={e.id} engine={e} token={token} selected={selectedEngine === e.id} onChanged={onChanged} onModels={models => onModels(e.id, models)} />)}</ul>
  </section>
}
