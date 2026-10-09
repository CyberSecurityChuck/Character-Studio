import { Component, StrictMode, type ErrorInfo, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './styles.css'

class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch(_error: Error, _info: ErrorInfo) {
    // Do not log application state or private data.
  }
  render() {
    if (this.state.failed) return (
      <main className="fatal"><h1>The studio could not be displayed.</h1>
        <p>Saved work remains on this computer. Reload to try again.</p>
        <button onClick={() => location.reload()}>Reload studio</button></main>
    )
    return this.props.children
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode><ErrorBoundary><App /></ErrorBoundary></StrictMode>,
)
