import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import type { DashboardStats, PrintJob } from '../types'
import { AlertTriangle, Printer } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie, Legend,
} from 'recharts'

// ── Palette for pie chart ─────────────────────────────────────────────────────
const PIE_COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
  '#06b6d4', '#f97316', '#84cc16', '#ec4899', '#6366f1',
]

// ── Metric group ──────────────────────────────────────────────────────────────
function MetricGroup({
  title,
  rows,
}: {
  title: string
  rows: { label: string; value: string; sub?: string; dim?: boolean }[]
}) {
  return (
    <div className="card space-y-3">
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">{title}</p>
      {rows.map(r => (
        <div key={r.label} className="flex items-baseline justify-between">
          <span className={`text-sm ${r.dim ? 'text-gray-500' : 'text-gray-300'}`}>{r.label}</span>
          <div className="text-right">
            <span className={`text-lg font-bold ${r.dim ? 'text-gray-500' : 'text-white'}`}>{r.value}</span>
            {r.sub && <span className="text-xs text-gray-500 ml-1.5">{r.sub}</span>}
          </div>
        </div>
      ))}
    </div>
  )
}

function PrintRow({ job }: { job: PrintJob }) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-surface-3 last:border-0">
      <div className="min-w-0">
        <p className="text-sm font-medium text-white truncate">{job.name}</p>
        <p className="text-xs text-gray-500">
          {formatDistanceToNow(new Date(job.started_at), { addSuffix: true })}
          {job.printer_name && ` · ${job.printer_name}`}
        </p>
      </div>
      <div className="text-right shrink-0 ml-4">
        <p className="text-sm text-white">{(job.total_grams / 1000).toFixed(3)} kg</p>
        {job.total_cost > 0 && (
          <p className="text-xs text-gray-400">€{job.total_cost.toFixed(2)}</p>
        )}
      </div>
    </div>
  )
}

// ── Tooltip style shared across charts ───────────────────────────────────────
const TT_STYLE = { background: '#2c2c2e', border: '1px solid #3a3a3c', borderRadius: 8 }

// ── Tabbed chart section ──────────────────────────────────────────────────────
type ChartTab = 'materials' | 'cost' | 'weight' | 'location'

const TAB_LABELS: { key: ChartTab; label: string }[] = [
  { key: 'materials', label: 'Materials' },
  { key: 'cost',      label: 'Cost (€)' },
  { key: 'weight',    label: 'Filament (kg)' },
  { key: 'location',  label: 'Avg Price / Location' },
]

function ChartSection({ stats }: { stats: DashboardStats }) {
  const [tab, setTab] = useState<ChartTab>('materials')

  const pieData = stats.material_breakdown.map((m, i) => ({
    name: m.material,
    value: m.count,
    kg: m.current_kg,
    color: PIE_COLORS[i % PIE_COLORS.length],
  }))

  const costData = [
    { name: 'Purchased', value: stats.total_filament_spent_eur },
    { name: 'Printed',   value: +(stats.total_filament_spent_eur - stats.total_available_eur).toFixed(2) },
    { name: 'Available', value: stats.total_available_eur },
  ]

  const weightData = [
    { name: 'Purchased', value: stats.total_filament_kg },
    { name: 'Printed',   value: +(stats.total_filament_kg - stats.total_available_kg).toFixed(3) },
    { name: 'Available', value: stats.total_available_kg },
  ]

  const locationData = stats.price_by_location.map((l, i) => ({
    name: l.location,
    avg: l.avg_price,
    count: l.count,
    color: PIE_COLORS[i % PIE_COLORS.length],
  }))

  return (
    <div className="card">
      {/* Tab bar */}
      <div className="flex gap-1 mb-4 border-b border-surface-3 pb-3 flex-wrap">
        {TAB_LABELS.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-3 py-1 text-xs rounded-lg transition-colors ${
              tab === t.key
                ? 'bg-accent text-white'
                : 'text-gray-400 hover:text-white hover:bg-surface-3'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Materials pie */}
      {tab === 'materials' && (
        pieData.length === 0
          ? <p className="text-sm text-gray-500">No spools yet.</p>
          : <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={90}
                  label={({ name, value }) => `${name} (${value})`}
                  labelLine={false}
                >
                  {pieData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                </Pie>
                <Tooltip
                  contentStyle={TT_STYLE}
                  formatter={(value: number, name: string, props) => [
                    `${value} spools · ${props.payload.kg.toFixed(2)} kg`, name,
                  ]}
                />
                <Legend formatter={(v) => <span style={{ color: '#9ca3af', fontSize: 12 }}>{v}</span>} />
              </PieChart>
            </ResponsiveContainer>
      )}

      {/* Cost bar */}
      {tab === 'cost' && (
        stats.total_filament_spent_eur === 0
          ? <p className="text-sm text-gray-500">No purchase data yet.</p>
          : <ResponsiveContainer width="100%" height={240}>
              <BarChart data={costData} barSize={48}>
                <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={TT_STYLE} formatter={(v: number) => [`€${v.toFixed(2)}`, '']} />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  <Cell fill="#3b82f6" />
                  <Cell fill="#ef4444" />
                  <Cell fill="#10b981" />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
      )}

      {/* Filament weight bar */}
      {tab === 'weight' && (
        stats.total_filament_kg === 0
          ? <p className="text-sm text-gray-500">No filament data yet.</p>
          : <ResponsiveContainer width="100%" height={240}>
              <BarChart data={weightData} barSize={48}>
                <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={TT_STYLE} formatter={(v: number) => [`${v.toFixed(3)} kg`, '']} />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  <Cell fill="#3b82f6" />
                  <Cell fill="#ef4444" />
                  <Cell fill="#10b981" />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
      )}

      {/* Avg price by location */}
      {tab === 'location' && (
        locationData.length === 0
          ? <p className="text-sm text-gray-500">No spools with both a purchase location and price set yet.</p>
          : <ResponsiveContainer width="100%" height={240}>
              <BarChart data={locationData} barSize={40}>
                <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} axisLine={false} tickLine={false} unit="€" />
                <Tooltip
                  contentStyle={TT_STYLE}
                  formatter={(v: number, _: string, props) => [
                    `€${v.toFixed(2)} avg (${props.payload.count} spool${props.payload.count !== 1 ? 's' : ''})`,
                    'Avg price',
                  ]}
                />
                <Bar dataKey="avg" radius={[4, 4, 0, 0]}>
                  {locationData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
      )}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const { data: stats, isLoading } = useQuery<DashboardStats>({
    queryKey: ['dashboard'],
    queryFn: api.getDashboard,
    refetchInterval: 60_000,
  })

  const { data: haStatus } = useQuery({
    queryKey: ['ha-status'],
    queryFn: api.getHAStatus,
    refetchInterval: 30_000,
  })

  if (isLoading) return <div className="text-gray-500 text-sm">Loading…</div>
  if (!stats) return null

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold">Dashboard</h2>
        <span className={`text-xs px-2 py-0.5 rounded-full ${
          haStatus?.ha_available ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'
        }`}>
          HA {haStatus?.ha_available ? 'connected' : 'offline'}
        </span>
      </div>

      {/* Metric groups */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 w-full">
        <MetricGroup
          title="Cost (€)"
          rows={[
            { label: 'Total purchased', value: `€${stats.total_filament_spent_eur.toFixed(2)}` },
            { label: 'Printed / spent', value: `€${(stats.total_filament_spent_eur - stats.total_available_eur).toFixed(2)}`, dim: true },
            { label: 'Available',       value: `€${stats.total_available_eur.toFixed(2)}`, sub: 'est.' },
          ]}
        />
        <MetricGroup
          title="Filament (kg)"
          rows={[
            { label: 'Total purchased', value: `${stats.total_filament_kg.toFixed(2)} kg` },
            { label: 'Printed / spent', value: `${(stats.total_filament_kg - stats.total_available_kg).toFixed(2)} kg`, dim: true },
            { label: 'Available',       value: `${stats.total_available_kg.toFixed(2)} kg` },
          ]}
        />
        <MetricGroup
          title="Spools"
          rows={[
            { label: 'Total spools',  value: stats.total_spools.toString(), sub: `${stats.active_spools} active` },
            { label: 'Low stock',     value: stats.low_stock_spools.toString(), dim: stats.low_stock_spools === 0 },
            { label: 'Total prints',  value: stats.total_prints.toString(), sub: `${stats.total_prints} jobs` },
          ]}
        />
      </div>

      {/* Tabbed charts */}
      <ChartSection stats={stats} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Recent Prints */}
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
            <Printer size={14} /> Recent Prints
          </h3>
          {stats.recent_prints.length === 0 ? (
            <p className="text-gray-500 text-sm">No prints logged yet.</p>
          ) : (
            stats.recent_prints.map(job => <PrintRow key={job.id} job={job} />)
          )}
        </div>

        {/* Low Stock */}
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
            <AlertTriangle size={14} className="text-yellow-400" /> Low Stock Alerts
          </h3>
          {stats.low_stock.length === 0 ? (
            <p className="text-gray-500 text-sm">All spools well stocked.</p>
          ) : (
            stats.low_stock.map(spool => (
              <div key={spool.id} className="flex items-center gap-3 py-2 border-b border-surface-3 last:border-0">
                <span className="w-3 h-3 rounded-full shrink-0" style={{ background: spool.color_hex }} />
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-white truncate">
                    {spool.brand} {spool.material}{spool.subtype ? ` ${spool.subtype}` : ''} — {spool.color_name}
                  </p>
                  <div className="mt-1 h-1.5 rounded-full bg-surface-3 overflow-hidden">
                    <div className="h-full rounded-full bg-yellow-500" style={{ width: `${spool.remaining_pct}%` }} />
                  </div>
                </div>
                <span className="text-sm text-yellow-400 shrink-0">{spool.remaining_pct}%</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
