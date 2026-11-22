import { useCallback, useEffect, useId, useState } from 'react'
import { request, send } from './api'
import { InfoTip } from './Controls'
import { notify } from './Toast'

// Phase 8A (D041, D042): several Claude Code and Codex sign-ins. Each extra account is a
// private folder the official program keeps its own sign-in in; the studio never sees it.

type AccountStatus = { installed: boolean; version: string | null; signed_in: boolean; plan: string | null; message: string }
export type Account = { id: string; label: string; default: boolean; created_at: string | null; waiting: number; status: AccountStatus | null }
export type EngineAccounts = { engine: 'claude_cli' | 'codex_cli'; name: string; active: Partial<Record<'analysis' | 'generation', string>>; accounts: Account[] }
export type RunAccount = { id: string; label: string }
/** What the user chose on a paused or finished card; sent with Continue / Try failed again. */
export type AccountPick = { account_id: string | null; make_active: boolean }

export const accountEngines = ['claude_cli', 'codex_cli'] as const
export const isAccountEngine = (engine: string) => (accountEngines as readonly string[]).includes(engine)
export const accountName = (a: RunAccount | Account) => a.id === 'default' ? 'Default account' : a.label

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

export type Purpose = 'analysis' | 'generation'
const purposeHints: Record<string, string> = {
  'claude_cli:analysis': 'Analysis, quality checks and Polish prompt run on the account you choose.',
  'codex_cli:analysis': 'Analysis and quality checks run on the account you choose. The Generation engine panel can choose another Codex account.',
  'codex_cli:generation': 'Images and Codex edits run on the account you choose. The Analysis engine panel can choose another Codex account.',
}

/** Inside an engine panel (8A review, D044): the engine's sign-ins and which one this panel's
 *  runs use. The choice is part of the panel's form and saves with it; adding, signing in,
 *  renaming and removing change the sign-ins themselves, so they happen at once. */
export function AccountPicker({ engine, purpose, chosen, saved, onChoose, token }: { engine: 'claude_cli' | 'codex_cli'; purpose: Purpose; chosen: string; saved: string; onChoose: (id: string) => void; token: string }) {
  const { byEngine, reload } = useCliAccounts(true)
  const [busy, setBusy] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [watching, setWatching] = useState<{ id: string; until: number } | null>(null)
  const group = byEngine[engine]
  const key = `${engine}:${purpose}`
  const radioName = useId()

  // After opening a sign-in window, look again every few seconds until it is signed in.
  useEffect(() => {
    if (!watching) return
    const signedIn = group?.accounts.find(a => a.id === watching.id)?.status?.signed_in
    if (signedIn || Date.now() > watching.until) { setWatching(null); if (signedIn) notify('Signed in. The account is ready to use.'); return }
    const timer = window.setTimeout(() => { void reload(true) }, 4000)
    return () => window.clearTimeout(timer)
  }, [watching, group, reload])

  async function act(what: string, work: () => Promise<unknown>, done?: string) {
    setBusy(what); setError('')
    try { await work(); changed(); await reload(true); if (done) notify(done) }
    catch (e) { setError(e instanceof Error ? e.message : 'That did not work. Reload and try again.') }
    finally { setBusy('') }
  }
  if (!group) return <p className="hint" role="status">Loading accounts…</p>
  const add = () => act('add', async () => {
    await send(`/api/cli-accounts/${engine}`, 'POST', token, { label: name })
    setName('')
  }, `Account added. Use Sign in to sign it in to ${group.name}.`)
  async function signIn(account: Account) {
    setBusy(`sign-${account.id}`); setError('')
    try {
      await send(`/api/cli-accounts/${engine}/${account.id}/sign-in`, 'POST', token)
      notify(`A ${group!.name} sign-in window opened. Finish signing in there; this page updates when it is done.`)
      setWatching({ id: account.id, until: Date.now() + 5 * 60_000 })
    } catch (e) { setError(e instanceof Error ? e.message : 'The sign-in window could not be opened.') }
    finally { setBusy('') }
  }
  const rename = (account: Account) => {
    const label = window.prompt(`New name for “${account.label}”`, account.label)
    if (!label || label.trim() === account.label) return
    void act(`rename-${account.id}`, () => send(`/api/cli-accounts/${engine}/${account.id}`, 'PUT', token, { label }))
  }
  const remove = (account: Account) => {
    const shared = engine === 'codex_cli' ? ' It also goes from the other engine panel.' : ''
    if (!window.confirm(`Remove “${account.label}”? ${group.name} signs this account out on this PC and its folder is deleted.${shared} Past runs keep the name. You can add it again and sign in later.`)) return
    void act(`remove-${account.id}`, () => send(`/api/cli-accounts/${engine}/${account.id}`, 'DELETE', token), `“${account.label}” was signed out and removed.`)
  }

  return <div className="account-picker">
    <div className="engine-group-head account-head"><h3>Account</h3>
      <span className="hint">{purposeHints[key]}</span>
      <InfoTip label="About several accounts">Each account uses its own plan’s allowance. Switch when an account is signed out or to keep work and personal use apart. OpenAI’s and Anthropic’s terms don’t allow using extra accounts just to get around usage limits, and accounts used that way can be restricted; when a limit is reached, waiting for it to reset is the safe choice. The studio never sees your sign-in details: each extra account is a private folder the program keeps its own sign-in in, never backed up.</InfoTip>
    </div>
    <ul className="account-list" aria-label={`${group.name} accounts`}>{group.accounts.map(account => {
      const selected = chosen === account.id
      const ready = !!account.status?.installed && !!account.status.signed_in
      const waitingHere = watching?.id === account.id
      return <li key={account.id} className={`account-row${selected ? ' active' : ''}`}>
        <label className="account-use" title={ready || account.default ? 'Use for new runs' : 'Sign in first'}>
          <input type="radio" name={radioName} checked={selected} disabled={!!busy || (!ready && !account.default)} onChange={() => onChoose(account.id)} />
          <span className="visually-hidden">Use {account.label} for new runs</span>
        </label>
        <div className="account-main">
          <span className="account-name"><strong>{account.label}</strong>
            {account.default && <span className="engine-tag neutral">Your usual sign-in</span>}
            {saved === account.id && chosen !== saved && <span className="engine-tag neutral">Saved choice</span>}</span>
          <span className={`engine-card-state ${ready ? 'ready' : ''}`}><span className="status-dot" aria-hidden="true" />{statusWords(account.status, waitingHere)}
            {account.waiting > 0 && <span className="hint"> · {account.waiting} {account.waiting === 1 ? 'run' : 'runs'} waiting or running</span>}</span>
        </div>
        <span className="account-actions">
          {waitingHere && <span className="hint" role="status">Finish in the sign-in window…</span>}
          {account.status && account.status.installed && !account.status.signed_in && <button type="button" className={waitingHere ? 'secondary compact' : 'compact'} disabled={!!busy} title={waitingHere ? 'Closed the window? Open it again.' : undefined} onClick={() => void signIn(account)}>{waitingHere ? 'Open again' : 'Sign in'}</button>}
          {!account.default && <button type="button" className="secondary compact" disabled={!!busy} onClick={() => rename(account)}>Rename</button>}
          {!account.default && <button type="button" className="danger secondary compact" disabled={!!busy || account.waiting > 0} title={account.waiting ? 'Runs are waiting on this account' : undefined} onClick={() => remove(account)}>Remove</button>}
        </span>
      </li>
    })}</ul>
    <div className="account-add">
      <label className="visually-hidden" htmlFor={`add-${key}`}>Name for a new {group.name} account</label>
      <input id={`add-${key}`} maxLength={40} placeholder={engine === 'claude_cli' ? 'Name, for example “Claude – work”' : 'Name, for example “ChatGPT – personal”'}
        value={name} onChange={e => setName(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); if (name.trim()) void add() } }} />
      <button type="button" className="secondary compact" disabled={!!busy || !name.trim()} onClick={() => void add()}>Add account</button>
    </div>
    {engine === 'codex_cli' && <p className="hint">Codex sign-ins are shared by both engine panels; each panel chooses its own account.</p>}
    {error && <p className="frame-error" role="alert">{error}</p>}
  </div>
}

/** On a paused or finished card: run the waiting (or failed) items on another account. */
export function AccountChoice({ engine, purpose, current, verb, pick, onPick, limit = false }: { engine: string; purpose: Purpose; current: RunAccount | null; verb: string; pick: AccountPick; onPick: (pick: AccountPick) => void; limit?: boolean }) {
  const { byEngine } = useCliAccounts(true)
  const id = useId()
  const group = byEngine[engine]
  if (!isAccountEngine(engine) || !current || !group || group.accounts.length < 2) return null
  const chosen = pick.account_id ?? current.id
  const target = group.accounts.find(a => a.id === chosen)
  // The account this kind of run uses for new runs (Claude Code has only the analysis choice).
  const active = group.accounts.find(a => a.id === (group.active[purpose] ?? group.active.analysis))
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
