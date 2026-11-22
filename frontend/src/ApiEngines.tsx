import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { request, send } from './api'
import type { AccountPick, RunAccount } from './Accounts'
import { InfoTip } from './Controls'
import { notify, StatusNote } from './Toast'

/** Optional API engines (Phase 6A): keys, model lists and the charge confirmation.
 *  Phase 8B (D041, D042): several named keys per provider; each engine panel chooses one. */
export type ApiKey = { id: string; label: string; saved_at: string | null; waiting: number }
export type KeyPurpose = 'analysis' | 'generation'
export type ApiEngine = {
  id: string; name: string; company: string; key_help: string; pricing_url: string
  suggested_model: string | null; charge_note: string
  key: { saved: boolean; saved_at: string | null }
  keys: ApiKey[]; active: Partial<Record<KeyPurpose, string | null>>
  typical_usage: Usage | null
  models: string[]; models_checked_at: string | null; models_listed_by: string | null; models_error: string | null
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
export const generationNames: Record<string, string> = { codex_cli: 'Codex', manual: 'Manual', gemini_api: 'Gemini image', openai_api: 'OpenAI Images', bfl_api: 'FLUX' }

// One request shared by every card on the page; refreshed after any key change here.
let cache: { at: number; data: Promise<ApiEngine[]> } | null = null
const listeners = new Set<() => void>()
function load(force = false): Promise<ApiEngine[]> {
  if (!force && cache && Date.now() - cache.at < 30_000) return cache.data
  const data = request<ApiEngine[]>('/api/api-engines')
  cache = { at: Date.now(), data }
  data.catch(() => { cache = null })
  return data
}
export function keysChanged() { cache = null; listeners.forEach(fn => fn()) }

export function useApiEngines() {
  const [engines, setEngines] = useState<ApiEngine[]>([])
  const reload = useCallback((force = true) => load(force).then(setEngines, () => undefined), [])
  useEffect(() => {
    void load().then(setEngines, () => undefined)
    const again = () => { void load().then(setEngines, () => undefined) }
    listeners.add(again)
    return () => { listeners.delete(again) }
  }, [])
  return { engines, byId: Object.fromEntries(engines.map(e => [e.id, e])) as Record<string, ApiEngine>, reload }
}

/** The key a panel's new runs are charged to (its saved choice, else the first key). */
export function chargeKey(engine: ApiEngine | undefined, purpose: KeyPurpose): ApiKey | undefined {
  if (!engine) return undefined
  return engine.keys.find(k => k.id === engine.active[purpose]) ?? engine.keys[0]
}
/** The request fields that accept charges to the named key(s) only (Phase 8B). */
export const chargeFields = (...keys: (ApiKey | RunAccount | null | undefined)[]) =>
  ({ confirm_charges: true, charge_keys: keys.filter((k): k is ApiKey | RunAccount => !!k).map(k => k.id) })
export const keyName = (key: { label: string }) => `“${key.label}”`

const thousands = (n: number) => n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)

/** What a confirmed API run sends, to whom, through which key, and what it may cost.
 *  `image` describes an image run (Phase 6C): its own note, figures and settings. */
export function ChargeSummary({ engine, model, runs, what, image, costLine, purpose }: { engine: ApiEngine; model: string | null; runs: number; what?: string; image?: { size: string; quality?: string }; costLine?: string; purpose?: KeyPurpose }) {
  // Earlier figures come from analyses or image runs; a quality check (`what` given, no image) sends several images.
  const typical = image ? engine.typical_image_usage : what ? null : engine.typical_usage
  const settings = image ? `, ${image.size}${image.quality ? `, ${image.quality} quality` : ''}` : ''
  const key = chargeKey(engine, purpose ?? (image ? 'generation' : 'analysis'))
  return <div className="check-box warning charge-box">
    <strong>{runs === 1 ? 'This run may be charged' : `These ${runs} runs may be charged`} to your {engine.company} account{key ? ` through the key ${keyName(key)}` : ''}</strong>
    <ul>
      {key && engine.keys.length > 1 && <li>The {engine.company} account that owns the key {keyName(key)} is billed. Another key can be chosen in Studio settings.</li>}
      <li>Sends {what ?? 'the Base Image (without location data) and the analysis instruction'} to {engine.company}{model ? `, model ${model}` : ''}{settings}, once per run. Character names are never sent.</li>
      <li>{costLine ? costLine : typical ? `Earlier runs here used about ${thousands(typical.input_tokens)} input and ${thousands(typical.output_tokens)} output tokens each (${typical.runs} ${typical.runs === 1 ? 'run' : 'runs'}).`
        : image ? `${engine.company} charges per image; larger sizes${image.quality ? ' and higher quality' : ''} cost more. The studio records the reported figures after each run.`
        : what ? 'Several images use more input tokens than one analysis; the studio records the real figures after the run.'
        : 'A typical analysis is a few thousand tokens in and out; the studio records the real figures after each run.'}{' '}
        <a href={engine.pricing_url} target="_blank" rel="noreferrer">{engine.company} prices</a></li>
      <li>{image ? engine.image_charge_note : engine.charge_note}</li>
      <li>Nothing is retried on its own. A cancelled request may still be charged if {engine.company} already received it.</li>
    </ul>
  </div>
}

/** Ask before an API run. Resolves only on the user's explicit choice; `onConfirm` gets the
 *  request fields that accept charges to the key the dialog named. */
export function ChargeDialog({ engine, model, runs, note, title, action = 'Analyse', what, image, costLine, purpose, onConfirm, onClose }: { engine: ApiEngine; model: string | null; runs: number; note?: string; title?: string; action?: string; what?: string; image?: { size: string; quality?: string }; costLine?: string; purpose?: KeyPurpose; onConfirm: (charge: ReturnType<typeof chargeFields>) => void; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => { ref.current?.showModal() }, [])
  const key = chargeKey(engine, purpose ?? (image ? 'generation' : 'analysis'))
  return <dialog ref={ref} className="image-dialog text-dialog charge-dialog" aria-labelledby="charge-title" onClose={onClose}>
    <div className="text-dialog-form">
      <h2 id="charge-title">{title ?? `Analyse with the ${engine.name}?`}</h2>
      {note && <p className="hint">{note}</p>}
      <ChargeSummary engine={engine} model={model} runs={runs} what={what} image={image} costLine={costLine} purpose={purpose} />
      <div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Cancel</button>
        <button type="button" autoFocus disabled={!key} onClick={() => { onConfirm(chargeFields(key)); onClose() }}>{action} and accept charges</button></div>
    </div>
  </dialog>
}

const formatDay = (value: string | null) => value ? new Date(value).toLocaleDateString(undefined, { dateStyle: 'medium' }) : ''
const panelHints: Record<KeyPurpose, string> = {
  analysis: 'Analysis and quality checks are charged to the key you choose.',
  generation: 'Images and edits are charged to the key you choose.',
}

/** Inside an engine panel (Phase 8B): the provider's saved keys and which one this panel's
 *  runs are charged to. The choice is part of the panel's form and saves with it (FLUX has
 *  no panel, so its choice is saved at once); adding, testing, replacing, renaming and
 *  removing keys happen at once and are shared by every panel. Keys are never shown again. */
export function KeyPicker({ engine, purpose, chosen, saved, onChoose, token, onChanged, shared }: { engine: ApiEngine; purpose: KeyPurpose; chosen: string | null; saved: string | null; onChoose: (id: string) => void; token: string; onChanged: () => void; shared?: string }) {
  const [name, setName] = useState('')
  const [key, setKey] = useState('')
  const [replacing, setReplacing] = useState('')
  const [replacement, setReplacement] = useState('')
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const radioName = useId()
  const first = !engine.keys.length
  const label = name.trim() || (first ? 'Default' : '')
  async function act(what: string, work: () => Promise<string | void>) {
    setBusy(what); setError(''); setMessage('')
    try { const done = await work(); keysChanged(); onChanged(); if (done) setMessage(done) }
    catch (e) { setError(e instanceof Error ? e.message : 'That did not work. Reload and try again.') }
    finally { setBusy('') }
  }
  const listed = (item: ApiEngine) => item.models.length || item.image_models.length ? `${item.models.length + item.image_models.length} ${item.models.length + item.image_models.length === 1 ? 'model' : 'models'} available.` : 'No suitable models were listed.'
  const add = () => void act('add', async () => {
    const result = await send<ApiEngine & { key_id: string }>(`/api/api-engines/${engine.id}/keys`, 'POST', token, { label, key })
    setName(''); setKey('')
    if (result.models_error) throw new Error(`Key saved, but checking it failed: ${result.models_error}`)
    return `Key ${keyName({ label })} saved and working. ${listed(result)}${first ? '' : engine.id === 'bfl_api' ? ' Choose it above to use it for FLUX edits.' : ' Choose it above and save the panel to use it here.'}`
  })
  const test = (item: ApiKey) => void act(`test-${item.id}`, async () => {
    const result = await send<ApiEngine>(`/api/api-engines/${engine.id}/keys/${item.id}/test`, 'POST', token)
    return `Key ${keyName(item)} works. ${listed(result)}`
  })
  const replace = (item: ApiKey) => void act(`replace-${item.id}`, async () => {
    const result = await send<ApiEngine>(`/api/api-engines/${engine.id}/keys/${item.id}`, 'PUT', token, { key: replacement })
    setReplacing(''); setReplacement('')
    if (result.models_error) throw new Error(`Key replaced, but checking it failed: ${result.models_error}`)
    return `Key ${keyName(item)} replaced and working. Runs waiting on it use the new key.`
  })
  const rename = (item: ApiKey) => {
    const next = window.prompt(`New name for the key ${keyName(item)}`, item.label)
    if (!next || next.trim() === item.label) return
    void act(`rename-${item.id}`, async () => { await send(`/api/api-engines/${engine.id}/keys/${item.id}`, 'PUT', token, { label: next }) })
  }
  const remove = (item: ApiKey) => {
    if (!window.confirm(`Remove the key ${keyName(item)} from this computer? It stays valid at ${engine.company}; revoke it there if you no longer need it. Past runs keep its name.`)) return
    void act(`remove-${item.id}`, async () => { await send(`/api/api-engines/${engine.id}/keys/${item.id}`, 'DELETE', token); notify(`Key ${keyName(item)} removed from this computer.`) })
  }
  return <div className="account-picker key-picker">
    <div className="engine-group-head account-head"><h3>{engine.keys.length > 1 ? 'API keys' : 'API key'}</h3>
      <span className="hint">{engine.keys.length > 1 ? (engine.id === 'bfl_api' ? 'FLUX edits are charged to the key you choose.' : panelHints[purpose]) : engine.key_help}</span>
      <InfoTip label="About several keys">Each key is billed to the {engine.company} account that owns it, so the charge confirmation always names the key. Use several keys to keep work and personal use or clients apart, or when a key stops working. Keys stay on this computer, protected for your Windows account, are never shown again or included in backups, and are only sent to {engine.company}.</InfoTip>
    </div>
    {engine.keys.length > 0 && <ul className="account-list" aria-label={`${engine.name} keys`}>{engine.keys.map(item => {
      const selected = chosen === item.id
      return <li key={item.id} className={`account-row${selected ? ' active' : ''}`}>
        <label className="account-use" title="Use for new runs">
          <input type="radio" name={radioName} checked={selected} disabled={!!busy} onChange={() => onChoose(item.id)} />
          <span className="visually-hidden">Use the key {item.label} for new runs</span>
        </label>
        <div className="account-main">
          <span className="account-name"><strong>{item.label}</strong>
            {saved === item.id && chosen !== saved && <span className="engine-tag neutral">Saved choice</span>}</span>
          <span className="engine-card-state ready"><span className="status-dot" aria-hidden="true" />Saved on this computer{item.saved_at ? ` · ${formatDay(item.saved_at)}` : ''}
            {item.waiting > 0 && <span className="hint"> · {item.waiting} {item.waiting === 1 ? 'run' : 'runs'} waiting or running</span>}</span>
          {replacing === item.id && <div className="api-key-form key-replace">
            <label htmlFor={`replace-${item.id}`} className="visually-hidden">New key for {item.label}</label>
            <input id={`replace-${item.id}`} type="password" autoComplete="off" spellCheck={false} autoFocus placeholder={`Paste the new ${engine.company} key`} value={replacement} disabled={!!busy}
              onChange={e => setReplacement(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && replacement.trim()) { e.preventDefault(); replace(item) } if (e.key === 'Escape') { setReplacing(''); setReplacement('') } }} />
            <button type="button" className="secondary compact" onClick={() => { setReplacing(''); setReplacement('') }}>Cancel</button>
            <button type="button" className="compact" disabled={!!busy || !replacement.trim()} onClick={() => replace(item)}>{busy === `replace-${item.id}` ? 'Saving…' : 'Save key'}</button>
          </div>}
        </div>
        <span className="account-actions">
          <button type="button" className="secondary compact" disabled={!!busy} onClick={() => test(item)}>{busy === `test-${item.id}` ? 'Testing…' : 'Test key'}</button>
          <button type="button" className="secondary compact" disabled={!!busy} onClick={() => { setReplacing(item.id); setReplacement('') }}>Replace</button>
          <button type="button" className="secondary compact" disabled={!!busy} onClick={() => rename(item)}>Rename</button>
          <button type="button" className="danger secondary compact" disabled={!!busy || item.waiting > 0} title={item.waiting ? 'Runs are waiting on this key' : undefined} onClick={() => remove(item)}>Remove</button>
        </span>
      </li>
    })}</ul>}
    <div className="account-add key-add">
      <label className="visually-hidden" htmlFor={`key-name-${engine.id}-${purpose}`}>Name for a new {engine.name} key</label>
      <input id={`key-name-${engine.id}-${purpose}`} className="key-name" maxLength={40} placeholder={first ? 'Name (Default)' : 'Name, for example “Work”'} value={name} disabled={!!busy}
        onChange={e => setName(e.target.value)} />
      <label className="visually-hidden" htmlFor={`key-${engine.id}-${purpose}`}>{engine.name} key</label>
      <input id={`key-${engine.id}-${purpose}`} type="password" autoComplete="off" spellCheck={false} placeholder={`Paste your ${engine.company} API key`} value={key} disabled={!!busy}
        onChange={e => setKey(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && key.trim() && label) { e.preventDefault(); add() } }} />
      <button type="button" className={first ? 'compact' : 'secondary compact'} disabled={!!busy || !key.trim() || !label} onClick={add}>{busy === 'add' ? 'Saving…' : first ? 'Save key' : 'Add key'}</button>
    </div>
    <StatusNote text={message} />
    {error && <p className="frame-error" role="alert">{error}</p>}
    <p className="hint">Billed by {engine.company}, separately from your plans; every run asks you first and names the key.{shared ? ` ${shared}` : ''}</p>
  </div>
}

/** On a paused or finished card (Phase 8B): continue the waiting (or failed) items with
 *  another of the provider's keys. Sent as `account_id`, with a confirmation naming it. */
export function KeyChoice({ engine, purpose, current, verb, pick, onPick }: { engine: string; purpose: KeyPurpose; current: RunAccount | null; verb: string; pick: AccountPick; onPick: (pick: AccountPick) => void }) {
  const { byId } = useApiEngines()
  const id = useId()
  const item = byId[engine]
  if (!isApiEngine(engine) || !current || !item || item.keys.length < 2 && item.keys.some(k => k.id === current.id)) return null
  const chosen = pick.account_id ?? current.id
  const target = item.keys.find(k => k.id === chosen)
  const active = chargeKey(item, purpose)
  const moved = chosen !== current.id
  const gone = !item.keys.some(k => k.id === current.id)
  return <div className="account-switch">
    <label htmlFor={id}>{verb} with the key</label>
    <select id={id} value={chosen} onChange={e => onPick({ account_id: e.target.value === current.id ? null : e.target.value, make_active: false })}>
      {gone && <option value={current.id} disabled>{current.label} (removed)</option>}
      {item.keys.map(k => <option key={k.id} value={k.id}>{k.label}{k.id === current.id ? ' (used so far)' : ''}</option>)}
    </select>
    {moved && target && <label className="checkbox-label"><input type="checkbox" checked={pick.make_active} onChange={e => onPick({ ...pick, make_active: e.target.checked })} /> Also use for future runs</label>}
    {moved && target && <span className="hint">{pick.make_active ? `New runs will be charged to ${keyName(target)} too.` : `Only this run moves to ${keyName(target)}. New runs keep using ${active ? keyName(active) : 'the key chosen in Studio settings'}.`} The charge confirmation names the new key.</span>}
    {gone && !moved && <span className="hint">The key this run used was removed. Choose another key to continue.</span>}
  </div>
}
