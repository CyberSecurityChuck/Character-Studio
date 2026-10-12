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

export type CopySummary = { count: number; packages: number; scenes: string[] }
export type CopyChoice = 'remove' | 'keep' | null

/** Deleting a character or photo that also has copies inside saved packages: the user decides. */
export function CopiesDialog({ title, message, copies, onChoose }: { title: string; message: string; copies: CopySummary; onChoose: (choice: CopyChoice) => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const chosen = useRef<CopyChoice>(null)
  useEffect(() => { ref.current?.showModal() }, [])
  const choose = (choice: CopyChoice) => { chosen.current = choice; ref.current?.close() }
  const where = copies.scenes.length === 1 ? `the scene “${copies.scenes[0]}”` : `${copies.scenes.length} scenes (${copies.scenes.join(', ')})`
  return <dialog ref={ref} className="image-dialog text-dialog copies-dialog" aria-labelledby="copies-title" onClose={() => onChoose(chosen.current)}>
    <div className="text-dialog-form">
      <h2 id="copies-title">{title}</h2>
      <p>{message}</p>
      <div className="check-box warning">
        <strong>Copies in saved packages</strong>
        <p>{copies.count} {copies.count === 1 ? 'copy' : 'copies'} of these photos {copies.count === 1 ? 'is' : 'are'} saved in {copies.packages} {copies.packages === 1 ? 'package' : 'packages'} in {where}: the files sent to Codex or exported for manual use.</p>
        <ul>
          <li><b>Remove copies too</b> deletes those files. The packages keep their other files, and export zips are rebuilt without them.</li>
          <li><b>Keep copies</b> leaves them in the scene’s run folders until you delete that scene.</li>
        </ul>
        <p>Results and approval records are kept either way. Packages you already downloaded are not changed.</p>
      </div>
      <div className="dialog-actions copies-actions">
        <button type="button" className="secondary" onClick={() => choose(null)}>Cancel</button>
        <span className="spacer" />
        <button type="button" className="secondary" onClick={() => choose('keep')}>Delete, keep copies</button>
        <button type="button" className="danger secondary" onClick={() => choose('remove')}>Delete and remove copies</button>
      </div>
    </div>
  </dialog>
}

const glyphs = {
  download: <><path d="M12 4v11" /><path d="M7.5 10.5L12 15l4.5-4.5" /><path d="M5 19h14" /></>,
  check: <><path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z" /><path d="M8.8 12.2l2.2 2.2 4.2-4.6" /></>,
  trash: <><path d="M4.5 7h15" /><path d="M9.5 7V4.8h5V7" /><path d="M6.5 7l.9 12.2h9.2L17.5 7" /><path d="M10.2 10.5v5.5M13.8 10.5v5.5" /></>,
  folder: <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />,
  import: <><path d="M12 15V4" /><path d="M7.5 8.5L12 4l4.5 4.5" /><path d="M5 14v5h14v-5" /></>,
  edit: <><path d="M4 20h4L19 9l-4-4L4 16z" /><path d="M13.5 6.5l4 4" /></>,
  bookmark: <path d="M7 4h10v16l-5-3.5L7 20z" />,
  compare: <><rect x="3" y="5" width="7.5" height="14" rx="1.5" /><rect x="13.5" y="5" width="7.5" height="14" rx="1.5" /></>,
}

/** Small line icon used inside compact action buttons. */
export function Glyph({ name }: { name: keyof typeof glyphs }) {
  return <svg className="inline-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">{glyphs[name]}</svg>
}
