import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api } from '../api'
import type { PrintJob, Spool, AMSTray, PrinterConfig } from '../types'
import { Plus, Pencil, Trash2, X, CheckCircle, XCircle, Zap, Scale, FileText, Download } from 'lucide-react'
import Modal from '../components/Modal'
import { format } from 'date-fns'

const PAGE_SIZE = 50

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
  const now = format(new Date(), "yyyy-MM-dd'T'HH:mm")
  const [name, setName] = useState(initial?.name ?? '')
  const [modelName, setModelName] = useState(initial?.model_name ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [startedAt, setStartedAt] = useState(
    initial?.started_at ? initial.started_at.slice(0, 16) : now
  )
  const [finishedAt, setFinishedAt] = useState(
    initial?.finished_at ? initial.finished_at.slice(0, 16) : ''
  )
  const [durationH, setDurationH] = useState(
    initial?.duration_hours?.toString() ?? ''
  )
  const [success, setSuccess] = useState(initial?.success ?? true)
  const [printerId, setPrinterId] = useState<number | ''>('')
  const [notes, setNotes] = useState(initial?.notes ?? '')
  const [usages, setUsages] = useState<UsageRow[]>(
    initial?.usages?.map(u => ({
      spool_id: u.spool_id,
      grams_used: u.grams_used,
      ams_slot: u.ams_slot ?? '',
    })) ?? []
  )
  const [loadingAMS, setLoadingAMS] = useState(false)

  const { data: printers = [] } = useQuery<PrinterConfig[]>({
    queryKey: ['printers'],
    queryFn: api.getPrinters,
  })

  useEffect(() => {
    if (initial?.printer_name && printers.length > 0) {
      const match = printers.find(p => p.name === initial.printer_name)
      if (match) setPrinterId(match.id)
    }
  }, [printers, initial?.printer_name])

  const selectedPrinter = printers.find(p => p.id === printerId) ?? null

  // Auto-load AMS on first open when printer is known and no usages are set yet
  useEffect(() => {
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
    const first = spools[0]
    if (first) setUsages(u => [...u, { spool_id: first.id, grams_used: 0, ams_slot: '' }])
  }
  const removeUsage = (i: number) => setUsages(u => u.filter((_, idx) => idx !== i))
  const updateUsage = (i: number, k: keyof UsageRow, v: string | number) =>
    setUsages(u => u.map((row, idx) => idx === i ? { ...row, [k]: v } : row))

  const handleSave = () => {
    onSave({
      name,
      model_name: modelName || null,
      description: description || null,
      started_at: startedAt,
      finished_at: finishedAt || null,
      duration_seconds: durationH ? Math.round(parseFloat(durationH) * 3600) : null,
      success,
      notes: notes || null,
      printer_name: selectedPrinter?.name ?? null,
      usages: usages.map(u => ({
        spool_id: Number(u.spool_id),
        grams_used: Number(u.grams_used),
        ams_slot: u.ams_slot || null,
      })),
    })
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
            <label className="label">{t('prints.form.modelFile')}</label>
            <input className="input" value={modelName} onChange={e => setModelName(e.target.value)}
              placeholder={t('prints.form.modelPlaceholder')} />
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
              <input className="input" type="datetime-local" value={finishedAt} onChange={e => setFinishedAt(e.target.value)} />
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
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" checked={success} onChange={e => setSuccess(e.target.checked)} />
            {t('prints.form.printSucceeded')}
          </label>

          {/* Filament usages */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="label mb-0">{t('prints.form.filamentUsed')}</label>
              <div className="flex items-center gap-2">
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
              </div>
            </div>
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
                  {spools.map(s => (
                    <option key={s.id} value={s.id}>
                      {s.brand} {s.material}{s.subtype ? ` ${s.subtype}` : ''} — {s.color_name}
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
  const { data: printers = [] } = useQuery<PrinterConfig[]>({
    queryKey: ['printers'],
    queryFn: api.getPrinters,
  })

  const printer = printers.find(p => p.name === job.printer_name) ?? printers[0] ?? null

  const { data: trays = [], isLoading } = useQuery<AMSTray[]>({
    queryKey: ['printer-ams', printer?.id],
    queryFn: () => api.getPrinterAMS(printer!.id),
    enabled: !!printer,
  })

  const assigned = trays.filter(t => t.spool !== null)
  const [grams, setGrams] = useState<Record<string, string>>({})

  const handleSave = () => {
    const usages = assigned
      .map(t => ({ spool_id: t.spool!.id, grams_used: parseFloat(grams[t.slot_key] || '0'), ams_slot: t.slot_key }))
      .filter(u => u.grams_used > 0)
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
          {isLoading && <p className="text-sm text-gray-500">{t('prints.form.loading')}</p>}

          {!isLoading && assigned.length === 0 && (
            <p className="text-sm text-gray-500">{t('prints.form.noAMSAssigned')}</p>
          )}

          {assigned.map(t => (
            <div key={t.slot_key} className="flex items-center gap-3">
              <span
                className="w-3 h-3 rounded-full shrink-0"
                style={{ background: t.spool!.color_hex }}
              />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-white truncate">
                  {t.spool!.brand} {t.spool!.material}
                  {t.spool!.subtype ? ` ${t.spool!.subtype}` : ''} · {t.spool!.color_name}
                </p>
                <p className="text-xs text-gray-500">
                  {t.tray} · {t.spool!.remaining_pct}% {t.spool!.current_weight_g !== undefined
                    ? `(${(t.spool!.current_weight_g / 1000).toFixed(3)} kg)`
                    : ''}
                </p>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <input
                  className="input w-20 text-sm py-1 text-right"
                  type="number"
                  min="0"
                  step="0.1"
                  placeholder="0"
                  value={grams[t.slot_key] ?? ''}
                  onChange={e => setGrams(g => ({ ...g, [t.slot_key]: e.target.value }))}
                />
                <span className="text-xs text-gray-500">g</span>
              </div>
            </div>
          ))}

          <p className="text-xs text-gray-500 pt-1">{t('prints.gramsHint')}</p>
        </div>

        <div className="flex justify-end gap-2 px-5 py-4 border-t border-surface-3">
          <button className="btn-ghost" onClick={onCancel}>{t('common.cancel')}</button>
          <button
            className="btn-primary"
            onClick={handleSave}
            disabled={assigned.length === 0}
          >
            {t('prints.saveUsage')}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Print Row ─────────────────────────────────────────────────────────────────

function PrintRow({ job, onEdit, onDelete, onLogUsage }: {
  job: PrintJob
  onEdit: () => void
  onDelete: () => void
  onLogUsage: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const needsUsage = job.source === 'auto' && job.finished_at && job.usages.length === 0
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
          </div>
          <p className="text-xs text-gray-500">
            {format(new Date(job.started_at), 'dd.MM.yyyy HH:mm')}
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
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<PrintJob | null>(null)
  const [loggingUsage, setLoggingUsage] = useState<PrintJob | null>(null)
  const [page, setPage] = useState(0)
  const [shown, setShown] = useState<PrintJob[]>([])

  const { data: total } = useQuery({
    queryKey: ['prints-count'],
    queryFn: api.getPrintsTotal,
  })

  const { data: pagePrints = [], isLoading } = useQuery<PrintJob[]>({
    queryKey: ['prints', page],
    queryFn: () => api.getPrints(PAGE_SIZE, page * PAGE_SIZE),
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
    onSuccess: () => { invalidate(); setEditing(null) },
  })
  const deleteMut = useMutation({ mutationFn: api.deletePrint, onSuccess: invalidate })

  const totalCount = total?.total ?? 0
  const hasMore = shown.length < totalCount

  const totalGrams = shown.reduce((s, j) => s + j.total_grams, 0)
  const totalCost  = shown.reduce((s, j) => s + j.total_cost, 0)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-lg font-bold">
            {t('prints.history')} ({shown.length}{totalCount > shown.length ? ` of ${totalCount}` : ''})
          </h2>
          {shown.length > 0 && (
            <p className="text-xs text-gray-500">
              {totalGrams.toFixed(0)}g · €{totalCost.toFixed(2)}
            </p>
          )}
        </div>
        <button className="btn-primary flex items-center gap-1.5" onClick={() => setShowForm(true)}>
          <Plus size={14} /> {t('prints.logPrint')}
        </button>
      </div>

      {isLoading && shown.length === 0 && <p className="text-gray-500 text-sm">{t('common.loading')}</p>}

      <div className="space-y-2">
        {shown.map(job => (
          <PrintRow
            key={job.id}
            job={job}
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
