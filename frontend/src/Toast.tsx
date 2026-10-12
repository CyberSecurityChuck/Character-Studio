import { useEffect, useRef, useState } from 'react'

/** Success messages (Phase 6C/6D review): a toast in the top-right corner plus, where the
 *  message is shown in a panel, a green inline banner. Problems stay next to their field. */
type Tone = 'success' | 'info'
type Toast = { id: number; title: string; detail: string; tone: Tone }

const LIFETIME = 5000
const MAX_VISIBLE = 3
let toasts: Toast[] = []
let nextId = 1
const listeners = new Set<(items: Toast[]) => void>()
const publish = () => listeners.forEach(listener => listener(toasts))

/** "Key works. 23 models available." → title "Key works", detail "23 models available." */
function split(text: string): [string, string] {
  const match = text.match(/^(.+?[.!?])\s+(.+)$/s)
  if (!match) return [text.replace(/\.$/, ''), '']
  return [match[1].replace(/\.$/, ''), match[2]]
}

export function notify(text: string, tone: Tone = 'success') {
  const [title, detail] = split(text.trim())
  if (!title) return
  toasts = [...toasts.filter(t => t.title !== title || t.detail !== detail), { id: nextId++, title, detail, tone }].slice(-MAX_VISIBLE)
  publish()
}

function dismiss(id: number) {
  toasts = toasts.filter(t => t.id !== id)
  publish()
}

/** Messages that report work in progress or a failed copy are not successes. */
export function toneOf(text: string): Tone | 'progress' {
  if (/…$/.test(text.trim())) return 'progress'
  if (/^(copy failed|nothing|no saved image)/i.test(text.trim())) return 'info'
  return 'success'
}

function ToastCard({ toast }: { toast: Toast }) {
  const timer = useRef<number | undefined>(undefined)
  const start = () => { timer.current = window.setTimeout(() => dismiss(toast.id), LIFETIME) }
  const stop = () => window.clearTimeout(timer.current)
  useEffect(() => { start(); return stop }, []) // eslint-disable-line react-hooks/exhaustive-deps
  return <div className={`toast ${toast.tone}`} onMouseEnter={stop} onMouseLeave={start} onFocus={stop} onBlur={start}>
    <span className="toast-icon" aria-hidden="true">{toast.tone === 'success'
      ? <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M5.5 12.5l4.2 4.2 8.8-9.4" /></svg>
      : <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M12 8v.01M12 11.5v5" /></svg>}</span>
    <div className="toast-copy"><strong>{toast.title}</strong>{toast.detail && <span>{toast.detail}</span>}</div>
    <button type="button" className="toast-close" aria-label="Close notification" onClick={() => dismiss(toast.id)}>×</button>
  </div>
}

/** Rendered once in the app shell. */
export function Toaster() {
  const [items, setItems] = useState<Toast[]>(toasts)
  useEffect(() => { listeners.add(setItems); return () => { listeners.delete(setItems) } }, [])
  // The inline status lines already announce messages; the toasts are the visual echo.
  return <div className="toast-stack" aria-live="off">{items.map(t => <ToastCard key={t.id} toast={t} />)}</div>
}

/** The inline status line of a panel or page: successes become a green banner and also
 *  appear as a toast; progress and neutral notes stay as quiet text. */
export function StatusNote({ text, className = '' }: { text: string; className?: string }) {
  const tone = text ? toneOf(text) : 'progress'
  useEffect(() => { if (text && tone !== 'progress') notify(text, tone) }, [text]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!text) return <p className={`status-note ${className}`} role="status" />
  return <p className={`status-note ${tone} ${className}`} role="status">
    {tone === 'success' && <svg className="status-check" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M5.5 12.5l4.2 4.2 8.8-9.4" /></svg>}
    <span>{text}</span></p>
}
