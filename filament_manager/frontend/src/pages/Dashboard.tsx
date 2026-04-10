import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api } from '../api'
import type { DashboardStats, PrintJob, PrinterConfig, PrinterStatus } from '../types'
import { AlertTriangle, Printer, Zap, CheckCircle2 } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { enUS, de, es, type Locale } from 'date-fns/locale'
import { useHATZ, useCurrencyFormatter } from '../hooks/useHATZ'
import { parseUTC } from '../utils/time'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie, Legend, CartesianGrid,
} from 'recharts'

const LOCALE_MAP: Record<string, Locale> = { en: enUS, de, es }

const PIE_COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
  '#06b6d4', '#f97316', '#84cc16', '#ec4899', '#6366f1',
]

const TT_STYLE = { background: '#1c1c1e', border: '1px solid #48484a', borderRadius: 8, color: '#f5f5f7' }
const TT_LABEL = { color: '#d1d5db' }
const TT_ITEM  = { color: '#f5f5f7' }

// ── Combined inventory card ───────────────────────────────────────────────────

function InventoryCard({ stats }: { stats: DashboardStats }) {
  const { t } = useTranslation()
  const fmtCurrency = useCurrencyFormatter()

  const rows = [
    {
      label:  t('dashboard.totalPurchased'),
      spools: stats.total_spools,
      kg:     stats.total_filament_kg,
      eur:    stats.total_filament_spent_eur,
      dim:    false,
    },
    {
      label:  t('dashboard.printedSpent'),
      spools: stats.empty_spools,
      kg:     stats.total_filament_kg - stats.total_available_kg,
      eur:    stats.total_filament_spent_eur - stats.total_available_eur,
      dim:    true,
    },
    {
      label:  t('dashboard.available'),
      spools: stats.active_spools,
      kg:     stats.total_available_kg,
      eur:    stats.total_available_eur,
      est:    true,
      dim:    false,
    },
  ]

  return (
    <div className="card">
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
        {t('dashboard.inventoryGroup')}
      </p>
      <table className="w-full">
        <thead>
          <tr className="border-b border-surface-3">
            <th className="pb-2 text-left" />
            <th className="pb-2 text-right text-xs font-medium text-gray-500 pl-5 whitespace-nowrap">
              {t('dashboard.spoolsGroup')}
            </th>
            <th className="pb-2 text-right text-xs font-medium text-gray-500 pl-5 whitespace-nowrap">
              {t('dashboard.colWeight')}
            </th>
            <th className="pb-2 text-right text-xs font-medium text-gray-500 pl-5 whitespace-nowrap">
              {t('dashboard.colMoney')}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.label} className="border-b border-surface-3/40 last:border-0">
              <td className={`py-2.5 pr-4 text-sm ${r.dim ? 'text-gray-500' : 'text-gray-300'}`}>{r.label}</td>
              <td className={`py-2.5 pl-5 text-right text-sm font-semibold tabular-nums ${r.dim ? 'text-gray-500' : 'text-white'}`}>
                {r.spools}
              </td>
              <td className={`py-2.5 pl-5 text-right text-sm font-semibold tabular-nums whitespace-nowrap ${r.dim ? 'text-gray-500' : 'text-white'}`}>
                {r.kg.toFixed(2)} kg
              </td>
              <td className={`py-2.5 pl-5 text-right text-sm tabular-nums whitespace-nowrap ${r.dim ? 'text-gray-500' : 'text-gray-300'}`}>
                {fmtCurrency(r.eur)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Running job card ──────────────────────────────────────────────────────────

const LIVE_LABELS: Record<string, string> = {
  print_stage:    'Stage',
  print_progress: 'Progress',
  remaining_time: 'Remaining',
  print_weight:   'Weight',
  ams_active:     'AMS active',
  active_tray:    'Tray',
}
const LIVE_UNITS: Record<string, string> = {
  print_progress: '%',
  remaining_time: ' min',
  print_weight:   'g',
}
const LIVE_KEYS = ['print_stage', 'print_progress', 'remaining_time', 'print_weight', 'ams_active', 'active_tray'] as const

function RunningJobCard({ job, printers }: { job: PrintJob; printers: PrinterConfig[] }) {
  const { t, i18n } = useTranslation()
  const locale = LOCALE_MAP[i18n.resolvedLanguage ?? 'en'] ?? enUS
  const tz = useHATZ()
  const qc = useQueryClient()

  const printer = printers.find(p => p.name === job.printer_name) ?? null

  const { data: status } = useQuery<PrinterStatus>({
    queryKey: ['printer-status-live', printer?.id],
    queryFn: () => api.getPrinterStatus(printer!.id),
    enabled: !!printer,
    refetchInterval: 10_000,
  })

  const forceFinishMut = useMutation({
    mutationFn: () => api.updatePrint(job.id, {
      finished_at: new Date().toISOString(),
      success: true,
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboard'] }),
  })

  const handleForceFinish = () => {
    if (!window.confirm(t('dashboard.forceFinishConfirm'))) return
    forceFinishMut.mutate()
  }

  const liveEntries = status
    ? LIVE_KEYS.map(k => [k, status[k]] as [string, string | null]).filter(([, v]) => v != null && v !== '')
    : []

  return (
    <div className="card border border-blue-800/60 bg-blue-950/20">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Zap size={15} className="text-blue-400 shrink-0 mt-0.5" />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-white truncate">{job.name}</p>
            <p className="text-xs text-gray-500 mt-0.5">
              {job.printer_name && <span>{job.printer_name} · </span>}
              {t('dashboard.runningFor')} {formatDistanceToNow(parseUTC(job.started_at), { locale })}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-white border border-surface-3 hover:border-gray-500 rounded px-2 py-0.5 transition-colors disabled:opacity-50"
            onClick={handleForceFinish}
            disabled={forceFinishMut.isPending}
            title={t('dashboard.forceFinish')}
          >
            <CheckCircle2 size={12} />
            {t('dashboard.forceFinish')}
          </button>
          <span className="text-xs bg-blue-900 text-blue-300 px-2 py-0.5 rounded-full">
            {t('dashboard.runningJob')}
          </span>
        </div>
      </div>

      {liveEntries.length > 0 && (
        <div className="mt-3 pt-3 border-t border-blue-800/40 flex flex-wrap gap-x-5 gap-y-1">
          {liveEntries.map(([key, val]) => (
            <span key={key} className="text-xs text-gray-500">
              {LIVE_LABELS[key]}: <span className="text-gray-200 font-medium">{val}{LIVE_UNITS[key] ?? ''}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Recent print row ──────────────────────────────────────────────────────────

function PrintRow({ job }: { job: PrintJob }) {
  const { i18n } = useTranslation()
  const locale = LOCALE_MAP[i18n.resolvedLanguage ?? 'en'] ?? enUS
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-surface-3 last:border-0">
      <div className="min-w-0">
        <p className="text-sm font-medium text-white truncate">{job.name}</p>
        <p className="text-xs text-gray-500">
          {formatDistanceToNow(parseUTC(job.started_at), { addSuffix: true, locale })}
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

// ── Chart section ─────────────────────────────────────────────────────────────

type ChartTab = 'materials' | 'cost' | 'weight' | 'location' | 'timeline'

function ChartSection({ stats }: { stats: DashboardStats }) {
  const { t } = useTranslation()
  const [tab, setTab] = useState<ChartTab>('materials')

  const TAB_LABELS: { key: ChartTab; label: string }[] = [
    { key: 'materials', label: t('dashboard.tabs.materials') },
    { key: 'cost',      label: t('dashboard.tabs.cost') },
    { key: 'weight',    label: t('dashboard.tabs.weight') },
    { key: 'location',  label: t('dashboard.tabs.location') },
    { key: 'timeline',  label: t('dashboard.tabs.timeline') },
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
                <Legend formatter={(v, entry: any) => (
                  <span style={{ color: '#9ca3af', fontSize: 12 }}>
                    {v}{entry?.payload?.value != null ? ` (${entry.payload.value})` : ''}
                  </span>
                )} />
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

      {tab === 'timeline' && (
        stats.prints_per_day.length === 0
          ? <p className="text-sm text-gray-500">{t('dashboard.noPrints')}</p>
          : (() => {
              const data = stats.prints_per_day
              const total = data.length
              const minGap = Math.max(1, Math.floor(total / 24))
              let lastMonth = ''
              const tickFormatter = (dateStr: string, index: number) => {
                if (index % minGap !== 0) return ''
                const month = dateStr.slice(0, 7)
                if (month === lastMonth) return ''
                lastMonth = month
                const d = new Date(dateStr + 'T12:00:00Z')
                return d.toLocaleDateString(undefined, { month: 'short', year: '2-digit' })
              }
              return (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={data} barSize={total > 180 ? 2 : total > 60 ? 4 : 8} barCategoryGap={1}>
                    <CartesianGrid vertical={false} stroke="#2c2c2e" />
                    <XAxis
                      dataKey="date"
                      tick={{ fill: '#9ca3af', fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                      tickFormatter={tickFormatter}
                      interval={0}
                    />
                    <YAxis
                      tick={{ fill: '#9ca3af', fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                      allowDecimals={false}
                      width={24}
                    />
                    <Tooltip
                      contentStyle={TT_STYLE}
                      labelStyle={TT_LABEL}
                      itemStyle={TT_ITEM}
                      labelFormatter={(label: string) =>
                        new Date(label + 'T12:00:00Z').toLocaleDateString(undefined, {
                          weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
                        })
                      }
                      formatter={(v: number) => [v === 1 ? '1 print' : `${v} prints`, '']}
                      separator=""
                    />
                    <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                      {data.map((entry, i) => (
                        <Cell key={i} fill={entry.count === 0 ? '#1e293b' : '#3b82f6'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )
            })()
      )}

    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const { t } = useTranslation()

  const { data: stats, isLoading } = useQuery<DashboardStats>({
    queryKey: ['dashboard'],
    queryFn: api.getDashboard,
    refetchInterval: 30_000,
  })

  const { data: haStatus } = useQuery({
    queryKey: ['ha-status'],
    queryFn: api.getHAStatus,
    refetchInterval: 30_000,
  })

  const { data: printers = [] } = useQuery<PrinterConfig[]>({
    queryKey: ['printers'],
    queryFn: api.getPrinters,
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

      {/* Running job — only shown when a print is active */}
      {stats.running_job && (
        <RunningJobCard job={stats.running_job} printers={printers} />
      )}

      {/* Combined inventory metrics */}
      <InventoryCard stats={stats} />

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
