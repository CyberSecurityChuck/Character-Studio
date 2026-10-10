import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from 'react'

// Close a popover on outside press or Escape.
function useDismiss(open: boolean, ref: React.RefObject<HTMLElement | null>, close: () => void) {
  useEffect(() => {
    if (!open) return
    const press = (e: PointerEvent) => { if (!ref.current?.contains(e.target as Node)) close() }
    const key = (e: globalThis.KeyboardEvent) => { if (e.key === 'Escape') close() }
    document.addEventListener('pointerdown', press)
    document.addEventListener('keydown', key)
    return () => { document.removeEventListener('pointerdown', press); document.removeEventListener('keydown', key) }
  }, [open, ref, close])
}

/** A small (i) button whose explanation appears on hover, focus or click. */
export function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const id = useId()
  const ref = useRef<HTMLSpanElement>(null)
  useDismiss(open, ref, () => setOpen(false))
  return <span className="info-tip" ref={ref} onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
    {/* preventDefault keeps a surrounding <label> from toggling its control. */}
    <button type="button" className="info-button" aria-label={`About ${label}`} aria-describedby={open ? id : undefined}
      onClick={e => { e.preventDefault(); e.stopPropagation(); setOpen(true) }} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}>i</button>
    {open && <span role="tooltip" id={id} className="info-pop">{children}</span>}
  </span>
}

export type MenuItem = { label: string; onSelect: () => void; danger?: boolean; disabled?: boolean }

/** A ⋯ button with a short list of actions for one card. */
export function CardMenu({ label, items, disabled }: { label: string; items: MenuItem[]; disabled?: boolean }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  useDismiss(open, ref, () => setOpen(false))
  useEffect(() => { if (open) ref.current?.querySelector<HTMLButtonElement>('[role=menuitem]:not(:disabled)')?.focus() }, [open])
  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const entries = [...(ref.current?.querySelectorAll<HTMLButtonElement>('[role=menuitem]:not(:disabled)') ?? [])]
    const index = entries.indexOf(document.activeElement as HTMLButtonElement)
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      entries[(index + (e.key === 'ArrowDown' ? 1 : -1) + entries.length) % entries.length]?.focus()
    } else if (e.key === 'Escape' || e.key === 'Tab') {
      setOpen(false)
      if (e.key === 'Escape') button.current?.focus()
    }
  }
  return <div className="card-menu" ref={ref} onKeyDown={onKeyDown}>
    <button ref={button} type="button" className="menu-button" aria-label={`Actions for ${label}`} aria-haspopup="menu" aria-expanded={open} disabled={disabled}
      onClick={e => { e.stopPropagation(); setOpen(o => !o) }}>
      <svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="1.8" /><circle cx="12" cy="12" r="1.8" /><circle cx="19" cy="12" r="1.8" /></svg>
    </button>
    {open && <div role="menu" className="menu-pop" aria-label={`Actions for ${label}`}>
      {items.map(item => <button key={item.label} type="button" role="menuitem" className={item.danger ? 'danger' : ''} disabled={item.disabled}
        onClick={e => { e.stopPropagation(); setOpen(false); item.onSelect() }}>{item.label}</button>)}
    </div>}
  </div>
}

/** Short single-field dialog (rename) with footer actions. */
export function TextDialog({ title, label, initial, maxLength, saveLabel = 'Save', onSave, onClose }: { title: string; label: string; initial: string; maxLength: number; saveLabel?: string; onSave: (value: string) => Promise<void>; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const [value, setValue] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { ref.current?.showModal() }, [])
  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true); setError('')
    try { await onSave(value.trim()); onClose() }
    catch (err) { setError(err instanceof Error ? err.message : 'That did not work. Try again.'); setBusy(false) }
  }
  return <dialog ref={ref} className="image-dialog text-dialog" aria-labelledby="text-dialog-title" onClose={onClose}>
    <form className="text-dialog-form" onSubmit={e => void submit(e)}>
      <h2 id="text-dialog-title">{title}</h2>
      <label htmlFor="text-dialog-input">{label}</label>
      <input id="text-dialog-input" autoFocus maxLength={maxLength} value={value} disabled={busy} onChange={e => setValue(e.target.value)} />
      {error && <p className="frame-error" role="alert">{error}</p>}
      <div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Cancel</button><button disabled={busy || !value.trim() || value.trim() === initial}>{busy ? 'Saving…' : saveLabel}</button></div>
    </form>
  </dialog>
}

/** Toolbar shown while choosing several cards. */
export function SelectionBar({ count, total, onAll, onNone, onDone, children }: { count: number; total: number; onAll: () => void; onNone: () => void; onDone: () => void; children: ReactNode }) {
  return <div className="selection-bar" role="region" aria-label="Selection">
    <strong>{count} selected</strong>
    {count < total ? <button type="button" className="link-button" onClick={onAll}>Select all ({total})</button> : <button type="button" className="link-button" onClick={onNone}>Clear selection</button>}
    <span className="spacer" />
    {children}
    <button type="button" className="secondary" onClick={onDone}>Done</button>
  </div>
}

/** Display-only sentence case: capitalise the first letter, leave the rest as written. */
export const sentence = (text: string) => text ? text.charAt(0).toLocaleUpperCase() + text.slice(1) : text
