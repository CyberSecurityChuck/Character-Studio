import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { ApiError, request, send } from './api'
import { ApiKeyBox, isApiEngine, useApiEngines, type ApiEngine } from './ApiEngines'
import { InfoTip } from './Controls'
import { ModelPicker } from './ModelPicker'

type Status = { engine: string; name: string; installed: boolean; version: string | null; signed_in: boolean; plan: string | null; message: string }
type Settings = { analysis_engine: string; generation_engine: string; claude_timeout: number; codex_timeout: number; api_timeout: number; models: Record<string, { analysis?: string }>; revision: number }
type Choice = { id: string; name: string; tag?: string; line: string }

// Aliases that `claude --help` documents for `--model`; Codex takes any model name.
const claudeModels = ['opus', 'sonnet', 'fable']
const analysisGroups: { title: string; hint: string; items: Choice[] }[] = [
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
const generationChoices: Choice[] = [
  { id: 'codex_cli', name: 'Codex', tag: 'Subscription', line: 'Your ChatGPT plan · generates from the approved images' },
  { id: 'manual', name: 'Manual', line: 'Export the package, make the image in any app, import it' },
]
const analysisFields = ['analysis_engine', 'models', 'claude_timeout', 'codex_timeout', 'api_timeout'] as const
const generationFields = ['generation_engine', 'codex_timeout'] as const
type Field = keyof Settings
const pick = (s: Settings, fields: readonly Field[]) => Object.fromEntries(fields.map(f => [f, s[f]])) as Partial<Settings>
const same = (a: Settings, b: Settings, fields: readonly Field[]) => JSON.stringify(pick(a, fields)) === JSON.stringify(pick(b, fields))
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
    <div className="panel-actions"><span className="spacer" role="status">{busy ? 'Saving…' : blocked && dirty ? blocked : dirty ? 'Unsaved changes' : message || 'All changes saved'}</span>
      <button type="button" className="secondary" disabled={!dirty || busy} onClick={onCancel}>Cancel</button>
      <button type="button" disabled={!dirty || busy || !!blocked} onClick={onSave}>{label}</button></div>
  </>
}

export default function Engines({ token }: { token: string }) {
  const [statuses, setStatuses] = useState<Status[]>([])
  const [checking, setChecking] = useState(false)
  const [saved, setSaved] = useState<Settings | null>(null)
  const [form, setForm] = useState<Settings | null>(null)
  const [busy, setBusy] = useState<'analysis' | 'generation' | ''>('')
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

  async function save(panel: 'analysis' | 'generation', fields: readonly Field[]) {
    if (!form || !saved) return
    setBusy(panel); setErrors(e => ({ ...e, [panel]: '' })); setMessages(m => ({ ...m, [panel]: '' }))
    try {
      const next = await send<Settings>('/api/engines/settings', 'PUT', token, { ...saved, ...pick(form, fields), revision: saved.revision })
      setSaved(next)
      // Keep the other panel's unsaved edits.
      setForm(f => f && { ...f, ...pick(next, fields), revision: next.revision })
      setMessages(m => ({ ...m, [panel]: 'Saved to this computer' }))
    } catch (e) {
      const text = e instanceof Error ? e.message : 'Settings could not be saved.'
      setErrors(er => ({ ...er, [panel]: e instanceof ApiError && e.status === 409 ? `${text} Reload the page to see the latest settings.` : text }))
    } finally { setBusy('') }
  }
  if (!form || !saved) return <section className="panel provider-panel"><p role="status">{errors.analysis || 'Loading engine settings…'}</p></section>

  const byStatus = Object.fromEntries(statuses.map(s => [s.engine, s]))
  const engine = form.analysis_engine
  const model = form.models[engine]?.analysis ?? ''
  const setModel = (id: string, value: string) => setForm({ ...form, models: { ...form.models, [id]: { analysis: value } } })
  const apiItem: ApiEngine | undefined = isApiEngine(engine) ? api.byId[engine] : undefined
  const blocked = apiItem && !apiItem.key.saved ? `Add a ${apiItem.name} key first` : apiItem && !model ? 'Choose a model first' : undefined
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
      <ApiKeyBox engine={apiItem} token={token} selected={saved.analysis_engine === engine} onChanged={() => void api.reload()} />
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
      <PanelFooter dirty={!same(form, saved, analysisFields)} busy={busy === 'analysis'} message={messages.analysis} error={errors.analysis} blocked={blocked}
        label="Save analysis engine" onCancel={() => setForm({ ...form, ...pick(saved, analysisFields) })} onSave={() => void save('analysis', analysisFields)} />
    </section>

    <section className="panel provider-panel engines-panel" aria-labelledby="generation-engine-title">
      <div className="panel-head"><div><span className="tiny-label">MAKES THE IMAGE</span><h2 id="generation-engine-title">Generation engine</h2></div></div>
      <p>Creates the final image from an approved scene, one run per click. API image engines arrive in Phase 6C.</p>
      <div className="engine-cards" role="radiogroup" aria-labelledby="generation-engine-title">{generationChoices.map(c => <ChoiceCard key={c.id} choice={c} name="generation-engine" checked={form.generation_engine === c.id}
        state={c.id === 'manual' ? undefined : statusText(byStatus.codex_cli, checking)} ready={!!byStatus.codex_cli?.signed_in} onSelect={() => setForm({ ...form, generation_engine: c.id })} />)}</div>
      <div className="engine-details">
        {form.generation_engine === 'codex_cli' ? <>
          <CliStatus name="Codex" status={byStatus.codex_cli} checking={checking} onCheck={() => void check()} />
          <div className="engine-fields"><TimeLimit id="generation-timeout" label="Time limit" value={form.codex_timeout}
            tip="A Codex run that reaches this limit is stopped. One image took about 70 seconds in testing. Shared with Codex analysis." onChange={v => setForm({ ...form, codex_timeout: v })} /></div>
          <p className="hint">Codex always uses its built-in image model; there is no model to choose here.</p>
        </> : <p className="hint">The Generate step offers <b>Export for manual use</b> and <b>Import result</b>. Nothing is sent from the studio.</p>}
      </div>
      <PanelFooter dirty={!same(form, saved, generationFields)} busy={busy === 'generation'} message={messages.generation} error={errors.generation}
        label="Save generation engine" onCancel={() => setForm({ ...form, ...pick(saved, generationFields) })} onSave={() => void save('generation', generationFields)} />
      <div className="privacy-note"><strong>What leaves this computer</strong><p>Analyse and quality checks send the Base Image (checks also the reference photos and the result), without location data, to the analysis engine’s company: Anthropic for Claude Code and the Anthropic API, OpenAI for Codex and the OpenAI API, Google for the Gemini API. Polish prompt sends the prompt text and the analysis to Anthropic. Generate sends the Base Image and the approved reference photos to OpenAI via Codex. Character names are never sent. Manual analysis and manual export send nothing.</p></div>
    </section>
  </>
}
