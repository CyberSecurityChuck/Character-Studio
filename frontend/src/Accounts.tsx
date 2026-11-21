import { useCallback, useEffect, useId, useState } from 'react'
import { request, send } from './api'
import { InfoTip } from './Controls'
import { notify } from './Toast'

// Phase 8A (D041, D042): several Claude Code and Codex sign-ins. Each extra account is a
// private folder the official program keeps its own sign-in in; the studio never sees it.

type AccountStatus = { installed: boolean; version: string | null; signed_in: boolean; plan: string | null; message: string }
export type Account = { id: string; label: string; default: boolean; created_at: string | null; waiting: number; status: AccountStatus | null }
export type EngineAccounts = { engine: 'claude_cli' | 'codex_cli'; name: string; active: string; accounts: Account[] }
export type RunAccount = { id: string; label: string }
/** What the user chose on a paused or finished card; sent with Continue / Try failed again. */
export type AccountPick = { account_id: string | null; make_active: boolean }

export const accountEngines = ['claude_cli', 'codex_cli'] as const
export const isAccountEngine = (engine: string) => (accountEngines as readonly string[]).includes(engine)
export const accountName = (a: RunAccount | Account) => a.id === 'default' ? 'Default account' : a.label
const uses: Record<string, string> = {
  claude_cli: 'Analysis, quality checks and Polish prompt when Claude Code is the analysis engine.',
  codex_cli: 'Image generation, Codex edits and, when Codex is the analysis engine, analysis.',
}

// One request shared by every card on the page; refreshed after any change here.
const cache: Partial<Record<'quick' | 'full', { at: number; data: Promise<EngineAccounts[]> }>> = {}
const listeners = new Set<() => void>()
function load(full: boolean, force = false): Promise<EngineAccounts[]> {
  const key = full ? 'full' : 'quick'
  const hit = cache[key]
  if (!force && hit && Date.now() - hit.at < 30_000) return hit.data
  const data = request<EngineAccounts[]>(`/api/cli-accounts${full ? '' : '?status=false'}`)
  cache[key] = { at: Date.now(), data }
  data.catch(() => { delete cache[key] })
  return data
}
function changed() { delete cache.quick; delete cache.full; listeners.forEach(fn => fn()) }

/** The accounts per engine; `full` also checks each account's sign-in (slower). */
export function useCliAccounts(full: boolean) {
  const [data, setData] = useState<EngineAccounts[] | null>(null)
  const reload = useCallback((force = false) => load(full, force).then(setData, () => undefined), [full])
  useEffect(() => {
    void reload()
    const again = () => { void reload() }
    listeners.add(again)
    return () => { listeners.delete(again) }
  }, [reload])
  const byEngine = Object.fromEntries((data ?? []).map(e => [e.engine, e])) as Partial<Record<string, EngineAccounts>>
  return { data, byEngine, reload }
}

function statusWords(status: AccountStatus | null, checking: boolean) {
  if (!status) return checking ? 'Checking…' : 'Unknown'
  if (!status.installed) return status.message === 'Removed.' ? 'Removed' : 'Not installed'
  return status.signed_in ? `Signed in${status.plan ? ` · ${status.plan}` : ''}` : 'Signed out'
}

/** Studio settings → Subscription accounts. Choices save at once; removing asks first. */
export function AccountsPanel({ token }: { token: string }) {
  const { data, reload } = useCliAccounts(true)
  const [checking, setChecking] = useState(false)
  const [busy, setBusy] = useState('')
  const [names, setNames] = useState<Record<string, string>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [watching, setWatching] = useState<{ engine: string; id: string; until: number } | null>(null)

  const check = useCallback(async () => { setChecking(true); try { await reload(true) } finally { setChecking(false) } }, [reload])
  // After opening a sign-in window, look again every few seconds until it is signed in.
  useEffect(() => {
    if (!watching) return
    const signedIn = data?.find(e => e.engine === watching.engine)?.accounts.find(a => a.id === watching.id)?.status?.signed_in
    if (signedIn || Date.now() > watching.until) { setWatching(null); if (signedIn) notify('Signed in. The account is ready to use.'); return }
    const timer = window.setTimeout(() => { void reload(true) }, 4000)
    return () => window.clearTimeout(timer)
  }, [watching, data, reload])

  async function act(engine: string, key: string, work: () => Promise<unknown>, done?: string) {
    setBusy(key); setErrors(e => ({ ...e, [engine]: '' }))
    try { await work(); changed(); await reload(true); if (done) notify(done) }
    catch (e) { setErrors(er => ({ ...er, [engine]: e instanceof Error ? e.message : 'That did not work. Reload and try again.' })) }
    finally { setBusy('') }
  }
  const add = (group: EngineAccounts) => act(group.engine, `add-${group.engine}`, async () => {
    await send(`/api/cli-accounts/${group.engine}`, 'POST', token, { label: names[group.engine] ?? '' })
    setNames(n => ({ ...n, [group.engine]: '' }))
  }, `Account added. Use Sign in to sign it in to ${group.name}.`)
  const choose = (group: EngineAccounts, account: Account) => act(group.engine, `use-${account.id}`,
    () => send(`/api/cli-accounts/${group.engine}/active`, 'PUT', token, { account_id: account.id }),
    `${group.name} now uses ${accountName(account)} for new runs. Runs already queued keep their account.`)
  async function signIn(group: EngineAccounts, account: Account) {
    setBusy(`sign-${account.id}`); setErrors(e => ({ ...e, [group.engine]: '' }))
    try {
      await send(`/api/cli-accounts/${group.engine}/${account.id}/sign-in`, 'POST', token)
      notify(`A ${group.name} sign-in window opened. Finish signing in there; this page updates when it is done.`)
      setWatching({ engine: group.engine, id: account.id, until: Date.now() + 5 * 60_000 })
    } catch (e) { setErrors(er => ({ ...er, [group.engine]: e instanceof Error ? e.message : 'The sign-in window could not be opened.' })) }
    finally { setBusy('') }
  }
  const rename = (group: EngineAccounts, account: Account) => {
    const label = window.prompt(`New name for “${account.label}”`, account.label)
    if (!label || label.trim() === account.label) return
    void act(group.engine, `rename-${account.id}`, () => send(`/api/cli-accounts/${group.engine}/${account.id}`, 'PUT', token, { label }))
  }
  const remove = (group: EngineAccounts, account: Account) => {
    if (!window.confirm(`Remove “${account.label}”? ${group.name} signs this account out on this PC and its folder is deleted. Past runs keep the name. You can add it again and sign in later.`)) return
    void act(group.engine, `remove-${account.id}`, () => send(`/api/cli-accounts/${group.engine}/${account.id}`, 'DELETE', token), `“${account.label}” was signed out and removed.`)
  }

  return <section className="panel provider-panel accounts-panel" aria-labelledby="accounts-title">
    <div className="panel-head"><div><span className="tiny-label">YOUR SIGN-INS</span><h2 id="accounts-title">Subscription accounts</h2></div>
      <button type="button" className="secondary compact" disabled={checking} onClick={() => void check()}>{checking ? 'Checking…' : 'Check again'}</button></div>
    <p>Sign in to more than one Claude or ChatGPT account and choose which one new runs use. A paused batch can also continue on another account with one click.</p>
    {!data && <p role="status">{checking ? 'Checking accounts…' : 'Loading accounts…'}</p>}
    {data?.map(group => <div key={group.engine} className="account-group">
      <div className="engine-group-head"><h3>{group.name}</h3><span className="hint">{uses[group.engine]}</span></div>
      <ul className="account-list" aria-label={`${group.name} accounts`}>{group.accounts.map(account => {
        const active = group.active === account.id
        const ready = !!account.status?.installed && !!account.status.signed_in
        return <li key={account.id} className={`account-row${active ? ' active' : ''}`}>
          <label className="account-use" title={ready || account.default ? 'Use for new runs' : 'Sign in first'}>
            <input type="radio" name={`account-${group.engine}`} checked={active} disabled={!!busy || (!ready && !account.default)} onChange={() => void choose(group, account)} />
            <span className="visually-hidden">Use {account.label} for new runs</span>
          </label>
          <div className="account-main">
            <span className="account-name"><strong>{account.label}</strong>
              {account.default && <span className="engine-tag neutral">Your usual sign-in</span>}
              {active && <span className="engine-tag">Used for new runs</span>}</span>
            <span className={`engine-card-state ${ready ? 'ready' : ''}`}><span className="status-dot" aria-hidden="true" />{statusWords(account.status, checking || (watching?.id === account.id))}
              {account.waiting > 0 && <span className="hint"> · {account.waiting} {account.waiting === 1 ? 'run' : 'runs'} waiting or running</span>}</span>
          </div>
          <span className="account-actions">
            {watching?.id === account.id && <span className="hint" role="status">Finish in the sign-in window…</span>}
            {account.status && account.status.installed && !account.status.signed_in && <button type="button" className={watching?.id === account.id ? 'secondary compact' : 'compact'} disabled={!!busy} title={watching?.id === account.id ? 'Closed the window? Open it again.' : undefined} onClick={() => void signIn(group, account)}>{watching?.id === account.id ? 'Open again' : 'Sign in'}</button>}
            {!account.default && <button type="button" className="link-button" disabled={!!busy} onClick={() => rename(group, account)}>Rename</button>}
            {!account.default && <button type="button" className="danger secondary compact" disabled={!!busy || account.waiting > 0} title={account.waiting ? 'Runs are waiting on this account' : undefined} onClick={() => remove(group, account)}>Remove</button>}
          </span>
        </li>
      })}</ul>
      <form className="account-add" onSubmit={e => { e.preventDefault(); void add(group) }}>
        <label className="visually-hidden" htmlFor={`add-${group.engine}`}>Name for a new {group.name} account</label>
        <input id={`add-${group.engine}`} maxLength={40} placeholder={group.engine === 'claude_cli' ? 'Name, for example “Claude – work”' : 'Name, for example “ChatGPT – personal”'}
          value={names[group.engine] ?? ''} onChange={e => setNames(n => ({ ...n, [group.engine]: e.target.value }))} />
        <button type="submit" className="secondary compact" disabled={!!busy || !(names[group.engine] ?? '').trim()}>Add account</button>
        <InfoTip label={`Adding a ${group.name} account`}>The studio makes an empty, private folder for the account in your data folder (never backed up). Sign in uses {group.name}’s own sign-in in a separate window, so the studio never sees your password or sign-in details.</InfoTip>
      </form>
      {errors[group.engine] && <p className="frame-error" role="alert">{errors[group.engine]}</p>}
    </div>)}
    <div className="privacy-note"><strong>About several accounts</strong><p>Each account uses its own plan’s allowance. Switch when an account is signed out or when you want to keep work and personal use apart. OpenAI’s and Anthropic’s terms don’t allow using extra accounts just to get around usage limits, and accounts used that way can be restricted. When a limit is reached, waiting for it to reset is the safe choice.</p></div>
  </section>
}

/** On a paused or finished card: run the waiting (or failed) items on another account. */
export function AccountChoice({ engine, current, verb, pick, onPick, limit = false }: { engine: string; current: RunAccount | null; verb: string; pick: AccountPick; onPick: (pick: AccountPick) => void; limit?: boolean }) {
  const { byEngine } = useCliAccounts(true)
  const id = useId()
  const group = byEngine[engine]
  if (!isAccountEngine(engine) || !current || !group || group.accounts.length < 2) return null
  const chosen = pick.account_id ?? current.id
  const target = group.accounts.find(a => a.id === chosen)
  const active = group.accounts.find(a => a.id === group.active)
  const moved = chosen !== current.id
  return <div className="account-switch">
    <label htmlFor={id}>{verb} on</label>
    <select id={id} value={chosen} onChange={e => onPick({ account_id: e.target.value === current.id ? null : e.target.value, make_active: false })}>
      {group.accounts.map(a => {
        const out = !!a.status && !a.status.signed_in
        return <option key={a.id} value={a.id} disabled={out && a.id !== current.id}>{accountName(a)}{a.id === current.id ? ' (used so far)' : ''}{out ? ' · signed out' : ''}</option>
      })}
    </select>
    {moved && target && <label className="checkbox-label"><input type="checkbox" checked={pick.make_active} onChange={e => onPick({ ...pick, make_active: e.target.checked })} /> Also use for future runs</label>}
    {moved && target && limit && <span className="hint account-terms">This pause is a plan limit. OpenAI’s and Anthropic’s terms don’t allow using another account just to get around a usage limit; waiting for the reset is the safe choice.</span>}
    {moved && target && <span className="hint">{pick.make_active ? `New runs will use ${accountName(target)} too.` : `Only this run moves to ${accountName(target)}. New runs keep using ${active ? accountName(active) : 'the account chosen in Studio settings'}.`}</span>}
  </div>
}

/** The body for Continue / Try failed again with the chosen account, if one was chosen. */
export const pickBody = (pick: AccountPick, engine?: string) => pick.account_id ? { account_id: pick.account_id, make_active: pick.make_active, ...(engine ? { account_engine: engine } : {}) } : {}
export const afterPick = (pick: AccountPick) => { if (pick.account_id) changed() }
