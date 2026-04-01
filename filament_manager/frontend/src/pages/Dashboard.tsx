import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api } from '../api'
import type { DashboardStats, PrintJob } from '../types'
import { AlertTriangle, Printer } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { enUS, de, es, type Locale } from 'date-fns/locale'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie, Legend,
} from 'recharts'

const LOCALE_MAP: Record<string, Locale> = { en: enUS, de, es }

const PIE_COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
  '#06b6d4', '#f97316', '#84cc16', '#ec4899', '#6366f1',
]

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
  const { i18n } = useTranslation()
  const locale = LOCALE_MAP[i18n.resolvedLanguage ?? 'en'] ?? enUS
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-surface-3 last:border-0">
      <div className="min-w-0">
        <p className="text-sm font-medium text-white truncate">{job.name}</p>
        <p className="text-xs text-gray-500">
          {formatDistanceToNow(new Date(job.started_at), { addSuffix: true, locale })}
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

const TT_STYLE = { background: '#1c1c1e', border: '1px solid #48484a', borderRadius: 8, color: '#f5f5f7' }
const TT_LABEL = { color: '#d1d5db' }
const TT_ITEM  = { color: '#f5f5f7' }

type ChartTab = 'materials' | 'cost' | 'weight' | 'location'

function ChartSection({ stats }: { stats: DashboardStats }) {
  const { t } = useTranslation()
  const [tab, setTab] = useState<ChartTab>('materials')

  const TAB_LABELS: { key: ChartTab; label: string }[] = [
    { key: 'materials', label: t('dashboard.tabs.materials') },
    { key: 'cost',      label: t('dashboard.tabs.cost') },
    { key: 'weight',    label: t('dashboard.tabs.weight') },
    { key: 'location',  label: t('dashboard.tabs.location') },
  ]

  const pieData = stats.material_breakdown.map((m, i) => ({
    name: m.material,
    value: m.count,
    kg: m.current_kg,
    color: PIE_COLORS[i % PIE_COLORS.length],
  }))

  const costData = [
    { name: t('dashboard.chart.purchased'), value: stats.total_filament_spent_eur },
    { name: t('dashboard.chart.printed'),   value: +(stats.total_filament_spent_eur - stats.total_available_eur).toFixed(2) },
    { name: t('dashboard.chart.available'), value: stats.total_available_eur },
  ]

  const weightData = [
    { name: t('dashboard.chart.purchased'), value: stats.total_filament_kg },
    { name: t('dashboard.chart.printed'),   value: +(stats.total_filament_kg - stats.total_available_kg).toFixed(3) },
    { name: t('dashboard.chart.available'), value: stats.total_available_kg },
  ]

  const locationData = stats.price_by_location.map((l, i) => ({
    name: l.location,
    avg: l.avg_price,
    count: l.count,
    color: PIE_COLORS[i % PIE_COLORS.length],
  }))

  return (
    <div className="card">
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

      {tab === 'materials' && (
        pieData.length === 0
          ? <p className="text-sm text-gray-500">{t('dashboard.noSpools')}</p>
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
                  labelStyle={TT_LABEL}
                  itemStyle={TT_ITEM}
                  formatter={(value: number, name: string, props) => [
                    `${value} ${value === 1 ? t('dashboard.chart.spool') : t('dashboard.chart.spools')} · ${props.payload.kg.toFixed(2)} kg`, name,
                  ]}
                />
                <Legend formatter={(v) => <span style={{ color: '#9ca3af', fontSize: 12 }}>{v}</span>} />
              </PieChart>
            </ResponsiveContainer>
      )}

      {tab === 'cost' && (
        stats.total_filament_spent_eur === 0
          ? <p className="text-sm text-gray-500">{t('dashboard.noPurchaseData')}</p>
          : <ResponsiveContainer width="100%" height={240}>
              <BarChart data={costData} barSize={48}>
                <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={TT_STYLE} labelStyle={TT_LABEL} itemStyle={TT_ITEM} separator="" formatter={(v: number) => [`€${v.toFixed(2)}`, '']} />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  <Cell fill="#3b82f6" />
                  <Cell fill="#ef4444" />
                  <Cell fill="#10b981" />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
      )}

      {tab === 'weight' && (
        stats.total_filament_kg === 0
          ? <p className="text-sm text-gray-500">{t('dashboard.noFilamentData')}</p>
          : <ResponsiveContainer width="100%" height={240}>
              <BarChart data={weightData} barSize={48}>
                <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={TT_STYLE} labelStyle={TT_LABEL} itemStyle={TT_ITEM} separator="" formatter={(v: number) => [`${v.toFixed(3)} kg`, '']} />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  <Cell fill="#3b82f6" />
                  <Cell fill="#ef4444" />
                  <Cell fill="#10b981" />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
      )}

      {tab === 'location' && (
        locationData.length === 0
          ? <p className="text-sm text-gray-500">{t('dashboard.noLocationData')}</p>
          : <ResponsiveContainer width="100%" height={240}>
              <BarChart data={locationData} barSize={40}>
                <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} axisLine={false} tickLine={false} unit="€" />
                <Tooltip
                  contentStyle={TT_STYLE}
                  labelStyle={TT_LABEL}
                  itemStyle={TT_ITEM}
                  formatter={(v: number, _: string, props) => [
                    `€${v.toFixed(2)} avg (${props.payload.count} ${props.payload.count !== 1 ? t('dashboard.chart.spools') : t('dashboard.chart.spool')})`,
                    t('dashboard.chart.avgPrice'),
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

export default function Dashboard() {
  const { t } = useTranslation()

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

  if (isLoading) return <div className="text-gray-500 text-sm">{t('common.loading')}</div>
  if (!stats) return null

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold">{t('dashboard.title')}</h2>
        <span className={`text-xs px-2 py-0.5 rounded-full ${
          haStatus?.ha_available ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'
        }`}>
          {haStatus?.ha_available ? t('dashboard.haConnected') : t('dashboard.haOffline')}
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 w-full">
        <MetricGroup
          title={t('dashboard.costGroup')}
          rows={[
            { label: t('dashboard.totalPurchased'), value: `€${stats.total_filament_spent_eur.toFixed(2)}` },
            { label: t('dashboard.printedSpent'),   value: `€${(stats.total_filament_spent_eur - stats.total_available_eur).toFixed(2)}`, dim: true },
            { label: t('dashboard.available'),      value: `€${stats.total_available_eur.toFixed(2)}`, sub: t('common.est') },
          ]}
        />
        <MetricGroup
          title={t('dashboard.filamentGroup')}
          rows={[
            { label: t('dashboard.totalPurchased'), value: `${stats.total_filament_kg.toFixed(2)} kg` },
            { label: t('dashboard.printedSpent'),   value: `${(stats.total_filament_kg - stats.total_available_kg).toFixed(2)} kg`, dim: true },
            { label: t('dashboard.available'),      value: `${stats.total_available_kg.toFixed(2)} kg` },
          ]}
        />
        <MetricGroup
          title={t('dashboard.spoolsGroup')}
          rows={[
            { label: t('dashboard.totalSpools'), value: stats.total_spools.toString(), sub: `${stats.active_spools} ${t('common.active')}` },
            { label: t('dashboard.lowStock'),    value: stats.low_stock_spools.toString(), dim: stats.low_stock_spools === 0 },
            { label: t('dashboard.totalPrints'), value: stats.total_prints.toString() },
          ]}
        />
      </div>

      <ChartSection stats={stats} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
            <Printer size={14} /> {t('dashboard.recentPrints')}
          </h3>
          {stats.recent_prints.length === 0 ? (
            <p className="text-gray-500 text-sm">{t('dashboard.noPrints')}</p>
          ) : (
            stats.recent_prints.map(job => <PrintRow key={job.id} job={job} />)
          )}
        </div>

        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
            <AlertTriangle size={14} className="text-yellow-400" /> {t('dashboard.lowStockAlerts')}
          </h3>
          {stats.low_stock.length === 0 ? (
            <p className="text-gray-500 text-sm">{t('dashboard.allWellStocked')}</p>
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
