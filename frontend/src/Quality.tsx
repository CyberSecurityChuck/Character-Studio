import { useCallback, useEffect, useRef, useState } from 'react'
import { request, send } from './api'
import { ChargeDialog, engineNames, isApiEngine, sendsTo, useApiEngines } from './ApiEngines'
import type { SceneDetail } from './Scenes'

/** Identity and composition checks of one result (Phase 6B). A model's opinion of what it can
 *  see, never a measurement; it changes nothing about the result or its approval. */
export type QualityCheck = {
  id: string; result_id: string; job_id: string | null; engine: string; engine_version: string | null; created_at: string
  composition_score: number | null; identity_score: number | null
  data: {
    composition: Record<string, { score: number; note: string }>
    identity: { subject: string; expected: 'replaced' | 'kept' | 'unassigned'; score: number; note: string }[]
    summary: string; issues: string[]
  }
}
type RunJob = { id: string; status: string; engine_name: string; error_details: string | null }
type EngineSettings = { analysis_engine: string; api_models: Record<string, { analysis?: string }> }

export const scoreLabels = ['Could not judge', 'Does not match', 'Clear differences', 'Some differences', 'Close', 'Very close']
const aspectLabels: Record<string, string> = { camera_and_framing: 'Camera and framing', subject_positions: 'Positions', poses: 'Poses', head_and_gaze: 'Head and gaze', outfits: 'Outfits', environment: 'Environment', lighting: 'Lighting' }
const expectLabels = { replaced: 'should be the assigned character', kept: 'should stay as in the Base Image', unassigned: 'not assigned' }
const tone = (score: number | null) => score == null || score === 0 ? 'none' : score >= 4 ? 'good' : score === 3 ? 'mid' : 'bad'
const formatDate = (value: string) => new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })

export function Score({ score }: { score: number | null }) {
  const value = score ?? 0
  return <span className={`score ${tone(score)}`} title={`${value} of 5`}>
    <span className="pips" aria-hidden="true">{[1, 2, 3, 4, 5].map(n => <i key={n} className={n <= value ? 'on' : ''} />)}</span>
    <span>{score == null ? 'Not checked' : scoreLabels[value]}</span>
  </span>
}

/** Short label for a result card: the weaker of composition and identity. */
export function checkBadge(check: QualityCheck | null) {
  if (!check) return null
  const scores = [check.composition_score, check.identity_score].filter((s): s is number => s != null)
  const worst = scores.length ? Math.min(...scores) : null
  return { label: worst == null ? 'Checked' : scoreLabels[worst], tone: tone(worst) }
}

export function QualityPanel({ resultId, resultVersion, references, token, runningJobId, onStarted, onDone }: {
  resultId: string; resultVersion: number; references: number; token: string; runningJobId?: string | null
  onStarted?: (detail: SceneDetail) => void; onDone?: () => void
}) {
  const [checks, setChecks] = useState<QualityCheck[]>([])
  const [shownId, setShownId] = useState<string | null>(null)
  const [job, setJob] = useState<RunJob | null>(null)
  const [jobId, setJobId] = useState<string | null>(runningJobId ?? null)
  const [settings, setSettings] = useState<EngineSettings | null>(null)
  const [asking, setAsking] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const api = useApiEngines()
  // Parents pass a new callback on every render; the poll should not restart for that.
  const done = useRef(onDone)
  done.current = onDone
  const load = useCallback(() => request<QualityCheck[]>(`/api/results/${resultId}/checks`).then(setChecks, e => setError(e.message)), [resultId])
  useEffect(() => { void load(); request<EngineSettings>('/api/engines/settings').then(setSettings, () => undefined) }, [load])
  useEffect(() => { if (runningJobId) setJobId(runningJobId) }, [runningJobId])
  useEffect(() => {
    if (!jobId) return
    let stop = false
    const poll = async () => {
      try {
        const current = await request<RunJob>(`/api/jobs/${jobId}`)
        if (stop) return
        setJob(current)
        if (['not_started', 'running'].includes(current.status)) { window.setTimeout(() => void poll(), 1500); return }
        setJobId(null); setBusy(false)
        if (current.status === 'completed') { setShownId(null); await load(); setJob(null) }
        done.current?.()
      } catch { if (!stop) window.setTimeout(() => void poll(), 3000) }
    }
    void poll()
    return () => { stop = true }
  }, [jobId, load])

  const engine = settings?.analysis_engine ?? 'claude_cli'
  const apiEngine = isApiEngine(engine) ? api.byId[engine] : undefined
  const what = `the Base Image, ${references} reference ${references === 1 ? 'photo' : 'photos'} and result ${resultVersion} (without location data)`
  async function start(confirmed: boolean) {
    setBusy(true); setError('')
    try {
      const detail = await send<SceneDetail>(`/api/results/${resultId}/check`, 'POST', token, confirmed ? { confirm_charges: true } : undefined)
      onStarted?.(detail)
      setJobId(detail.active_job?.kind === 'check' ? detail.active_job.id : null)
    } catch (e) { setError(e instanceof Error ? e.message : 'The check could not be started.'); setBusy(false) }
  }
  function ask() {
    if (engine === 'manual') return
    if (isApiEngine(engine)) { void api.reload(); setAsking(true); return }
    if (window.confirm(`Check result ${resultVersion} with ${engineNames[engine]}? This sends ${what} to ${sendsTo[engine]} and uses your plan’s allowance once. Nothing about the result changes.`)) void start(false)
  }
  const cancel = () => { if (jobId) void send(`/api/jobs/${jobId}/cancel`, 'POST', token).catch(() => undefined) }
  const remove = (check: QualityCheck) => {
    if (!window.confirm('Delete this check? The result is not changed.')) return
    void send(`/api/checks/${check.id}`, 'DELETE', token).then(() => { setShownId(null); void load() }, e => setError(e.message))
  }
  const shown = checks.find(c => c.id === shownId) ?? checks[0]
  const running = !!jobId && (!job || ['not_started', 'running'].includes(job.status))

  return <section className="quality-panel" aria-labelledby={`quality-${resultId}`}>
    <div className="quality-head">
      <h3 id={`quality-${resultId}`}>Quality check</h3>
      {checks.length > 1 && <select aria-label="Earlier checks" value={shown?.id} onChange={e => setShownId(e.target.value)}>{checks.map((c, i) => <option key={c.id} value={c.id}>{i === 0 ? 'Latest' : 'Earlier'} · {formatDate(c.created_at)} · {engineNames[c.engine] ?? c.engine}</option>)}</select>}
    </div>
    {running ? <div className="progress-card" role="status"><span className="spinner" aria-hidden="true" />
      <div><strong>{job?.status === 'running' ? `Checking with ${job.engine_name}…` : 'Waiting to start…'}</strong><p>Runs once. You can close this window; the check continues.</p></div>
      <button type="button" className="secondary" onClick={cancel}>Cancel</button></div>
      : job && job.status !== 'completed' ? <p className="frame-error" role="alert">{job.status === 'cancelled' ? 'The check was cancelled.' : job.error_details ?? 'The check did not finish.'}</p> : null}
    {shown ? <>
      <div className="quality-scores">
        <div><span className="field-label">Composition</span><Score score={shown.composition_score} /></div>
        <div><span className="field-label">Identity</span>{shown.identity_score == null ? <span className="hint">No replaced people</span> : <Score score={shown.identity_score} />}</div>
      </div>
      <p className="quality-summary">{shown.data.summary}</p>
      {shown.data.issues.length > 0 && <><span className="field-label">Worth fixing</span><ul className="quality-issues">{shown.data.issues.map(i => <li key={i}>{i}</li>)}</ul></>}
      <details className="quality-details"><summary>Every aspect and person</summary>
        <table><tbody>
          {Object.entries(shown.data.composition).map(([key, a]) => <tr key={key}><th scope="row">{aspectLabels[key] ?? key}</th><td><Score score={a.score} /></td><td>{a.note}</td></tr>)}
          {shown.data.identity.map(i => <tr key={i.subject}><th scope="row">{i.subject} <small>({expectLabels[i.expected]})</small></th><td><Score score={i.score} /></td><td>{i.note}</td></tr>)}
        </tbody></table>
      </details>
      <p className="hint">{engineNames[shown.engine] ?? shown.engine}{shown.engine_version ? ` · ${shown.engine_version}` : ''} · {formatDate(shown.created_at)}. A model’s opinion of what it can see, not a measurement; check the images yourself.</p>
    </> : !running && <p className="hint">Ask the analysis engine how closely this result keeps the Base Image’s composition and each person’s identity. It sends {what} to {engine === 'manual' ? 'the selected engine' : sendsTo[engine]}.</p>}
    {error && <p className="frame-error" role="alert">{error}</p>}
    {engine === 'manual' ? <p className="hint">Quality checks need an analysis engine; Manual is selected in Studio settings.</p>
      : <div className="quality-actions"><button type="button" className="secondary" disabled={busy || running} onClick={ask}>{shown ? 'Check again' : 'Check quality'}</button>
        {shown && <button type="button" className="link-button" disabled={busy || running} onClick={() => remove(shown)}>Delete this check</button>}</div>}
    {asking && apiEngine && <ChargeDialog engine={apiEngine} model={settings?.api_models[engine]?.analysis ?? null} runs={1} what={what}
      title={`Check result ${resultVersion} with the ${apiEngine.name}?`} action="Check" onConfirm={() => void start(true)} onClose={() => setAsking(false)} />}
  </section>
}
