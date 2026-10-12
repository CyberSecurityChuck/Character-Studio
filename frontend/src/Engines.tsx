import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { ApiError, request, send } from './api'
import { ApiKeyBox, isApiEngine, isImageEngine, useApiEngines, type ApiEngine } from './ApiEngines'
import { InfoTip } from './Controls'
import { ModelPicker } from './ModelPicker'
import { notify } from './Toast'

type Status = { engine: string; name: string; installed: boolean; version: string | null; signed_in: boolean; plan: string | null; message: string }
type Purpose = 'analysis' | 'generation'
type ImageOptions = { size: string; quality?: string }
type Settings = { analysis_engine: string; generation_engine: string; claude_timeout: number; codex_timeout: number; api_timeout: number
  models: Record<string, { analysis?: string; generation?: string }>; image_options: Record<string, ImageOptions>; revision: number }
type Choice = { id: string; name: string; tag?: string; line: string }
type Group = { title: string; hint: string; items: Choice[] }

// Aliases that `claude --help` documents for `--model`; Codex takes any model name.
const claudeModels = ['opus', 'sonnet', 'fable']
const analysisGroups: Group[] = [
  { title: 'Your subscriptions', hint: 'Plans you already pay for. No API key, no per-use billing.', items: [
    { id: 'claude_cli', name: 'Claude Code', tag: 'Subscription', line: 'Your Claude plan · sends the Base Image to Anthropic' },
    { id: 'codex_cli', name: 'Codex', tag: 'Subscription', line: 'Your ChatGPT plan · shares its allowance with image generation' },
  ] },
  { title: 'Pay per use', hint: 'Your own API key, billed by the provider. Every run asks you first.', items: [
    { id: 'gemini_api', name: 'Gemini API', tag: 'API key', line: 'Google · free tier available for analysis' },
    { id: 'anthropic_api', name: 'Anthropic API', tag: 'API key', line: 'Anthropic · billed separately from Claude plans' },
    { id: 'openai_api', name: 'OpenAI API', tag: 'API key', line: 'OpenAI · billed separately from ChatGPT plans' },
  ] },
  { title: 'Without an engine', hint: '', items: [
    { id: 'manual', name: 'Manual', line: 'Copy the instruction into any app and paste the reply back' },
  ] },
]
const generationGroups: Group[] = [
  { title: 'Your subscriptions', hint: 'No API key, no per-use billing.', items: [
    { id: 'codex_cli', name: 'Codex', tag: 'Subscription', line: 'Your ChatGPT plan · generates from the approved images' },
  ] },
  { title: 'Pay per use', hint: 'Your own API key, billed by the provider. Every run asks you first.', items: [
    { id: 'gemini_api', name: 'Gemini image', tag: 'API key', line: 'Google · charged per image, not on the free tier' },
    { id: 'openai_api', name: 'OpenAI Images', tag: 'API key', line: 'OpenAI · charged per image; your organisation must be verified' },
  ] },
  { title: 'Without an engine', hint: '', items: [
    { id: 'manual', name: 'Manual', line: 'Export the package, make the image in any app, import it' },
  ] },
]
// What each API image engine documents (October 2026); the server checks them again.
const imageSizes: Record<string, string[]> = { gemini_api: ['1K', '2K', '4K'], openai_api: ['1K', '2K'] }
const imageQualities: Record<string, string[]> = { openai_api: ['low', 'medium', 'high', 'xhigh', 'max'] }
const defaultOptions = (id: string): ImageOptions => imageQualities[id] ? { size: '1K', quality: 'medium' } : { size: '1K' }
const sizeHints: Record<string, string> = { '1K': 'About 1 megapixel', '2K': 'About 3–4 megapixels', '4K': 'About 8–16 megapixels' }

// Each panel saves only its own choices: its engine, its models and (generation) image options.
// The Codex and API time limits are shared by both panels.
const panelFields: Record<Purpose, readonly (keyof Settings)[]> = {
  analysis: ['analysis_engine', 'claude_timeout', 'codex_timeout', 'api_timeout'],
  generation: ['generation_engine', 'codex_timeout', 'api_timeout', 'image_options'],
}
function modelsFor(s: Settings, purpose: Purpose) {
  return Object.fromEntries(Object.keys(s.models).sort().map(id => [id, s.models[id]?.[purpose] ?? '']).filter(([, v]) => v))
}
function panelView(s: Settings, purpose: Purpose) {
  return JSON.stringify([...panelFields[purpose].map(f => f === 'image_options' ? Object.entries(s.image_options).sort() : s[f]), modelsFor(s, purpose)])
}
const same = (a: Settings, b: Settings, purpose: Purpose) => panelView(a, purpose) === panelView(b, purpose)
/** `target` with `source`'s choices for one panel; the other panel's choices are kept. */
function applyPanel(target: Settings, source: Settings, purpose: Purpose): Settings {
  const models: Settings['models'] = {}
  for (const id of new Set([...Object.keys(target.models), ...Object.keys(source.models)])) {
    const entry = { ...target.models[id] }
    const value = source.models[id]?.[purpose]
    if (value) entry[purpose] = value
    else delete entry[purpose]
    if (Object.keys(entry).length) models[id] = entry
  }
  const fields = Object.fromEntries(panelFields[purpose].map(f => [f, source[f]]))
  return { ...target, ...fields, models }
}
const formatDate = (value: string) => new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })

function statusText(status: Status | undefined, checking: boolean) {
  if (!status) return checking ? 'Checking…' : 'Unknown'
  return !status.installed ? 'Not installed' : status.signed_in ? `Ready${status.plan ? ` · ${status.plan}` : ''}` : 'Signed out'
}

function ChoiceCard({ choice, name, checked, state, ready, onSelect }: { choice: Choice; name: string; checked: boolean; state?: string; ready?: boolean; onSelect: () => void }) {
  return <label className={`engine-card ${checked ? 'selected' : ''}`}>
    <input type="radio" name={name} checked={checked} onChange={onSelect} />
    <span className="engine-card-body">
      <span className="engine-card-top"><strong>{choice.name}</strong>{choice.tag && <span className={`engine-tag ${choice.tag === 'API key' ? 'api' : ''}`}>{choice.tag}</span>}</span>
      <span className="engine-card-line">{choice.line}</span>
      {state && <span className={`engine-card-state ${ready ? 'ready' : ''}`}><span className="status-dot" aria-hidden="true" />{state}</span>}
    </span>
  </label>
}

function TimeLimit({ id, label, value, tip, onChange }: { id: string; label: string; value: number; tip: string; onChange: (value: number) => void }) {
  return <div className="engine-field"><div className="label-row"><label htmlFor={id}>{label}</label><InfoTip label={label}>{tip}</InfoTip></div>
    <div className="unit-input"><input id={id} type="number" min={30} max={1800} step={10} required value={value} onChange={e => onChange(Number(e.target.value))} /><span>seconds</span></div></div>
}

function CliStatus({ name, status, checking, onCheck }: { name: string; status?: Status; checking: boolean; onCheck: () => void }) {
  const ready = !!status?.installed && status.signed_in
  return <div className={`engine-status ${ready ? 'ready' : status ? 'attention' : ''}`}>
    <span className="status-dot" aria-hidden="true" />
    <div><strong>{name}</strong><span className="engine-state">{statusText(status, checking)}</span>
      <p className="hint">{status?.version ?? (status?.installed === false ? 'Not installed on this PC' : '')}{status?.message ? ` · ${status.message}` : ''}</p></div>
    <button type="button" className="secondary compact" disabled={checking} onClick={onCheck}>{checking ? 'Checking…' : 'Check again'}</button>
  </div>
}

function PanelFooter({ dirty, busy, message, error, blocked, label, onCancel, onSave }: { dirty: boolean; busy: boolean; message: string; error: string; blocked?: string; label: string; onCancel: () => void; onSave: () => void }) {
  return <>
    {error && <p className="frame-error" role="alert">{error}</p>}
    <div className="panel-actions"><span className="spacer" role="status">{busy ? 'Saving…' : blocked && dirty ? blocked : dirty ? 'Unsaved changes'
      : message ? <span className="saved-flag"><svg className="status-check" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M5.5 12.5l4.2 4.2 8.8-9.4" /></svg>{message}</span> : 'All changes saved'}</span>
      <button type="button" className="secondary" disabled={!dirty || busy} onClick={onCancel}>Cancel</button>
      <button type="button" disabled={!dirty || busy || !!blocked} onClick={onSave}>{label}</button></div>
  </>
}

export default function Engines({ token }: { token: string }) {
  const [statuses, setStatuses] = useState<Status[]>([])
  const [checking, setChecking] = useState(false)
  const [saved, setSaved] = useState<Settings | null>(null)
  const [form, setForm] = useState<Settings | null>(null)
  const [busy, setBusy] = useState<Purpose | ''>('')
  const [errors, setErrors] = useState({ analysis: '', generation: '' })
  const [messages, setMessages] = useState({ analysis: '', generation: '' })
  const api = useApiEngines()

  const check = useCallback(async () => {
    setChecking(true)
    try { setStatuses(await request<Status[]>('/api/engines/status')) } catch { /* shown as Unknown */ }
    finally { setChecking(false) }
  }, [])
  useEffect(() => {
    request<Settings>('/api/engines/settings').then(s => { setSaved(s); setForm(s) }, e => setErrors({ analysis: e.message, generation: '' }))
    void check()
  }, [check])

  async function save(panel: Purpose) {
    if (!form || !saved) return
    setBusy(panel); setErrors(e => ({ ...e, [panel]: '' })); setMessages(m => ({ ...m, [panel]: '' }))
    try {
      const next = await send<Settings>('/api/engines/settings', 'PUT', token, { ...applyPanel(saved, form, panel), revision: saved.revision })
      setSaved(next)
      // Keep the other panel's unsaved edits.
      setForm(f => f && { ...applyPanel(f, next, panel), revision: next.revision })
      setMessages(m => ({ ...m, [panel]: 'Saved to this computer' }))
      notify(`${panel === 'analysis' ? 'Analysis' : 'Generation'} engine saved. Your choice is saved on this computer.`)
    } catch (e) {
      const text = e instanceof Error ? e.message : 'Settings could not be saved.'
      setErrors(er => ({ ...er, [panel]: e instanceof ApiError && e.status === 409 ? `${text} Reload the page to see the latest settings.` : text }))
    } finally { setBusy('') }
  }
  if (!form || !saved) return <section className="panel provider-panel"><p role="status">{errors.analysis || 'Loading engine settings…'}</p></section>

  const byStatus = Object.fromEntries(statuses.map(s => [s.engine, s]))
  const engine = form.analysis_engine
  const model = form.models[engine]?.analysis ?? ''
  const setModel = (id: string, value: string, purpose: Purpose = 'analysis') => setForm({ ...form, models: { ...form.models, [id]: { ...form.models[id], [purpose]: value } } })
  const inUse = (id: string) => saved.analysis_engine === id || saved.generation_engine === id
  const apiItem: ApiEngine | undefined = isApiEngine(engine) ? api.byId[engine] : undefined
  const blocked = apiItem && !apiItem.key.saved ? `Add your ${apiItem.name} key first` : apiItem && !model ? 'Choose a model first' : undefined
  const choiceState = (id: string) => isApiEngine(id) ? (api.byId[id]?.key.saved ? 'Key saved' : 'Needs a key') : id === 'manual' ? undefined : statusText(byStatus[id], checking)
  const choiceReady = (id: string) => isApiEngine(id) ? !!api.byId[id]?.key.saved : !!byStatus[id]?.signed_in

  let details: ReactNode = null
  if (engine === 'claude_cli' || engine === 'codex_cli') {
    const claude = engine === 'claude_cli'
    details = <>
      <CliStatus name={claude ? "Claude Code" : "Codex"} status={byStatus[engine]} checking={checking} onCheck={() => void check()} />
      <div className="engine-fields">
        <div className="engine-field"><div className="label-row"><label htmlFor="cli-model">Model</label><InfoTip label="Model">{claude ? 'Default uses your Claude plan’s standard model. Opus, Sonnet and Fable always mean the latest version of that model. The same model is used for Polish prompt and quality checks.' : 'Default uses the model your ChatGPT plan gives Codex. Type a model name only if you know your plan offers it.'}</InfoTip></div>
          <ModelPicker id="cli-model" value={model} defaultLabel="Default (your plan’s choice)" options={claude ? claudeModels.map(m => ({ value: m })) : []}
            empty="Type a model name, or keep Default." onChange={v => setModel(engine, v)} /></div>
        <TimeLimit id="analysis-timeout" label="Time limit" value={claude ? form.claude_timeout : form.codex_timeout}
          tip={claude ? 'A Claude run that reaches this limit is stopped and marked as failed. Typical analyses take under a minute.' : 'A Codex run that reaches this limit is stopped. Shared with Codex image generation.'}
          onChange={v => setForm(claude ? { ...form, claude_timeout: v } : { ...form, codex_timeout: v })} />
      </div>
    </>
  } else if (apiItem) {
    const options = apiItem.models.map(m => ({ value: m, tag: m === apiItem.suggested_model ? 'Recommended' : undefined }))
    if (apiItem.suggested_model && !apiItem.models.includes(apiItem.suggested_model)) options.unshift({ value: apiItem.suggested_model, tag: 'Recommended' })
    details = <>
      <ApiKeyBox engine={apiItem} token={token} selected={inUse(engine)} onChanged={() => void api.reload()} />
      <div className="engine-fields">
        <div className="engine-field"><div className="label-row"><label htmlFor="api-model">Model</label><InfoTip label="Model">The models your key can use, listed when you saved or tested the key.{apiItem.suggested_model ? ` ${apiItem.suggested_model} is on Google’s free tier for analysis (October 2026).` : ''}</InfoTip></div>
          <ModelPicker id="api-model" value={model} options={options} disabled={!apiItem.key.saved} placeholder={apiItem.key.saved ? 'Choose a model' : 'Add a key to list models'}
            empty="No models listed yet. Use Test key." onChange={v => setModel(engine, v)}
            footer={<span className="hint">{apiItem.models_checked_at ? `List updated ${formatDate(apiItem.models_checked_at)}. Test key refreshes it.` : 'Test key fetches the list.'}</span>} /></div>
        <TimeLimit id="analysis-timeout" label="Time limit" value={form.api_timeout}
          tip="How long the studio waits for the answer. A request that has already been sent may still finish and be charged after the studio stops waiting."
          onChange={v => setForm({ ...form, api_timeout: v })} />
      </div>
    </>
  } else {
    details = <p className="hint">The Analyse step offers <b>Do it manually</b>: copy the instruction into any app, attach the Base Image, and paste the reply back. Nothing is sent from the studio. Quality checks need an engine.</p>
  }

  const generator = form.generation_engine
  const imageItem: ApiEngine | undefined = isImageEngine(generator) ? api.byId[generator] : undefined
  const imageModel = form.models[generator]?.generation ?? ''
  const options = form.image_options[generator] ?? defaultOptions(generator)
  const setOptions = (change: Partial<ImageOptions>) => setForm({ ...form, image_options: { ...form.image_options, [generator]: { ...options, ...change } } })
  const generationBlocked = imageItem && !imageItem.key.saved ? `Add your ${imageItem.name} key first` : imageItem && !imageModel ? 'Choose an image model first' : undefined
  let generationDetails: ReactNode
  if (generator === 'codex_cli') {
    generationDetails = <>
      <CliStatus name="Codex" status={byStatus.codex_cli} checking={checking} onCheck={() => void check()} />
      <div className="engine-fields"><TimeLimit id="generation-timeout" label="Time limit" value={form.codex_timeout}
        tip="A Codex run that reaches this limit is stopped. One image took about 70 seconds in testing. Shared with Codex analysis." onChange={v => setForm({ ...form, codex_timeout: v })} /></div>
      <p className="hint">Codex always uses its built-in image model; there is no model to choose here.</p>
    </>
  } else if (imageItem) {
    const choices = imageItem.image_models.map(m => ({ value: m, tag: m === imageItem.suggested_image_model ? 'Recommended' : undefined }))
    if (imageItem.suggested_image_model && !imageItem.image_models.includes(imageItem.suggested_image_model)) choices.unshift({ value: imageItem.suggested_image_model, tag: 'Recommended' })
    const qualities = imageQualities[generator]
    generationDetails = <>
      <ApiKeyBox engine={imageItem} token={token} selected={inUse(generator)} onChanged={() => void api.reload()} />
      <div className="engine-fields">
        <div className="engine-field"><div className="label-row"><label htmlFor="image-model">Image model</label><InfoTip label="Image model">The image models your key can use, listed when you saved or tested the key. {imageItem.suggested_image_model} is what {imageItem.company} recommends (October 2026).</InfoTip></div>
          <ModelPicker id="image-model" value={imageModel} options={choices} disabled={!imageItem.key.saved} placeholder={imageItem.key.saved ? 'Choose an image model' : 'Add a key to list models'}
            empty="No image models listed yet. Use Test key." onChange={v => setModel(generator, v, 'generation')}
            footer={<span className="hint">{imageItem.models_checked_at ? `List updated ${formatDate(imageItem.models_checked_at)}. Test key refreshes it.` : 'Test key fetches the list.'}</span>} /></div>
        <TimeLimit id="generation-timeout" label="Time limit" value={form.api_timeout}
          tip="How long the studio waits for the image. Complex images can take up to two minutes. A request that has already been sent may still finish and be charged after the studio stops waiting. Shared with the API analysis engines."
          onChange={v => setForm({ ...form, api_timeout: v })} />
      </div>
      <div className="engine-fields image-options">
        <div className="engine-field"><div className="label-row"><span className="field-label" id="image-size-label">Image size</span><InfoTip label="Image size">The result keeps the Base Image’s shape. Larger sizes cost more. A preset can choose another size for its runs.</InfoTip></div>
          <div className="segmented" role="radiogroup" aria-labelledby="image-size-label">{imageSizes[generator].map(size => <label key={size} className={`segment ${options.size === size ? 'selected' : ''}`} title={sizeHints[size]}>
            <input type="radio" name="image-size" checked={options.size === size} onChange={() => setOptions({ size })} />{size}</label>)}</div></div>
        {qualities && <div className="engine-field"><div className="label-row"><span className="field-label" id="image-quality-label">Quality</span><InfoTip label="Quality">Higher quality takes longer and uses more image tokens, so it costs more. Medium is a good start.</InfoTip></div>
          <div className="segmented" role="radiogroup" aria-labelledby="image-quality-label">{qualities.map(q => <label key={q} className={`segment ${options.quality === q ? 'selected' : ''}`}>
            <input type="radio" name="image-quality" checked={options.quality === q} onChange={() => setOptions({ quality: q })} />{q === 'xhigh' ? 'Extra high' : q[0].toUpperCase() + q.slice(1)}</label>)}</div></div>}
      </div>
      {imageItem.image_charge_note && <p className="hint">{imageItem.image_charge_note}</p>}
    </>
  } else {
    generationDetails = <p className="hint">The Generate step offers <b>Export for manual use</b> and <b>Import result</b>. Nothing is sent from the studio.</p>
  }
  const generationState = (id: string) => id === 'codex_cli' ? statusText(byStatus.codex_cli, checking) : choiceState(id)
  const generationReady = (id: string) => id === 'codex_cli' ? !!byStatus.codex_cli?.signed_in : choiceReady(id)

  return <>
    <section className="panel provider-panel engines-panel" aria-labelledby="analysis-engine-title">
      <div className="panel-head"><div><span className="tiny-label">READS THE SCENE</span><h2 id="analysis-engine-title">Analysis engine</h2></div></div>
      <p>Analyses Base Images, checks result quality and (with Claude Code) polishes prompts. Runs once per click and never retries on its own.</p>
      <div className="engine-groups" role="radiogroup" aria-labelledby="analysis-engine-title">
        {analysisGroups.map(group => <div key={group.title} className="engine-group">
          <div className="engine-group-head"><h3>{group.title}</h3>{group.hint && <span className="hint">{group.hint}</span>}</div>
          <div className="engine-cards">{group.items.map(c => <ChoiceCard key={c.id} choice={c} name="analysis-engine" checked={engine === c.id}
            state={choiceState(c.id)} ready={choiceReady(c.id)} onSelect={() => setForm({ ...form, analysis_engine: c.id })} />)}</div>
        </div>)}
      </div>
      <div className="engine-details" aria-label="Selected engine settings">{details}</div>
      <PanelFooter dirty={!same(form, saved, 'analysis')} busy={busy === 'analysis'} message={messages.analysis} error={errors.analysis} blocked={blocked}
        label="Save analysis engine" onCancel={() => setForm(applyPanel(form, saved, 'analysis'))} onSave={() => void save('analysis')} />
    </section>

    <section className="panel provider-panel engines-panel" aria-labelledby="generation-engine-title">
      <div className="panel-head"><div><span className="tiny-label">MAKES THE IMAGE</span><h2 id="generation-engine-title">Generation engine</h2></div></div>
      <p>Creates the final image from an approved scene, one run per click. Every engine receives exactly what you approved.</p>
      <div className="engine-groups" role="radiogroup" aria-labelledby="generation-engine-title">
        {generationGroups.map(group => <div key={group.title} className="engine-group">
          <div className="engine-group-head"><h3>{group.title}</h3>{group.hint && <span className="hint">{group.hint}</span>}</div>
          <div className="engine-cards">{group.items.map(c => <ChoiceCard key={c.id} choice={c} name="generation-engine" checked={generator === c.id}
            state={generationState(c.id)} ready={generationReady(c.id)} onSelect={() => setForm({ ...form, generation_engine: c.id })} />)}</div>
        </div>)}
      </div>
      <div className="engine-details" aria-label="Selected generation engine settings">{generationDetails}</div>
      <PanelFooter dirty={!same(form, saved, 'generation')} busy={busy === 'generation'} message={messages.generation} error={errors.generation} blocked={generationBlocked}
        label="Save generation engine" onCancel={() => setForm(applyPanel(form, saved, 'generation'))} onSave={() => void save('generation')} />
      <div className="engine-group-head region-key-head"><h3>Region editing with FLUX</h3><span className="hint">Optional. Black Forest Labs’ FLUX.1 Fill (exact masks, fixes only) and FLUX 3 (can replace a person) appear in a result’s Edit area once a key is saved. Codex, OpenAI Images and Gemini image use the settings above.</span></div>
      {api.byId.bfl_api && <ApiKeyBox engine={api.byId.bfl_api} token={token} selected={false} onChanged={() => void api.reload()} />}
      <div className="privacy-note"><strong>What leaves this computer</strong><p>Analyse and quality checks send the Base Image (checks also the reference photos and the result), without location data, to the analysis engine’s company: Anthropic for Claude Code and the Anthropic API, OpenAI for Codex and the OpenAI API, Google for the Gemini API. Polish prompt sends the prompt text and the analysis to Anthropic. Generate sends the Base Image and the approved reference photos, without location data, with the approved prompt to the generation engine’s company: OpenAI for Codex and OpenAI Images, Google for Gemini image. Edit area sends the result (and, to replace a person, that person’s approved photos), with the marked area where the engine uses it, to the edit engine’s company: OpenAI for Codex and OpenAI Images, Google for Gemini image, Black Forest Labs for FLUX. Character names are never sent. Manual analysis and manual export send nothing.</p></div>
    </section>
  </>
}
