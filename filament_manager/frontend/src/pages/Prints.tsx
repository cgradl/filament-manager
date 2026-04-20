import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api } from '../api'
import type { PrintJob, Spool, AMSTray, PrinterConfig, SuggestedUsage, PrinterStatus, Project } from '../types'
import { Plus, Pencil, Trash2, X, CheckCircle, XCircle, Zap, Scale, FileText, Download, Search, CalendarDays, FolderOpen } from 'lucide-react'
import Modal from '../components/Modal'
import { useHATZ } from '../hooks/useHATZ'
import { formatDateTimeTZ, nowInTZ, utcToLocalInput, localInputToUTC } from '../utils/time'

const PAGE_SIZE = 50

// ── Date filter helpers ───────────────────────────────────────────────────────

type FilterMode = 'month' | 'week' | 'day'

interface DateFilter {
  mode: FilterMode
  preset: 'this' | 'last' | 'custom'
  custom: string  // YYYY-MM for month; YYYY-MM-DD for week/day
}

function addDays(dateStr: string, n: number): string {
  const d = new Date(dateStr + 'T12:00:00Z')
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}

function getMondayOf(dateStr: string): string {
  const d = new Date(dateStr + 'T12:00:00Z')
  const delta = (d.getUTCDay() + 6) % 7   // Mon=0 … Sun=6
  return addDays(dateStr, -delta)
}

/** Return the default date/month string for a mode+preset combination. */
function presetToCustom(mode: FilterMode, preset: 'this' | 'last', today: string): string {
  if (mode === 'month') {
    if (preset === 'this') return today.slice(0, 7)
    const d = new Date(today + 'T12:00:00Z')
    d.setUTCDate(1)
    d.setUTCMonth(d.getUTCMonth() - 1)
    return d.toISOString().slice(0, 7)
  }
  if (mode === 'week') {
    const ref = preset === 'this' ? today : addDays(today, -7)
    return getMondayOf(ref)
  }
  return preset === 'this' ? today : addDays(today, -1)
}

/** Format "YYYY-MM-DD" as "DD.MM." for compact range labels. */
function fmtShort(dateStr: string): string {
  const [, m, d] = dateStr.split('-')
  return `${d}.${m}.`
}

function resolveDateRange(f: DateFilter, today: string): { start: string; end: string } | null {
  const { mode, preset, custom } = f
  if (mode === 'month') {
    let ym: string
    if (preset === 'this') {
      ym = today.slice(0, 7)
    } else if (preset === 'last') {
      const d = new Date(today + 'T12:00:00Z')
      d.setUTCDate(1)
      d.setUTCMonth(d.getUTCMonth() - 1)
      ym = d.toISOString().slice(0, 7)
    } else {
      if (!custom) return null
      ym = custom
    }
    const [y, m] = ym.split('-').map(Number)
    const lastDay = new Date(Date.UTC(y, m, 0)).getUTCDate()
    return { start: `${ym}-01`, end: `${ym}-${String(lastDay).padStart(2, '0')}` }
  }
  if (mode === 'week') {
    const ref = preset === 'this' ? today : preset === 'last' ? addDays(today, -7) : custom
    if (!ref) return null
    const mon = getMondayOf(ref)
    return { start: mon, end: addDays(mon, 6) }
  }
  if (mode === 'day') {
    const day = preset === 'this' ? today : preset === 'last' ? addDays(today, -1) : custom
    if (!day) return null
    return { start: day, end: day }
  }
  return null
}

// ── Print Form ────────────────────────────────────────────────────────────────

interface UsageRow { spool_id: number; grams_used: number; ams_slot: string }

function PrintForm({
  initial,
  spools,
  onSave,
  onCancel,
}: {
  initial?: PrintJob
  spools: Spool[]
  onSave: (data: unknown) => void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  const tz = useHATZ()
  const now = nowInTZ(tz)
  const [name, setName] = useState(initial?.name ?? '')
  const [modelName, setModelName] = useState(initial?.model_name ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [startedAt, setStartedAt] = useState(
    initial?.started_at ? utcToLocalInput(initial.started_at, tz) : now
  )
  const [finishedAt, setFinishedAt] = useState(
    initial?.finished_at ? utcToLocalInput(initial.finished_at, tz) : ''
  )
  const [durationH, setDurationH] = useState(
    initial?.duration_hours?.toString() ?? ''
  )
  const [success, setSuccess] = useState(initial?.success ?? true)
  const [printerId, setPrinterId] = useState<number | ''>('')
  const [notes, setNotes] = useState(initial?.notes ?? '')
  const [usages, setUsages] = useState<UsageRow[]>(() => {
    // Confirmed usages take priority
    if (initial?.usages && initial.usages.length > 0) {
      return initial.usages.map(u => ({
        spool_id: u.spool_id,
        grams_used: u.grams_used,
        ams_slot: u.ams_slot ?? '',
      }))
    }
    // Unconfirmed auto print: pre-populate from the cloud snapshot so the edit
    // form shows the print-time spool, not whatever is in the slot right now.
    if (initial?.suggested_usages && initial.suggested_usages.length > 0) {
      return initial.suggested_usages
        .filter(s => s.spool_id != null)
        .map(s => ({ spool_id: s.spool_id!, grams_used: s.grams, ams_slot: s.ams_slot }))
    }
    return []
  })
  const [loadingAMS, setLoadingAMS] = useState(false)
  const [showEmptySpools, setShowEmptySpools] = useState(false)
  const [deductWeight, setDeductWeight] = useState(true)
  // For existing jobs usages start read-only; new jobs go straight to edit mode
  const [usageEditMode, setUsageEditMode] = useState(!initial)
  const [fmProjectId, setFmProjectId] = useState<number | ''>(initial?.fm_project_id ?? '')

  const { data: printers = [] } = useQuery<PrinterConfig[]>({
    queryKey: ['printers'],
    queryFn: api.getPrinters,
  })

  const { data: projects = [] } = useQuery<Project[]>({
    queryKey: ['projects'],
    queryFn: api.getProjects,
  })

  useEffect(() => {
    if (initial?.printer_name && printers.length > 0) {
      const match = printers.find(p => p.name === initial.printer_name)
      if (match) setPrinterId(match.id)
    }
  }, [printers, initial?.printer_name])

  const selectedPrinter = printers.find(p => p.id === printerId) ?? null

  // Spools visible in dropdowns: non-empty always shown; empty only when checkbox is on.
  // Always include spools already selected in a usage row so existing rows don't go blank.
  const selectedSpoolIds = new Set(usages.map(u => u.spool_id))
  const visibleSpools = spools.filter(
    s => showEmptySpools || Math.round(s.remaining_pct) > 0 || selectedSpoolIds.has(s.id)
  )

  // Auto-load AMS on first open when printer is known and no usages are set yet.
  // Only for new prints — never overwrite stored usages on an existing job.
  useEffect(() => {
    if (initial) return             // editing existing job — never auto-load
    if (!printerId) return
    if (usages.length > 0) return  // already has data — don't overwrite
    const printer = printers.find(p => p.id === printerId)
    if (!printer) return
    setLoadingAMS(true)
    api.getPrinterAMS(printer.id).then(trays => {
      const rows: UsageRow[] = trays
        .filter(t => t.spool !== null)
        .map(t => ({ spool_id: t.spool!.id, grams_used: 0, ams_slot: t.slot_key }))
      if (rows.length > 0) setUsages(rows)
    }).finally(() => setLoadingAMS(false))
  }, [printerId])

  const loadFromAMS = async () => {
    if (!selectedPrinter) return
    setLoadingAMS(true)
    try {
      const trays = await api.getPrinterAMS(selectedPrinter.id)
      const rows: UsageRow[] = trays
        .filter(t => t.spool !== null)
        .map(t => ({ spool_id: t.spool!.id, grams_used: 0, ams_slot: t.slot_key }))
      setUsages(rows)
    } finally {
      setLoadingAMS(false)
    }
  }

  const addUsage = () => {
    const first = visibleSpools[0]
    if (first) setUsages(u => [...u, { spool_id: first.id, grams_used: 0, ams_slot: '' }])
  }
  const removeUsage = (i: number) => setUsages(u => u.filter((_, idx) => idx !== i))
  const updateUsage = (i: number, k: keyof UsageRow, v: string | number) =>
    setUsages(u => u.map((row, idx) => idx === i ? { ...row, [k]: v } : row))

  const handleSave = () => {
    const payload: Record<string, unknown> = {
      name,
      model_name: modelName || null,
      description: description || null,
      started_at: localInputToUTC(startedAt, tz),
      finished_at: finishedAt ? localInputToUTC(finishedAt, tz) : null,
      duration_seconds: durationH ? Math.round(parseFloat(durationH) * 3600) : null,
      success,
      notes: notes || null,
      printer_name: selectedPrinter?.name ?? null,
      fm_project_id: fmProjectId || null,
    }
    // Only send usages when the user explicitly entered edit mode — otherwise the
    // backend would revert and re-apply existing usages unchanged, creating noisy
    // audit pairs (print_delete + print_manual) with zero net weight change.
    if (usageEditMode) {
      payload.usages = usages.map(u => ({
        spool_id: Number(u.spool_id),
        grams_used: Number(u.grams_used),
        ams_slot: u.ams_slot || null,
      }))
      payload.deduct_weight = deductWeight
    }
    onSave(payload)
  }

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-surface-2 border border-surface-3 rounded-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-surface-3">
          <h2 className="font-semibold">{initial ? t('prints.editPrint') : t('prints.logPrint')}</h2>
          <button onClick={onCancel} className="btn-ghost p-1"><X size={16} /></button>
        </div>

        <div className="p-5 space-y-4">
          <div>
            <label className="label">{t('prints.form.printName')} *</label>
            <input className="input" value={name} onChange={e => setName(e.target.value)}
              placeholder={t('prints.form.namePlaceholder')} />
          </div>
          <div>
            <label className="label">{t('prints.form.description')}</label>
            <input className="input" value={description} onChange={e => setDescription(e.target.value)} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">{t('prints.form.startedAt')} *</label>
              <input className="input" type="datetime-local" value={startedAt} onChange={e => setStartedAt(e.target.value)} />
            </div>
            <div>
              <label className="label">{t('prints.form.finishedAt')}</label>
              <input
                className={`input ${initial?.finished_at ? 'opacity-60' : ''}`}
                type="datetime-local"
                value={finishedAt}
                onChange={e => setFinishedAt(e.target.value)}
                readOnly={!!initial?.finished_at}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">{t('prints.form.duration')}</label>
              <input className="input" type="number" step="0.1" min="0" value={durationH}
                onChange={e => setDurationH(e.target.value)} placeholder="2.5" />
            </div>
            <div>
              <label className="label">{t('prints.form.printer')}</label>
              {initial ? (
                <p className="input opacity-60 cursor-default select-none">
                  {initial.printer_name ?? t('common.none')}
                </p>
              ) : (
                <select
                  className="input"
                  value={printerId}
                  onChange={e => setPrinterId(e.target.value ? Number(e.target.value) : '')}
                >
                  <option value="">{t('common.none')}</option>
                  {printers.map(p => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              )}
            </div>
          </div>

          {projects.length > 0 && (
            <div>
              <label className="label flex items-center gap-1"><FolderOpen size={12} /> {t('prints.form.project')}</label>
              <select
                className="input"
                value={fmProjectId}
                onChange={e => setFmProjectId(e.target.value ? Number(e.target.value) : '')}
              >
                <option value="">{t('common.none')}</option>
                {projects.map(p => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
          )}

          <div className="flex items-center gap-6">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={success} onChange={e => setSuccess(e.target.checked)} />
              {t('prints.form.printSucceeded')}
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={deductWeight} onChange={e => setDeductWeight(e.target.checked)} />
              {t('prints.form.deductFromSpool')}
            </label>
          </div>

          {/* Filament usages */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="label mb-0">{t('prints.form.filamentUsed')}</label>
              <div className="flex items-center gap-2">
                {usageEditMode ? (
                  <>
                    <label className="flex items-center gap-1 text-xs text-gray-400 cursor-pointer select-none">
                      <input
                        type="checkbox"
                        checked={showEmptySpools}
                        onChange={e => setShowEmptySpools(e.target.checked)}
                        className="accent-blue-500"
                      />
                      {t('prints.form.showEmptySpools')}
                    </label>
                    <button
                      className="btn-ghost text-xs py-0.5 flex items-center gap-1 disabled:opacity-40"
                      onClick={loadFromAMS}
                      disabled={!selectedPrinter || loadingAMS}
                      title={selectedPrinter ? `Load current AMS tray assignments from ${selectedPrinter.name}` : t('prints.form.selectPrinterFirst')}
                    >
                      <Download size={11} />
                      {loadingAMS ? t('prints.form.loading') : t('prints.form.loadFromAMS')}
                    </button>
                    <button className="btn-ghost text-xs py-0.5" onClick={addUsage}>{t('prints.form.addSpool')}</button>
                  </>
                ) : (
                  <button
                    className="btn-ghost text-xs py-0.5 flex items-center gap-1"
                    onClick={() => setUsageEditMode(true)}
                  >
                    <Pencil size={11} />
                    {t('prints.form.editUsages')}
                  </button>
                )}
              </div>
            </div>

            {/* Read-only usage display */}
            {!usageEditMode && (
              usages.length === 0 ? (
                <p className="text-xs text-gray-500">{t('prints.form.noUsagesRecorded')}</p>
              ) : (
                usages.map((u, i) => {
                  const spool = spools.find(s => s.id === u.spool_id)
                  return (
                    <div key={i} className="flex items-center gap-2 py-1 text-xs text-gray-400">
                      {spool && (
                        <span
                          className="w-2.5 h-2.5 rounded-full shrink-0"
                          style={{ background: spool.color_hex }}
                        />
                      )}
                      <span className="flex-1">
                        {spool
                          ? `${spool.brand} ${spool.material}${spool.subtype ? ` ${spool.subtype}` : ''} — ${spool.color_name}`
                          : `Spool #${u.spool_id}`}
                      </span>
                      <span className="text-gray-300">{u.grams_used.toFixed(1)}g</span>
                      {u.ams_slot && <span className="text-blue-400">{u.ams_slot}</span>}
                    </div>
                  )
                })
              )
            )}

            {/* Editable usage rows */}
            {usageEditMode && (
              <>
                {usages.length === 0 && (
                  <p className="text-xs text-gray-500">
                    {selectedPrinter ? t('prints.form.loadAMSHint') : t('prints.form.noAMSPrinter')}
                  </p>
                )}
                {usages.map((u, i) => (
                  <div key={i} className="flex items-center gap-2 mb-2">
                    <select
                      className="input flex-1 text-xs py-1"
                      value={u.spool_id}
                      onChange={e => updateUsage(i, 'spool_id', e.target.value)}
                    >
                      {visibleSpools.map(s => (
                        <option key={s.id} value={s.id}>
                          {s.brand} {s.material}{s.subtype ? ` ${s.subtype}` : ''} — {s.color_name} ({Math.round(s.remaining_pct)}%)
                        </option>
                      ))}
                    </select>
                    <input
                      className="input w-20 text-xs py-1"
                      type="number" step="0.1" min="0"
                      value={u.grams_used || ''}
                      onChange={e => updateUsage(i, 'grams_used', parseFloat(e.target.value) || 0)}
                      placeholder="g"
                    />
                    <span className="text-xs text-gray-500">g</span>
                    <input
                      className="input w-24 text-xs py-1"
                      value={u.ams_slot}
                      onChange={e => updateUsage(i, 'ams_slot', e.target.value)}
                      placeholder="slot"
                    />
                    <button onClick={() => removeUsage(i)} className="text-red-400 hover:text-red-300"><X size={14} /></button>
                  </div>
                ))}
              </>
            )}
          </div>

          <div>
            <label className="label">{t('prints.form.notes')}</label>
            <textarea className="input h-16 resize-none" value={notes} onChange={e => setNotes(e.target.value)} />
          </div>
        </div>

        <div className="flex justify-end gap-2 px-5 py-4 border-t border-surface-3">
          <button className="btn-ghost" onClick={onCancel}>{t('common.cancel')}</button>
          <button className="btn-primary" onClick={handleSave} disabled={!name || !startedAt}>{t('common.save')}</button>
        </div>
      </div>
    </div>
  )
}

// ── Log Usage Modal ───────────────────────────────────────────────────────────

function LogUsageModal({
  job,
  onSave,
  onCancel,
}: {
  job: PrintJob
  onSave: (usages: { spool_id: number; grams_used: number; ams_slot: string }[]) => void
  onCancel: () => void
}) {
  const { t } = useTranslation()

  // Spools list — used to display info for the snapshotted spool_id in each suggestion.
  const { data: spools = [] } = useQuery<Spool[]>({
    queryKey: ['spools'],
    queryFn: api.getSpools,
  })

  // Backward-compat fallback: for old suggestions without a spool_id snapshot,
  // look up the current AMS tray to find which spool is there now.
  const { data: printers = [] } = useQuery<PrinterConfig[]>({
    queryKey: ['printers'],
    queryFn: api.getPrinters,
  })
  const printer = printers.find(p => p.name === job.printer_name) ?? null
  const needsFallback = (job.suggested_usages ?? []).some(s => s.spool_id == null)
  const { data: trays = [] } = useQuery<AMSTray[]>({
    queryKey: ['printer-ams', printer?.id],
    queryFn: () => api.getPrinterAMS(printer!.id),
    enabled: !!printer && needsFallback,
  })
  const traysBySlot = Object.fromEntries(trays.map(t => [t.slot_key, t]))

  const suggestions = job.suggested_usages ?? []

  const [grams, setGrams] = useState<Record<string, string>>(() =>
    Object.fromEntries(suggestions.map(s => [s.ams_slot, String(s.grams)]))
  )

  const handleSave = () => {
    const usages: { spool_id: number; grams_used: number; ams_slot: string }[] = []
    for (const s of suggestions) {
      const gramsVal = parseFloat(grams[s.ams_slot] || '0')
      // Use snapshotted spool_id; fall back to the current AMS tray for old suggestions
      const spoolId = s.spool_id ?? traysBySlot[s.ams_slot]?.spool?.id ?? null
      if (gramsVal <= 0 || spoolId == null) continue
      usages.push({ spool_id: spoolId, grams_used: gramsVal, ams_slot: s.ams_slot })
    }
    onSave(usages)
  }

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-surface-2 border border-surface-3 rounded-2xl w-full max-w-md">
        <div className="flex items-center justify-between px-5 py-4 border-b border-surface-3">
          <div>
            <h2 className="font-semibold">{t('prints.logUsage')}</h2>
            <p className="text-xs text-gray-500 mt-0.5 truncate max-w-xs">{job.name}</p>
          </div>
          <button onClick={onCancel} className="btn-ghost p-1"><X size={16} /></button>
        </div>

        <div className="p-5 space-y-3">
          <p className="text-xs text-blue-400 bg-blue-950/40 rounded px-3 py-1.5">
            {t('prints.cloudSuggestion')}
          </p>

          {suggestions.length === 0 && (
            <p className="text-sm text-gray-500">{t('prints.form.noAMSAssigned')}</p>
          )}

          {suggestions.map(s => {
            // Prefer the snapshotted spool (captured at print-end); fall back to current AMS
            const spool = s.spool_id
              ? (spools.find(sp => sp.id === s.spool_id) ?? null)
              : (traysBySlot[s.ams_slot]?.spool ?? null)
            return (
              <div key={s.ams_slot} className="flex items-center gap-3">
                <span
                  className="w-3 h-3 rounded-full shrink-0"
                  style={{ background: spool?.color_hex ?? '#888' }}
                />
                <div className="flex-1 min-w-0">
                  {spool ? (
                    <>
                      <p className="text-sm text-white truncate">
                        {spool.brand} {spool.material}
                        {spool.subtype ? ` ${spool.subtype}` : ''} · {spool.color_name}
                      </p>
                      <p className="text-xs text-gray-500">
                        {s.ams_slot} · {spool.remaining_pct}%
                        {` (${(spool.current_weight_g / 1000).toFixed(3)} kg)`}
                      </p>
                    </>
                  ) : (
                    <p className="text-sm text-gray-400">{s.ams_slot}</p>
                  )}
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <input
                    className="input w-20 text-sm py-1 text-right"
                    type="number"
                    min="0"
                    step="0.1"
                    placeholder="0"
                    value={grams[s.ams_slot] ?? ''}
                    onChange={e => setGrams(g => ({ ...g, [s.ams_slot]: e.target.value }))}
                  />
                  <span className="text-xs text-gray-500">g</span>
                </div>
              </div>
            )
          })}

          <p className="text-xs text-gray-500 pt-1">{t('prints.gramsHint')}</p>
        </div>

        <div className="flex justify-end gap-2 px-5 py-4 border-t border-surface-3">
          <button className="btn-ghost" onClick={onCancel}>{t('common.cancel')}</button>
          <button
            className="btn-primary"
            onClick={handleSave}
          >
            {t('prints.saveUsage')}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Live status bar for active (open) print jobs ──────────────────────────────

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

function LivePrintStatus({ printerId }: { printerId: number }) {
  const { data: status } = useQuery<PrinterStatus>({
    queryKey: ['printer-status-live', printerId],
    queryFn: () => api.getPrinterStatus(printerId),
    refetchInterval: 10_000,
  })

  const entries = status
    ? LIVE_KEYS.map(k => [k, status[k]] as [string, string | null]).filter(([, v]) => v != null && v !== '')
    : []

  if (entries.length === 0) return null

  return (
    <div className="mt-2 pt-2 border-t border-surface-3 flex flex-wrap gap-x-4 gap-y-0.5">
      {entries.map(([key, val]) => (
        <span key={key} className="text-xs text-gray-500">
          {LIVE_LABELS[key]}: <span className="text-gray-300">{val}{LIVE_UNITS[key] ?? ''}</span>
        </span>
      ))}
    </div>
  )
}

// ── Print Row ─────────────────────────────────────────────────────────────────

function PrintRow({ job, printer, onEdit, onDelete, onLogUsage }: {
  job: PrintJob
  printer: PrinterConfig | null
  onEdit: () => void
  onDelete: () => void
  onLogUsage: () => void
}) {
  const tz = useHATZ()
  const [expanded, setExpanded] = useState(false)
  const needsUsage = job.source === 'auto' && job.finished_at && job.total_grams === 0 && job.suggested_usages !== null
  const showModel = job.model_name && job.model_name !== job.name

  return (
    <div className="card cursor-pointer" onClick={() => setExpanded(e => !e)}>
      <div className="flex items-center gap-3">
        {job.success
          ? <CheckCircle size={16} className="text-green-400 shrink-0" />
          : <XCircle size={16} className="text-red-400 shrink-0" />
        }
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-medium text-white truncate">{job.name}</p>
            {job.source === 'auto' && (
              <span className="text-xs bg-blue-900 text-blue-300 px-1.5 py-0.5 rounded flex items-center gap-0.5 shrink-0">
                <Zap size={9} /> auto
              </span>
            )}
            {job.project_name && (
              <span className="text-xs bg-surface-3 text-gray-300 px-1.5 py-0.5 rounded shrink-0">
                {job.project_name}
              </span>
            )}
          </div>
          <p className="text-xs text-gray-500">
            {formatDateTimeTZ(job.started_at, tz)}
            {job.printer_name && ` · ${job.printer_name}`}
            {job.duration_hours && ` · ${job.duration_hours}h`}
          </p>
          {showModel && (
            <p className="text-xs text-gray-600 flex items-center gap-1 mt-0.5">
              <FileText size={10} />
              {job.model_name}
            </p>
          )}
        </div>
        <div className="text-right shrink-0">
          <p className="text-sm text-white">{job.total_grams.toFixed(1)}g</p>
          {job.total_cost > 0 && <p className="text-xs text-gray-400">€{job.total_cost.toFixed(2)}</p>}
        </div>
        <div className="flex gap-1 ml-2" onClick={e => e.stopPropagation()}>
          {needsUsage && (
            <button
              className="btn-ghost p-1 text-yellow-400"
              onClick={onLogUsage}
              title="Log filament usage"
            >
              <Scale size={12} />
            </button>
          )}
          <button className="btn-ghost p-1" onClick={onEdit}><Pencil size={12} /></button>
          <button className="btn-ghost p-1 text-red-400" onClick={onDelete}><Trash2 size={12} /></button>
        </div>
      </div>

      {/* Live status — always visible for active (open) jobs that have a known printer */}
      {!job.finished_at && printer && (
        <LivePrintStatus printerId={printer.id} />
      )}

      {expanded && job.usages.length > 0 && (
        <div className="mt-3 pt-3 border-t border-surface-3 space-y-1">
          {job.usages.map(u => (
            <div key={u.id} className="flex items-center gap-2 text-xs text-gray-400">
              {u.spool && (
                <span
                  className="w-2.5 h-2.5 rounded-full shrink-0"
                  style={{ background: u.spool.color_hex }}
                />
              )}
              <span className="flex-1">
                {u.spool
                  ? `${u.spool.brand} ${u.spool.material}${u.spool.subtype ? ` ${u.spool.subtype}` : ''} — ${u.spool.color_name}`
                  : `Spool #${u.spool_id}`}
              </span>
              <span>{u.grams_used.toFixed(1)}g</span>
              {u.cost && <span className="text-gray-500">€{u.cost.toFixed(2)}</span>}
              {u.ams_slot && <span className="text-blue-400">{u.ams_slot}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Prints() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const tz = useHATZ()
  const today = nowInTZ(tz).slice(0, 10)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<PrintJob | null>(null)
  const [loggingUsage, setLoggingUsage] = useState<PrintJob | null>(null)
  const [page, setPage] = useState(0)
  const [shown, setShown] = useState<PrintJob[]>([])
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [dateFilter, setDateFilter] = useState<DateFilter | null>(null)

  // Debounce search input — fire API call 300 ms after the user stops typing
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(t)
  }, [search])

  const needle    = debouncedSearch.trim().toLowerCase()
  const dateRange = dateFilter ? resolveDateRange(dateFilter, today) : null
  const isFiltered = !!needle || !!dateRange

  // Reset accumulated list whenever filters change
  useEffect(() => {
    setShown([])
    setPage(0)
  }, [debouncedSearch, dateFilter])

  const { data: total } = useQuery({
    queryKey: ['prints-count', needle, dateRange?.start, dateRange?.end, tz],
    queryFn: () => api.getPrintsTotal(
      needle || undefined,
      dateRange?.start,
      dateRange?.end,
      tz,
    ),
  })

  const { data: pagePrints = [], isLoading } = useQuery<PrintJob[]>({
    queryKey: ['prints', page, needle, dateRange?.start, dateRange?.end, tz],
    queryFn: () => api.getPrints(
      PAGE_SIZE,
      page * PAGE_SIZE,
      needle || undefined,
      dateRange?.start,
      dateRange?.end,
      tz,
    ),
  })

  useEffect(() => {
    if (pagePrints.length === 0) return
    setShown(prev => {
      const existingIds = new Set(prev.map(p => p.id))
      const newItems = pagePrints.filter(p => !existingIds.has(p.id))
      return newItems.length > 0 ? [...prev, ...newItems] : prev
    })
  }, [pagePrints])

  const { data: spools = [] } = useQuery<Spool[]>({
    queryKey: ['spools'],
    queryFn: () => api.getSpools(),
  })

  const { data: printers = [] } = useQuery<PrinterConfig[]>({
    queryKey: ['printers'],
    queryFn: api.getPrinters,
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['prints'] })
    qc.invalidateQueries({ queryKey: ['prints-count'] })
    qc.invalidateQueries({ queryKey: ['spools'] })
    qc.invalidateQueries({ queryKey: ['dashboard'] })
    setShown([])
    setPage(0)
  }

  const createMut = useMutation({ mutationFn: api.createPrint, onSuccess: () => { invalidate(); setShowForm(false) } })
  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: unknown }) => api.updatePrint(id, data),
    onSuccess: (updated: PrintJob) => {
      setShown(prev => prev.map(j => j.id === updated.id ? updated : j))
      qc.invalidateQueries({ queryKey: ['spools'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
      setEditing(null)
    },
  })
  const deleteMut = useMutation({ mutationFn: api.deletePrint, onSuccess: invalidate })

  const totalCount = total?.total ?? 0
  const hasMore = shown.length < totalCount

  // Filtering is handled server-side; shown contains only matching results
  const filtered = shown

  const totalGrams = filtered.reduce((s, j) => s + j.total_grams, 0)
  const totalCost  = filtered.reduce((s, j) => s + j.total_cost, 0)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-lg font-bold">
            {t('prints.history')} ({isFiltered ? `${filtered.length} of ` : ''}{shown.length}{totalCount > shown.length ? ` of ${totalCount}` : ''})
          </h2>
          {filtered.length > 0 && (
            <p className="text-xs text-gray-500">
              {totalGrams.toFixed(0)}g · €{totalCost.toFixed(2)}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
            <input
              className="input pl-7 py-1.5 text-sm w-48"
              placeholder={t('prints.search')}
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          <button className="btn-primary flex items-center gap-1.5" onClick={() => setShowForm(true)}>
            <Plus size={14} /> {t('prints.logPrint')}
          </button>
        </div>
      </div>

      {/* Date filter bar */}
      <div className="card py-2.5 px-3 flex items-center gap-2 flex-wrap">
        <CalendarDays size={13} className="text-gray-500 shrink-0" />

        {(['month', 'week', 'day'] as FilterMode[]).map(m => (
          <button
            key={m}
            onClick={() => setDateFilter(f =>
              f?.mode === m ? null : { mode: m, preset: 'this', custom: presetToCustom(m, 'this', today) }
            )}
            className={`px-2.5 py-1 text-xs rounded-lg transition-colors ${
              dateFilter?.mode === m
                ? 'bg-blue-900 text-blue-200'
                : 'text-gray-400 hover:text-white hover:bg-surface-3 border border-surface-3'
            }`}
          >
            {t(`prints.filter.${m}`)}
          </button>
        ))}

        {dateFilter && (
          <>
            <div className="w-px h-4 bg-surface-3 mx-0.5" />

            {(['this', 'last'] as const).map(p => (
              <button
                key={p}
                onClick={() => setDateFilter(f => f ? { ...f, preset: p, custom: presetToCustom(f.mode, p, today) } : null)}
                className={`px-2.5 py-1 text-xs rounded-lg transition-colors ${
                  dateFilter.preset === p
                    ? 'bg-surface-3 text-white'
                    : 'text-gray-400 hover:text-white hover:bg-surface-3'
                }`}
              >
                {dateFilter.mode === 'month'
                  ? (p === 'this' ? t('prints.filter.thisMonth') : t('prints.filter.lastMonth'))
                  : dateFilter.mode === 'week'
                  ? (p === 'this' ? t('prints.filter.thisWeek') : t('prints.filter.lastWeek'))
                  : (p === 'this' ? t('prints.filter.today') : t('prints.filter.yesterday'))}
              </button>
            ))}

            <input
              type={dateFilter.mode === 'month' ? 'month' : 'date'}
              className="input py-0.5 text-xs"
              style={{ width: 132 }}
              value={dateFilter.custom}
              onChange={e => {
                if (!e.target.value) return
                if (dateFilter.mode === 'week') {
                  // Snap to Monday of the selected week
                  const monday = getMondayOf(e.target.value)
                  setDateFilter(f => f ? { ...f, preset: 'custom', custom: monday } : null)
                } else {
                  setDateFilter(f => f ? { ...f, preset: 'custom', custom: e.target.value } : null)
                }
              }}
            />
            {dateFilter.mode === 'week' && dateFilter.custom && (
              <span className="text-xs text-gray-400 whitespace-nowrap">
                {fmtShort(dateFilter.custom)} – {fmtShort(addDays(dateFilter.custom, 6))}
              </span>
            )}

            <button
              onClick={() => setDateFilter(null)}
              className="text-gray-500 hover:text-white ml-0.5"
              title={t('prints.filter.clear')}
            >
              <X size={13} />
            </button>
          </>
        )}
      </div>

      {isLoading && shown.length === 0 && <p className="text-gray-500 text-sm">{t('common.loading')}</p>}

      {isFiltered && filtered.length === 0 && shown.length > 0 && (
        <p className="text-sm text-gray-500">{t('prints.noResults')}</p>
      )}

      <div className="space-y-2">
        {filtered.map(job => (
          <PrintRow
            key={job.id}
            job={job}
            printer={printers.find(p => p.name === job.printer_name) ?? null}
            onEdit={() => setEditing(job)}
            onDelete={() => { if (confirm(t('prints.confirmDelete', { name: job.name }))) deleteMut.mutate(job.id) }}
            onLogUsage={() => setLoggingUsage(job)}
          />
        ))}
      </div>

      {hasMore && (
        <div className="flex justify-center pt-2">
          <button
            className="btn-ghost text-sm px-6"
            onClick={() => setPage(p => p + 1)}
            disabled={isLoading}
          >
            {isLoading ? t('common.loading') : t('prints.loadMore', { n: totalCount - shown.length })}
          </button>
        </div>
      )}

      {(showForm || editing) && (
        <Modal>
          <PrintForm
            initial={editing ?? undefined}
            spools={spools}
            onSave={data => {
              if (editing) updateMut.mutate({ id: editing.id, data })
              else createMut.mutate(data)
            }}
            onCancel={() => { setShowForm(false); setEditing(null) }}
          />
        </Modal>
      )}

      {loggingUsage && (
        <Modal>
          <LogUsageModal
            job={loggingUsage}
            onSave={usages => {
              updateMut.mutate({
                id: loggingUsage.id,
                data: { usages },
              })
              setLoggingUsage(null)
            }}
            onCancel={() => setLoggingUsage(null)}
          />
        </Modal>
      )}
    </div>
  )
}
