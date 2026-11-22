import { InfoTip } from './Controls'

/** Phase 8C (D046): "Switch automatically" inside an engine panel, under Account or API keys.
 *  Off by default. When on, the ticked accounts or keys, in the user's order, are where a
 *  run moves when its own account is signed out or its key is refused. Part of the panel's
 *  form, so it saves with the panel's Save button like the account and key choice. */
export type Fallback = { on: boolean; order: string[] }
export type FallbackItem = { id: string; label: string; state?: string; ready?: boolean }
export const fallbackOff: Fallback = { on: false, order: [] }

const tips = {
  account: 'Only when the account is signed out or was removed. The studio checks the sign-in before each run, so nothing is sent on an account that cannot be used and nothing runs twice. It never switches because of a usage limit: OpenAI’s and Anthropic’s terms don’t allow extra accounts just to get past limits. The list is tried once, in this order; if none is signed in, the run pauses as before. The account that works becomes this panel’s choice, and every switch is shown on the run.',
  key: 'Only when the provider refuses the key (for example a revoked key), or the key was removed here. The run that was refused is not sent again; the runs that have not started move to the next key in this order that passes the free Test key check. It never switches because of a spending or rate limit. Every charge confirmation names these keys, and no other key is used. The key that works becomes this panel’s choice, and every switch is shown on the run.',
}

export function FallbackPicker({ kind, items, chosen, value, onChange }: { kind: 'account' | 'key'; items: FallbackItem[]; chosen: string | null; value: Fallback; onChange: (value: Fallback) => void }) {
  const others = items.filter(i => i.id !== chosen)
  if (!others.length) return null
  const ticked = value.order.filter(id => others.some(o => o.id === id))
  const rows = [...ticked.map(id => others.find(o => o.id === id)!), ...others.filter(o => !ticked.includes(o.id))]
  const current = items.find(i => i.id === chosen)
  const what = kind === 'account' ? 'account' : 'key'
  const toggle = (id: string) => onChange({ ...value, order: ticked.includes(id) ? ticked.filter(x => x !== id) : [...ticked, id] })
  const move = (id: string, step: -1 | 1) => {
    const order = [...ticked]
    const from = order.indexOf(id)
    const to = from + step
    if (from < 0 || to < 0 || to >= order.length) return
    ;[order[from], order[to]] = [order[to], order[from]]
    onChange({ ...value, order })
  }
  // Turning it on for the first time ticks every other account or key, in list order.
  const turn = (on: boolean) => onChange({ on, order: on && !ticked.length ? others.map(o => o.id) : ticked })

  return <div className="fallback-picker">
    <div className="fallback-head">
      <label className="checkbox-label"><input type="checkbox" checked={value.on} onChange={e => turn(e.target.checked)} />
        <span><strong>Switch automatically</strong> if {current ? `“${current.label}”` : `this ${what}`} {kind === 'account' ? 'is signed out' : 'is refused'}</span></label>
      <InfoTip label="About switching automatically">{tips[kind]}</InfoTip>
    </div>
    {value.on && <>
      <p className="hint">Tick where runs may move, in order. {kind === 'account' ? 'Never for usage limits.' : 'Never for spending or rate limits.'}</p>
      <ol className="fallback-list" aria-label={`Fallback ${what}s in order`}>{rows.map(row => {
        const on = ticked.includes(row.id)
        const index = ticked.indexOf(row.id)
        return <li key={row.id} className={`fallback-row${on ? ' on' : ''}`}>
          <span className="fallback-rank" aria-hidden="true">{on ? index + 1 : ''}</span>
          <label className="checkbox-label"><input type="checkbox" checked={on} onChange={() => toggle(row.id)} />
            <strong>{row.label}</strong>{row.state && <span className={`engine-card-state ${row.ready ? 'ready' : ''}`}><span className="status-dot" aria-hidden="true" />{row.state}</span>}</label>
          {on && <span className="fallback-order">
            <button type="button" className="secondary compact icon-only" aria-label={`Move ${row.label} up`} title="Move up" disabled={index === 0} onClick={() => move(row.id, -1)}>
              <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 15l6-6 6 6" /></svg></button>
            <button type="button" className="secondary compact icon-only" aria-label={`Move ${row.label} down`} title="Move down" disabled={index === ticked.length - 1} onClick={() => move(row.id, 1)}>
              <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 9l6 6 6-6" /></svg></button>
          </span>}
        </li>
      })}</ol>
      {!ticked.length && <p className="hint">Nothing is ticked, so nothing switches.</p>}
    </>}
  </div>
}

/** One automatic switch, as recorded on a job, batch or run (from, to, reason, time). */
export type SwitchRecord = { from: string; from_label: string; to: string; to_label: string; reason: string; at: string; job_id: string; kind?: string }
const reasonWords: Record<string, string> = {
  signed_out: 'it was signed out',
  account_removed: 'it was removed',
  key_removed: 'it was removed',
  key_refused: 'the provider refused it',
}
const when = (value: string) => new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
export const switchText = (s: SwitchRecord) => `Switched automatically from “${s.from_label}” to “${s.to_label}” because ${reasonWords[s.reason] ?? s.reason}`

export function SwitchNotes({ switches }: { switches?: SwitchRecord[] }) {
  if (!switches?.length) return null
  return <>{switches.map(s => <p key={`${s.at}-${s.to}`} className="switch-note">
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 8h13l-3-3M20 16H7l3 3" /></svg>
    <span>{switchText(s)} · {when(s.at)}</span></p>)}</>
}
