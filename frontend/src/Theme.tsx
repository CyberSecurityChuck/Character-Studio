import { useEffect, useState } from 'react'

// Light, Warm darkroom or follow Windows (D033). A display preference of this browser, so it is
// kept in localStorage; the studio's data never depends on it.
export type ThemeChoice = 'light' | 'dark' | 'system'
const KEY = 'character-studio.theme'
const systemDark = () => window.matchMedia('(prefers-color-scheme: dark)')

export function storedTheme(): ThemeChoice {
  try {
    const value = localStorage.getItem(KEY)
    return value === 'light' || value === 'dark' ? value : 'system'
  } catch { return 'system' }
}

export function applyTheme(choice: ThemeChoice) {
  const dark = choice === 'dark' || (choice === 'system' && systemDark().matches)
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
}

const options: { id: ThemeChoice; label: string; icon: React.ReactNode }[] = [
  { id: 'light', label: 'Light', icon: <><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2.2M12 19.3v2.2M4.6 4.6l1.6 1.6M17.8 17.8l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.6 19.4l1.6-1.6M17.8 6.2l1.6-1.6" /></> },
  { id: 'dark', label: 'Dark', icon: <path d="M19.5 14.6A7.8 7.8 0 0 1 9.4 4.5a7.8 7.8 0 1 0 10.1 10.1z" /> },
  { id: 'system', label: 'System', icon: <><rect x="3.5" y="4.5" width="17" height="11.5" rx="2" /><path d="M9 20h6M12 16v4" /></> },
]

/** Light · Dark · System switch for the top bar; System follows Windows as it changes. */
export function ThemeSwitch() {
  const [choice, setChoice] = useState<ThemeChoice>(storedTheme)
  useEffect(() => {
    applyTheme(choice)
    try { if (choice === 'system') localStorage.removeItem(KEY); else localStorage.setItem(KEY, choice) } catch { /* private window: the choice lasts for this visit */ }
    if (choice !== 'system') return
    const media = systemDark()
    const follow = () => applyTheme('system')
    media.addEventListener('change', follow)
    return () => media.removeEventListener('change', follow)
  }, [choice])
  return <div className="theme-switch" role="radiogroup" aria-label="Theme">
    {options.map(o => <button key={o.id} type="button" role="radio" aria-checked={choice === o.id} title={o.label} aria-label={`${o.label} theme`} className={choice === o.id ? 'on' : ''} onClick={() => setChoice(o.id)}>
      <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{o.icon}</svg>
    </button>)}
  </div>
}
