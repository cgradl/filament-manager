import React from 'react'
import ReactDOM from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import './index.css'
import './i18n'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
})

// ── HA theme sync ─────────────────────────────────────────────────────────────
// Reads HA's CSS variables from the parent frame and:
//  1. Applies the correct dark/light class (same logic as the inline bootstrap
//     script in index.html, but runs after React so it can react to HA theme
//     changes triggered after initial load).
//  2. Optionally maps HA's accent color to --fm-accent so the app follows the
//     user's configured HA theme color.

function hexToRgb(hex: string): string | null {
  hex = hex.replace(/^#/, '')
  if (hex.length === 3) hex = hex.split('').map(c => c + c).join('')
  if (hex.length !== 6) return null
  const r = parseInt(hex.slice(0, 2), 16)
  const g = parseInt(hex.slice(2, 4), 16)
  const b = parseInt(hex.slice(4, 6), 16)
  return `${r} ${g} ${b}`
}

function syncHATheme() {
  try {
    if (window.parent === window) return   // not inside an iframe
    const parentRoot = window.parent.document.documentElement
    const cs = window.parent.getComputedStyle(parentRoot)
    const bg = cs.getPropertyValue('--primary-background-color').trim()
    if (!bg) return

    // Determine dark/light from HA background luminance
    const hex = bg.replace(/^#/, '')
    const padded = hex.length === 3
      ? hex.split('').map(c => c + c).join('')
      : hex
    const r = parseInt(padded.slice(0, 2), 16)
    const g = parseInt(padded.slice(2, 4), 16)
    const b = parseInt(padded.slice(4, 6), 16)
    const lum = (r * 299 + g * 587 + b * 114) / 1000
    const isLight = lum >= 128

    if (isLight) {
      document.documentElement.classList.remove('dark')
    } else {
      document.documentElement.classList.add('dark')
    }

    // Mirror HA's accent / primary color into our CSS variable
    const accent = cs.getPropertyValue('--primary-color').trim()
    if (accent) {
      const rgb = hexToRgb(accent)
      if (rgb) document.documentElement.style.setProperty('--fm-accent', rgb)
    }
  } catch {
    // Cross-origin or security error — leave theme as-is
  }
}

// Run once after mount, then keep in sync with any HA theme changes.
syncHATheme()

// For standalone usage (not in HA): respect OS preference changes in real time.
const osMQ = window.matchMedia('(prefers-color-scheme: dark)')
osMQ.addEventListener('change', (e) => {
  try {
    if (window.parent !== window) return   // HA handles its own theming
  } catch { return }
  if (e.matches) {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
})

// ─────────────────────────────────────────────────────────────────────────────

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <HashRouter>
        <App />
      </HashRouter>
    </QueryClientProvider>
  </React.StrictMode>,
)
