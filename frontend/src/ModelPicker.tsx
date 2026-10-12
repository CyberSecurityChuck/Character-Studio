import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'

/** A searchable model list (Phase 6 review): a trigger showing the choice, a popover with a
 *  filter field, a "Default" entry where the engine has one, tags such as "Recommended",
 *  and an entry for a name the list does not contain. Full keyboard support. */
export type ModelOption = { value: string; tag?: string }

export function ModelPicker({ id, value, options, defaultLabel, allowCustom = true, placeholder = 'Choose a model', disabled, empty, footer, onChange }: {
  id: string; value: string; options: ModelOption[]; defaultLabel?: string; allowCustom?: boolean; placeholder?: string
  disabled?: boolean; empty?: string; footer?: ReactNode; onChange: (value: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const root = useRef<HTMLDivElement>(null)
  const search = useRef<HTMLInputElement>(null)
  const listId = useId()
  useEffect(() => {
    if (!open) return
    const press = (e: PointerEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('pointerdown', press)
    return () => document.removeEventListener('pointerdown', press)
  }, [open])
  useEffect(() => { if (open) { setQuery(''); requestAnimationFrame(() => search.current?.focus()) } }, [open])

  const text = query.trim().toLocaleLowerCase()
  const matches = options.filter(o => !text || o.value.toLocaleLowerCase().includes(text))
  // Recommended entries first, then the rest in their given order.
  matches.sort((a, b) => Number(!!b.tag) - Number(!!a.tag))
  const items: { value: string; label: string; tag?: string; custom?: boolean }[] = [
    ...(defaultLabel !== undefined && !text ? [{ value: '', label: defaultLabel }] : []),
    ...matches.map(o => ({ value: o.value, label: o.value, tag: o.tag })),
    ...(allowCustom && text && !options.some(o => o.value.toLocaleLowerCase() === text) ? [{ value: query.trim(), label: `Use “${query.trim()}”`, custom: true }] : []),
  ]
  const choose = (next: string) => { onChange(next); setOpen(false); document.getElementById(id)?.focus() }
  function key(e: KeyboardEvent) {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => Math.min(items.length - 1, a + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => Math.max(0, a - 1)) }
    else if (e.key === 'Enter') { e.preventDefault(); if (items[active]) choose(items[active].value) }
    else if (e.key === 'Escape') { e.preventDefault(); setOpen(false); document.getElementById(id)?.focus() }
  }
  const current = options.find(o => o.value === value)
  return <div className="model-picker" ref={root}>
    <button id={id} type="button" className="model-trigger" disabled={disabled} aria-haspopup="listbox" aria-expanded={open}
      onClick={() => { setActive(0); setOpen(o => !o) }} onKeyDown={e => { if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true) } }}>
      <span className={value || defaultLabel !== undefined ? '' : 'placeholder'}>{value || defaultLabel || placeholder}</span>
      {current?.tag && <span className="model-tag">{current.tag}</span>}
      <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M7 10l5 5 5-5" /></svg>
    </button>
    {open && <div className="model-pop">
      <input ref={search} type="search" className="model-search" placeholder={allowCustom ? 'Search or type a model name' : 'Search models'} value={query} spellCheck={false}
        role="combobox" aria-expanded="true" aria-controls={listId} aria-activedescendant={items[active] ? `${listId}-${active}` : undefined}
        onChange={e => { setQuery(e.target.value); setActive(0) }} onKeyDown={key} />
      <ul id={listId} role="listbox" aria-label="Models" className="model-list">
        {items.map((item, index) => <li key={`${item.custom ? 'custom:' : ''}${item.value}`} id={`${listId}-${index}`} role="option" aria-selected={item.value === value && !item.custom}
          className={`${index === active ? 'active' : ''} ${item.value === value && !item.custom ? 'chosen' : ''} ${item.custom ? 'custom' : ''}`}
          onMouseEnter={() => setActive(index)} onMouseDown={e => e.preventDefault()} onClick={() => choose(item.value)}>
          <span>{item.label}</span>{item.tag && <span className="model-tag">{item.tag}</span>}
          {item.value === value && !item.custom && <svg className="model-check" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>}
        </li>)}
        {!items.length && <li className="model-empty" role="presentation">{empty ?? 'No matching models.'}</li>}
      </ul>
      {footer && <div className="model-foot">{footer}</div>}
    </div>}
  </div>
}
