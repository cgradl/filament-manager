import { useState, useEffect } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Layers, Printer, Settings,
  ChevronLeft, ChevronRight, Menu, X,
} from 'lucide-react'

function AppIcon({ size = 24 }: { size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor">
      <path d="M20 6h-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h3v2a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1v-2h3a1 1 0 0 0 1-1V8a2 2 0 0 0-2-2M10 4h4v2h-4zm-2 16v-5h8v5zm10-7H6v-1h12zm0-3H6V8h12z" />
    </svg>
  )
}

const nav = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/spools',    icon: Layers,          label: 'Spools' },
  { to: '/prints',    icon: Printer,         label: 'Prints' },
  { to: '/settings',  icon: Settings,        label: 'Settings' },
]

function NavItems({ collapsed, onClick }: { collapsed?: boolean; onClick?: () => void }) {
  return (
    <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto">
      {nav.map(({ to, icon: Icon, label }) => (
        <NavLink
          key={to}
          to={to}
          onClick={onClick}
          title={collapsed ? label : undefined}
          className={({ isActive }) =>
            `flex items-center gap-3 rounded-lg text-sm transition-colors
             ${collapsed ? 'justify-center px-2 py-2.5' : 'px-3 py-2.5'}
             ${isActive
               ? 'bg-accent text-white'
               : 'text-gray-400 hover:text-white hover:bg-surface-3'
             }`
          }
        >
          <Icon size={16} className="shrink-0" />
          {!collapsed && <span>{label}</span>}
        </NavLink>
      ))}
    </nav>
  )
}

export default function Layout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const location = useLocation()

  // Close drawer on route change
  useEffect(() => {
    setDrawerOpen(false)
  }, [location.pathname])

  return (
    <div className="flex h-screen overflow-hidden bg-surface text-gray-100">

      {/* ── Desktop sidebar (≥768px) ─────────────────────────────────────────── */}
      <aside
        style={{ width: collapsed ? 56 : 208 }}
        className="hidden md:flex flex-col shrink-0 bg-surface-2 border-r border-surface-3 transition-all duration-200"
      >
        {/* Logo */}
        <div className={`border-b border-surface-3 py-4 flex items-center
                         ${collapsed ? 'justify-center px-2' : 'px-4 gap-2'}`}>
          {collapsed ? (
            <span className="text-accent" title="Filament Manager">
              <AppIcon size={22} />
            </span>
          ) : (
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <span className="text-accent shrink-0"><AppIcon size={20} /></span>
              <div className="min-w-0">
                <p className="text-sm font-bold text-white leading-tight truncate">Filament Manager</p>
                <p className="text-xs text-gray-500">3D Print Tracker</p>
              </div>
            </div>
          )}
        </div>

        <NavItems collapsed={collapsed} />

        {/* Collapse toggle */}
        <button
          className="flex items-center justify-center py-3 border-t border-surface-3
                     text-gray-500 hover:text-white hover:bg-surface-3 transition-colors shrink-0"
          onClick={() => setCollapsed(c => !c)}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </aside>

      {/* ── Mobile overlay + drawer (<768px) ─────────────────────────────────── */}
      {drawerOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40 bg-black/60"
            onClick={() => setDrawerOpen(false)}
          />

          {/* Drawer panel */}
          <aside className="fixed inset-y-0 left-0 z-50 flex flex-col w-64
                            bg-surface-2 border-r border-surface-3 shadow-xl">
            {/* Drawer header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-surface-3 shrink-0">
              <div className="flex items-center gap-2">
                <span className="text-accent shrink-0"><AppIcon size={20} /></span>
                <div>
                  <p className="text-sm font-bold text-white leading-tight">Filament Manager</p>
                  <p className="text-xs text-gray-500">3D Print Tracker</p>
                </div>
              </div>
              <button
                className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-surface-3 transition-colors"
                onClick={() => setDrawerOpen(false)}
              >
                <X size={18} />
              </button>
            </div>

            <NavItems onClick={() => setDrawerOpen(false)} />
          </aside>
        </>
      )}

      {/* ── Main content area ────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {/* Mobile top bar */}
        <header className="flex items-center gap-3 px-4 py-3
                           bg-surface-2 border-b border-surface-3 shrink-0 md:hidden">
          <button
            className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-surface-3 transition-colors"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open menu"
          >
            <Menu size={20} />
          </button>
          <p className="text-sm font-bold text-white">Filament Manager</p>
        </header>

        <main className="flex-1 overflow-y-auto p-4 md:p-6">
          {children}
        </main>
      </div>
    </div>
  )
}
