import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { ApiError, request, send } from './api'
import { ApiKeysPanel, apiEngineIds, isApiEngine, useApiEngines } from './ApiEngines'
import { InfoTip } from './Controls'

type Status = { engine: string; name: string; installed: boolean; version: string | null; signed_in: boolean; plan: string | null; message: string }
type Settings = { analysis_engine: string; generation_engine: string; claude_timeout: number; codex_timeout: number; api_timeout: number; api_models: Record<string, { analysis?: string }>; revision: number }

const analysisChoices = [
  { id: 'claude_cli', name: 'Claude (default)', note: 'Uses your Claude plan. Sends the Base Image to Anthropic.' },
  { id: 'codex_cli', name: 'Codex', note: 'Uses your ChatGPT plan’s Codex allowance, which image generation also uses. Sends the Base Image to OpenAI.' },
  { id: 'manual', name: 'Manual', note: 'Copy the instruction into any app and paste the reply back. Nothing is sent by the studio.' },
  { id: 'gemini_api', name: 'Gemini API', note: 'Uses your Google AI Studio key. Free-tier keys are not charged for analysis with free models, but Google may use free-tier content to improve its products. Sends the Base Image to Google.' },
  { id: 'anthropic_api', name: 'Anthropic API', note: 'Uses your Anthropic API key, billed per use, separately from a Claude plan. Sends the Base Image to Anthropic.' },
  { id: 'openai_api', name: 'OpenAI API', note: 'Uses your OpenAI API key, billed per use, separately from ChatGPT plans. Sends the Base Image to OpenAI.' },
]

function StatusCard({ status, checking }: { status?: Status; checking: boolean }) {
  const ready = !!status?.installed && status.signed_in
  const state = checking && !status ? 'Checking…' : !status ? 'Unknown' : !status.installed ? 'Not found' : status.signed_in ? 'Ready' : 'Signed out'
  return <div className={`engine-status ${ready ? 'ready' : status ? 'attention' : ''}`}>
    <span className="status-dot" aria-hidden="true" />
    <div><strong>{status?.name ?? '…'}</strong><span className="engine-state">{state}{status?.plan ? ` · ${status.plan}` : ''}</span>
      <p className="hint">{status?.version ?? (status?.installed === false ? 'Not installed on this PC' : '')}</p>
      {status?.message && <p className="hint">{status.message}</p>}</div>
  </div>
}

export default function Engines({ token }: { token: string }) {
  const [statuses, setStatuses] = useState<Status[]>([])
  const [checking, setChecking] = useState(false)
  const [saved, setSaved] = useState<Settings | null>(null)
  const [form, setForm] = useState<Settings | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const api = useApiEngines()
  const [models, setModels] = useState<Record<string, string[]>>({})

  const check = useCallback(async () => {
    setChecking(true)
    try { setStatuses(await request<Status[]>('/api/engines/status')) }
    catch (e) { setError(e instanceof Error ? e.message : 'Engine status could not be checked.') }
    finally { setChecking(false) }
  }, [])
  useEffect(() => {
    request<Settings>('/api/engines/settings').then(s => { setSaved(s); setForm(s) }, e => setError(e.message))
    void check()
  }, [check])

  const dirty = !!form && !!saved && JSON.stringify(form) !== JSON.stringify(saved)
  async function save(e: FormEvent) {
    e.preventDefault()
    if (!form) return
    setBusy(true); setError(''); setMessage('')
    try { const next = await send<Settings>('/api/engines/settings', 'PUT', token, form); setSaved(next); setForm(next); setMessage('Saved to this computer') }
    catch (e) { setError(e instanceof Error ? e.message : 'Settings could not be saved.'); if (e instanceof ApiError && e.status === 409) setMessage('Reload the page to see the latest settings.') }
    finally { setBusy(false) }
  }
  const byEngine = Object.fromEntries(statuses.map(s => [s.engine, s]))
  const setModel = (engine: string, value: string) => form && setForm({ ...form, api_models: { ...form.api_models, [engine]: { analysis: value } } })
  return <><section className="panel provider-panel engines-panel" aria-labelledby="engines-title">
    <div className="panel-head"><div><span className="tiny-label">YOUR SIGN-INS, YOUR PLANS</span><h2 id="engines-title">Analysis and generation engines</h2></div>
      <button type="button" className="secondary" disabled={checking} onClick={() => void check()}>{checking ? 'Checking…' : 'Check again'}</button></div>
    <p>The studio runs the official Claude Code and Codex programs installed on this PC, one run per click. It never reads or stores your logins and never retries on its own. Optional API engines use your own keys (below) and ask before every run.</p>
    <div className="engine-statuses"><StatusCard status={byEngine.claude_cli} checking={checking} /><StatusCard status={byEngine.codex_cli} checking={checking} /></div>
    {form && <form onSubmit={e => void save(e)}><fieldset disabled={busy}>
      <fieldset className="engine-choice"><legend>Analysis engine</legend>
        <div className="choice-grid">{analysisChoices.map(c => <label key={c.id} className={`choice-card ${form.analysis_engine === c.id ? 'selected' : ''}`}>
          <input type="radio" name="analysis-engine" value={c.id} checked={form.analysis_engine === c.id} onChange={() => setForm({ ...form, analysis_engine: c.id })} />
          <strong>{c.name}</strong>{isApiEngine(c.id) && !api.byId[c.id]?.key.saved && <span className="choice-note">needs a key</span>}<InfoTip label={`${c.name} analysis`}>{c.note}</InfoTip></label>)}</div>
      </fieldset>
      <fieldset className="engine-choice api-models"><legend>API engine models</legend>
        <div className="engine-fields">{apiEngineIds.map(id => {
          const item = api.byId[id]
          const value = form.api_models[id]?.analysis ?? ''
          const options = [...new Set([...(models[id] ?? []), ...(item?.suggested_model ? [item.suggested_model] : [])])]
          return <div key={id}><div className="label-row"><label htmlFor={`model-${id}`}>{item?.name ?? id} model</label><InfoTip label={`${item?.name ?? id} model`}>The model that analyses scenes with this engine. Use Test key under API keys to list the models your key can use{item?.suggested_model ? `; ${item.suggested_model} is on Google’s free tier as of October 2026` : ''}. Leave empty if you do not use this engine.</InfoTip></div>
            <input id={`model-${id}`} list={`models-${id}`} value={value} maxLength={80} spellCheck={false} placeholder={item?.suggested_model ?? 'Test the key to list models'} onChange={e => setModel(id, e.target.value)} />
            <datalist id={`models-${id}`}>{options.map(m => <option key={m} value={m} />)}</datalist></div>
        })}</div>
      </fieldset>
      <div className="engine-fields">
        <div><div className="label-row"><label htmlFor="generation-engine">Generation engine</label><InfoTip label="Generation engine">Creates the final image from an approved scene. Codex runs it from the studio with your ChatGPT sign-in. Manual lets you export the package, use any app yourself and import the result.</InfoTip></div><select id="generation-engine" value={form.generation_engine} onChange={e => setForm({ ...form, generation_engine: e.target.value })}><option value="codex_cli">Codex (default)</option><option value="manual">Manual</option></select></div>
        <div><div className="label-row"><label htmlFor="claude-timeout">Claude time limit (seconds)</label><InfoTip label="Claude time limit">A Claude run that reaches this limit is stopped and marked as failed. 30 to 1800 seconds. Typical analyses take under a minute.</InfoTip></div><input id="claude-timeout" type="number" min={30} max={1800} step={10} required value={form.claude_timeout} onChange={e => setForm({ ...form, claude_timeout: Number(e.target.value) })} /></div>
        <div><div className="label-row"><label htmlFor="codex-timeout">Codex time limit (seconds)</label><InfoTip label="Codex time limit">A Codex run that reaches this limit is stopped and marked as failed. 30 to 1800 seconds. Typical analyses take under a minute; one image took about 70 seconds in testing.</InfoTip></div><input id="codex-timeout" type="number" min={30} max={1800} step={10} required value={form.codex_timeout} onChange={e => setForm({ ...form, codex_timeout: Number(e.target.value) })} /></div>
        <div><div className="label-row"><label htmlFor="api-timeout">API time limit (seconds)</label><InfoTip label="API time limit">How long the studio waits for an API engine’s answer. A request that has already been sent may still finish and be charged after the studio stops waiting. 30 to 1800 seconds.</InfoTip></div><input id="api-timeout" type="number" min={30} max={1800} step={10} required value={form.api_timeout} onChange={e => setForm({ ...form, api_timeout: Number(e.target.value) })} /></div>
      </div>
      {error && <p className="frame-error" role="alert">{error}</p>}
      <div className="panel-actions"><span className="spacer" role="status">{busy ? 'Saving…' : dirty ? 'Unsaved changes' : message || 'All changes saved'}</span>
        <button type="button" className="secondary" disabled={!dirty} onClick={() => setForm(saved)}>Cancel</button>
        <button disabled={!dirty || busy}>Save engine settings</button></div>
    </fieldset></form>}
    <div className="privacy-note"><strong>What leaves this computer</strong><p>Analyse sends the Base Image, without location data, to the selected engine’s company (Anthropic for Claude and the Anthropic API, OpenAI for Codex and the OpenAI API, Google for the Gemini API). Polish prompt sends the prompt text and the analysis to Anthropic. Generate sends the Base Image and the approved reference photos, without location data, to OpenAI via Codex. Character names are never sent. Manual analysis and manual export send nothing from the studio.</p></div>
  </section>
  <ApiKeysPanel engines={api.engines} token={token} selectedEngine={saved?.analysis_engine ?? ''} onChanged={() => void api.reload()} onModels={(engine, list) => setModels(m => ({ ...m, [engine]: list }))} /></>
}
