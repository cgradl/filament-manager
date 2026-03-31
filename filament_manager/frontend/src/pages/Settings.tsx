import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api } from '../api'
import type { PrinterConfig, DiscoverResult, AMSTray, Spool, BrandSpoolWeight, FilamentSubtype } from '../types'
import { Plus, Trash2, X, RefreshCw, CheckCircle, AlertCircle, Search, Pencil, ChevronDown, ChevronUp, Download, Upload } from 'lucide-react'
import Modal from '../components/Modal'
import BambuCloudSection from '../components/BambuCloudSection'

// ── Printer Form ──────────────────────────────────────────────────────────────

function PrinterForm({
  initial,
  onSave,
  onCancel,
}: {
  initial?: PrinterConfig
  onSave: (data: { name: string; device_slug: string; ams_device_slug: string | null; ams_unit_count: number; is_active: boolean }) => void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  const [name, setName] = useState(initial?.name ?? '')
  const [deviceName, setDeviceName] = useState(
    initial?.device_slug.replace(/_/g, ' ') ?? ''
  )
  const [amsDeviceName, setAmsDeviceName] = useState(
    initial?.ams_device_slug?.replace(/_/g, ' ') ?? ''
  )
  const [amsCount, setAmsCount] = useState(initial?.ams_unit_count ?? 1)
  const [isActive, setIsActive] = useState(initial?.is_active ?? true)
  const [discovery, setDiscovery] = useState<DiscoverResult | null>(null)
  const [discovering, setDiscovering] = useState(false)

  const haSlugify = (s: string) =>
    s.toLowerCase().trim()
      .replace(/[\s-]+/g, '_')   // spaces/hyphens → underscore
      .replace(/[^\w]/g, '')     // strip anything not a-z, 0-9, _
      .replace(/_+/g, '_')       // collapse consecutive underscores
      .replace(/^_|_$/g, '')     // trim leading/trailing underscores

  const slug = haSlugify(deviceName)
  const amsSlug = haSlugify(amsDeviceName) || null

  const discover = async () => {
    if (!deviceName.trim()) return
    setDiscovering(true)
    try {
      const result = await api.discoverPrinter(deviceName.trim(), amsDeviceName.trim() || undefined)
      setDiscovery(result)
    } catch {
      setDiscovery(null)
    } finally {
      setDiscovering(false)
    }
  }

  const ENTITY_LABELS: Record<string, string> = {
    print_stage: 'Print Stage',
    print_progress: 'Print Progress',
    remaining_time: 'Remaining Time',
    nozzle_temp: 'Nozzle Temp',
    bed_temp: 'Bed Temp',
    current_file: 'Current File',
  }

  const foundCount = discovery
    ? Object.values(discovery.printer_entities).filter(e => e.found).length
    : 0
  const amsFoundCount = discovery
    ? discovery.ams_preview.flatMap(u => u.trays).filter(t => t.found).length
    : 0
  const amsTotalCount = discovery
    ? discovery.ams_preview.flatMap(u => u.trays).length
    : 0

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-surface-2 border border-surface-3 rounded-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-surface-3">
          <h2 className="font-semibold">{initial ? t('settings.printers.editPrinter') : t('settings.printers.addPrinter')}</h2>
          <button onClick={onCancel} className="btn-ghost p-1"><X size={16} /></button>
        </div>

        <div className="p-5 space-y-4">
          <div>
            <label className="label">{t('settings.printers.name')} *</label>
            <input className="input" value={name} onChange={e => setName(e.target.value)} placeholder="H2S" />
          </div>

          <div>
            <label className="label">{t('settings.printers.haDeviceName')}</label>
            <p className="text-xs text-gray-500 mb-1.5">{t('settings.printers.haDeviceHint')}</p>
            <div className="flex gap-2">
              <input
                className="input flex-1"
                value={deviceName}
                onChange={e => { setDeviceName(e.target.value); setDiscovery(null) }}
                placeholder="H2S"
              />
              <button
                className="btn-ghost px-3 flex items-center gap-1.5 shrink-0"
                onClick={discover}
                disabled={!deviceName.trim() || discovering}
              >
                <Search size={13} className={discovering ? 'animate-spin' : ''} />
                {t('settings.printers.discoverSearch')}
              </button>
            </div>
            {slug && (
              <p className="text-xs text-gray-500 mt-1">
                Entity prefix: <code className="bg-surface-3 px-1 rounded">sensor.{slug}_…</code>
              </p>
            )}
          </div>

          <div>
            <label className="label">{t('settings.printers.amsDeviceName')}</label>
            <p className="text-xs text-gray-500 mb-1.5">{t('settings.printers.amsDeviceHint')}</p>
            <input
              className="input"
              value={amsDeviceName}
              onChange={e => { setAmsDeviceName(e.target.value); setDiscovery(null) }}
              placeholder={t('settings.printers.leaveBlank')}
            />
            {amsSlug && amsSlug !== slug && (
              <p className="text-xs text-gray-500 mt-1">
                AMS prefix: <code className="bg-surface-3 px-1 rounded">sensor.{amsSlug}_ams_…</code>
              </p>
            )}
          </div>

          {discovery && (
            <div className="bg-surface-3/50 rounded-xl p-3 space-y-3">
              <div>
                <p className="text-xs font-medium text-gray-300 mb-2">
                  Printer: {foundCount}/{Object.keys(discovery.printer_entities).length} entities found
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-1">
                  {Object.entries(discovery.printer_entities).map(([key, info]) => (
                    <div key={key} className="flex items-center gap-1.5 text-xs">
                      {info.found
                        ? <CheckCircle size={11} className="text-green-400 shrink-0" />
                        : <AlertCircle size={11} className="text-red-400 shrink-0" />
                      }
                      <span className={info.found ? 'text-gray-300' : 'text-gray-500'}>
                        {ENTITY_LABELS[key]}
                        {info.found && info.state && (
                          <span className="text-gray-500"> = {info.state}</span>
                        )}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="border-t border-surface-3 pt-2">
                <p className="text-xs font-medium text-gray-300 mb-2">
                  AMS: {amsFoundCount}/{amsTotalCount} tray entities found
                </p>
                <div className="grid grid-cols-4 gap-1">
                  {discovery.ams_preview.flatMap(u => u.trays).map(t => (
                    <div key={t.slot} className={`text-xs text-center py-1 rounded ${
                      t.found ? 'bg-green-900/40 text-green-400' : 'bg-surface-3 text-gray-500'
                    }`}>
                      T{t.slot}
                      {t.found && t.state != null && (
                        <span className="block text-gray-400">{t.state}%</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {discovery.all_matching.length > 0 && foundCount === 0 && (
                <div className="border-t border-surface-3 pt-2">
                  <p className="text-xs text-yellow-400 mb-1">
                    No exact matches. Entities containing "{discovery.slug}":
                  </p>
                  <div className="space-y-0.5 max-h-24 overflow-y-auto">
                    {discovery.all_matching.slice(0, 10).map(e => (
                      <p key={e.entity_id} className="text-xs font-mono text-gray-400">{e.entity_id}</p>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          <div>
            <label className="label">{t('settings.printers.amsUnitCount')}</label>
            <select
              className="input w-32"
              value={amsCount}
              onChange={e => setAmsCount(Number(e.target.value))}
            >
              {[1, 2, 3, 4].map(n => (
                <option key={n} value={n}>{n} AMS unit{n > 1 ? 's' : ''}</option>
              ))}
            </select>
          </div>

          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" checked={isActive} onChange={e => setIsActive(e.target.checked)} />
            {t('settings.printers.monitorPrinter')}
          </label>
        </div>

        <div className="flex justify-end gap-2 px-5 py-4 border-t border-surface-3">
          <button className="btn-ghost" onClick={onCancel}>{t('common.cancel')}</button>
          <button
            className="btn-primary"
            onClick={() => onSave({
              name,
              device_slug: slug,
              ams_device_slug: amsSlug !== slug ? amsSlug : null,
              ams_unit_count: amsCount,
              is_active: isActive,
            })}
            disabled={!name.trim() || !deviceName.trim()}
          >
            {t('common.save')}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── AMS Tray Panel ────────────────────────────────────────────────────────────

function AMSTrayPanel({ printer }: { printer: PrinterConfig }) {
  const { t } = useTranslation()
  const qc = useQueryClient()

  const { data: trays, isLoading, refetch } = useQuery<AMSTray[]>({
    queryKey: ['printer-ams', printer.id],
    queryFn: () => api.getPrinterAMS(printer.id),
    refetchInterval: 30_000,
  })

  const { data: spools = [] } = useQuery<Spool[]>({
    queryKey: ['spools'],
    queryFn: () => api.getSpools(),
  })

  const assignMut = useMutation({
    mutationFn: ({ slot, spoolId }: { slot: string; spoolId: number | null }) =>
      api.assignAMSTray(printer.id, slot, spoolId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['printer-ams', printer.id] })
      qc.invalidateQueries({ queryKey: ['spools'] })
    },
  })

  const [syncingSlot, setSyncingSlot] = useState<string | null>(null)

  const syncSlotMut = useMutation({
    mutationFn: (slotKey: string) => api.syncAMSTrayWeight(printer.id, slotKey),
    onMutate: (slotKey) => setSyncingSlot(slotKey),
    onSettled: () => setSyncingSlot(null),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ['spools'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
      alert(`Updated ${result.spool_name}: ${result.remaining_pct}% → ${result.new_weight_g} g`)
    },
    onError: (err) => {
      alert(err instanceof Error ? err.message : 'Sync failed — no valid HA data for this tray')
    },
  })

  if (isLoading) return <p className="text-xs text-gray-500 py-2">{t('settings.printers.loadingAMS')}</p>
  if (!trays?.length) return <p className="text-xs text-gray-500 py-2">{t('settings.printers.noAMSData')}</p>

  const units = Array.from(new Set(trays.map(t => t.ams_id))).sort()

  return (
    <div className="mt-3 space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-gray-400">{t('settings.printers.amsAssignment')}</p>
        <button className="btn-ghost p-1" onClick={() => refetch()} title="Refresh display">
          <RefreshCw size={11} />
        </button>
      </div>

      {units.map(amsId => (
        <div key={amsId}>
          {units.length > 1 && (
            <p className="text-xs text-gray-500 mb-1.5">{t('settings.printers.amsUnit', { n: amsId })}</p>
          )}
          <div className="space-y-1.5">
            {trays.filter(t => t.ams_id === amsId).map(tray => (
              <AMSTrayRow
                key={tray.slot_key}
                tray={tray}
                spools={spools}
                onAssign={(spoolId) => assignMut.mutate({ slot: tray.slot_key, spoolId })}
                saving={assignMut.isPending}
                onSyncWeight={() => syncSlotMut.mutate(tray.slot_key)}
                syncingWeight={syncingSlot === tray.slot_key}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function AMSTrayRow({
  tray,
  spools,
  onAssign,
  saving,
  onSyncWeight,
  syncingWeight,
}: {
  tray: AMSTray
  spools: Spool[]
  onAssign: (spoolId: number | null) => void
  saving: boolean
  onSyncWeight: () => void
  syncingWeight: boolean
}) {
  const { t } = useTranslation()
  const selectedId = tray.spool?.id ?? null

  return (
    <div className="flex items-center gap-2 bg-surface-3/40 rounded-lg px-3 py-2">
      <span className="text-xs font-mono text-gray-400 w-6 shrink-0">T{tray.tray}</span>

      <div className="flex items-center gap-1.5 min-w-0 w-28 shrink-0">
        {tray.ha_color_hex ? (
          <span
            className="w-3 h-3 rounded-full border border-white/20 shrink-0"
            style={{ background: tray.ha_color_hex }}
          />
        ) : (
          <span className="w-3 h-3 rounded-full bg-surface-3 border border-white/10 shrink-0" />
        )}
        <span className="text-xs text-gray-500 truncate">
          {tray.ha_material ?? '—'}
        </span>
      </div>

      <span className="text-xs text-gray-500 w-10 shrink-0 text-right">
        {tray.ha_remaining != null ? `${tray.ha_remaining}%` : '—'}
      </span>

      <select
        className="input text-xs flex-1 py-1 min-w-0"
        value={selectedId ?? ''}
        disabled={saving}
        onChange={e => onAssign(e.target.value ? Number(e.target.value) : null)}
      >
        <option value="">{t('settings.printers.unassigned')}</option>
        {spools.map(s => (
          <option key={s.id} value={s.id}>
            {s.brand} {s.material}{s.subtype ? ` ${s.subtype}` : ''} · {s.color_name} ({Math.round(s.remaining_pct)}%)
          </option>
        ))}
      </select>

      {tray.spool ? (
        <>
          <span
            className="w-3 h-3 rounded-full border border-white/20 shrink-0"
            style={{ background: tray.spool.color_hex }}
            title={tray.spool.color_name}
          />
          <button
            className="btn-ghost p-1 shrink-0 text-gray-400 hover:text-white"
            onClick={onSyncWeight}
            disabled={syncingWeight}
            title="Sync weight from AMS (only updates if HA reports > 0%)"
          >
            <RefreshCw size={10} className={syncingWeight ? 'animate-spin' : ''} />
          </button>
        </>
      ) : (
        <span className="w-3 h-3 shrink-0" />
      )}
    </div>
  )
}

// ── Printer Card ──────────────────────────────────────────────────────────────

function PrinterCard({ printer, onEdit, onDelete }: {
  printer: PrinterConfig
  onEdit: () => void
  onDelete: () => void
}) {
  const { t } = useTranslation()
  const [showAMS, setShowAMS] = useState(false)

  const { data: status, refetch, isFetching } = useQuery({
    queryKey: ['printer-status', printer.id],
    queryFn: () => api.getPrinterStatus(printer.id),
    refetchInterval: 30_000,
    enabled: printer.is_active,
  })

  const stage = (status as Record<string, string | null> | undefined)?.print_stage?.toLowerCase() ?? 'unknown'
  const isPrinting = ['printing', 'auto_bed_leveling', 'heatbed_preheating'].includes(stage)

  const LABELS: Record<string, string> = {
    print_stage: 'Stage', print_progress: 'Progress',
    remaining_time: 'Remaining', nozzle_temp: 'Nozzle',
    bed_temp: 'Bed', current_file: 'File',
  }
  const UNITS: Record<string, string> = {
    nozzle_temp: '°C', bed_temp: '°C', print_progress: '%', remaining_time: ' min',
  }

  return (
    <div className="card">
      <div className="flex items-start justify-between mb-3">
        <div>
          <p className="font-semibold text-white">{printer.name}</p>
          <p className="text-xs text-gray-500 font-mono">sensor.{printer.device_slug}_…</p>
          {printer.ams_device_slug && (
            <p className="text-xs text-gray-500 font-mono">AMS: sensor.{printer.ams_device_slug}_ams_…</p>
          )}
          <div className="flex items-center gap-2 mt-1">
            <span className={`text-xs px-2 py-0.5 rounded-full ${
              isPrinting ? 'bg-blue-900 text-blue-300' :
              stage === 'finish' ? 'bg-green-900 text-green-300' :
              'bg-surface-3 text-gray-400'
            }`}>
              {stage}
            </span>
            <span className="text-xs text-gray-500">{printer.ams_unit_count} AMS</span>
          </div>
        </div>
        <div className="flex gap-1">
          <button className="btn-ghost p-1" onClick={() => refetch()} title="Refresh">
            <RefreshCw size={12} className={isFetching ? 'animate-spin' : ''} />
          </button>
          <button className="btn-ghost p-1" onClick={onEdit}><Pencil size={12} /></button>
          <button className="btn-ghost p-1 text-red-400" onClick={onDelete}><Trash2 size={12} /></button>
        </div>
      </div>

      {status && (
        <div className="grid grid-cols-3 gap-x-4 gap-y-1 text-xs text-gray-400">
          {Object.entries(status as unknown as Record<string, string | null>).map(([key, val]) => (
            val && key !== 'print_stage' ? (
              <span key={key}>
                {LABELS[key] ?? key}:{' '}
                <span className="text-white">{val}{UNITS[key] ?? ''}</span>
              </span>
            ) : null
          ))}
        </div>
      )}

      <button
        className="mt-3 flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 transition-colors"
        onClick={() => setShowAMS(v => !v)}
      >
        {showAMS ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        {t('settings.printers.amsAssignment')}
      </button>

      {showAMS && <AMSTrayPanel printer={printer} />}
    </div>
  )
}

// ── Brand Spool Weights ───────────────────────────────────────────────────────

function BrandWeightsSection() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [newBrand, setNewBrand] = useState('')
  const [newWeight, setNewWeight] = useState('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editBrand, setEditBrand] = useState('')
  const [editWeight, setEditWeight] = useState('')

  const { data: entries = [] } = useQuery<BrandSpoolWeight[]>({
    queryKey: ['brand-weights'],
    queryFn: api.getBrandWeights,
  })

  const inv = () => qc.invalidateQueries({ queryKey: ['brand-weights'] })

  const createMut = useMutation({
    mutationFn: () => api.createBrandWeight({ brand: newBrand.trim(), spool_weight_g: parseFloat(newWeight) }),
    onSuccess: () => { inv(); setNewBrand(''); setNewWeight('') },
  })
  const updateMut = useMutation({
    mutationFn: ({ id }: { id: number }) =>
      api.updateBrandWeight(id, { brand: editBrand.trim(), spool_weight_g: parseFloat(editWeight) }),
    onSuccess: () => { inv(); setEditingId(null) },
  })
  const deleteMut = useMutation({ mutationFn: api.deleteBrandWeight, onSuccess: inv })

  const startEdit = (e: BrandSpoolWeight) => {
    setEditingId(e.id); setEditBrand(e.brand); setEditWeight(e.spool_weight_g.toString())
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-300">{t('settings.brandWeights.title')}</h3>
      </div>
      <p className="text-xs text-gray-500 mb-3">{t('settings.brandWeights.hint')}</p>

      <div className="card space-y-2">
        {entries.length === 0 && (
          <p className="text-xs text-gray-500 py-1">{t('settings.brandWeights.noEntries')}</p>
        )}

        {entries.map(e => (
          <div key={e.id} className="flex items-center gap-2">
            {editingId === e.id ? (
              <>
                <input
                  className="input flex-1 text-sm py-1"
                  value={editBrand}
                  onChange={ev => setEditBrand(ev.target.value)}
                  placeholder={t('settings.brandWeights.brand')}
                />
                <input
                  className="input w-24 text-sm py-1 text-right"
                  type="number" min="0" step="1"
                  value={editWeight}
                  onChange={ev => setEditWeight(ev.target.value)}
                />
                <span className="text-xs text-gray-500 shrink-0">g</span>
                <button
                  className="btn-primary text-xs px-2 py-1"
                  onClick={() => updateMut.mutate({ id: e.id })}
                  disabled={!editBrand || !editWeight}
                >
                  {t('common.save')}
                </button>
                <button className="btn-ghost p-1" onClick={() => setEditingId(null)}><X size={12} /></button>
              </>
            ) : (
              <>
                <span className="flex-1 text-sm text-white">{e.brand}</span>
                <span className="text-sm text-gray-300 tabular-nums">{e.spool_weight_g.toFixed(0)} g</span>
                <button className="btn-ghost p-1" onClick={() => startEdit(e)}><Pencil size={12} /></button>
                <button
                  className="btn-ghost p-1 text-red-400"
                  onClick={() => deleteMut.mutate(e.id)}
                ><Trash2 size={12} /></button>
              </>
            )}
          </div>
        ))}

        <div className="flex items-center gap-2 pt-2 border-t border-surface-3">
          <input
            className="input flex-1 text-sm py-1"
            value={newBrand}
            onChange={e => setNewBrand(e.target.value)}
            placeholder={t('settings.brandWeights.brandPlaceholder')}
          />
          <input
            className="input w-24 text-sm py-1 text-right"
            type="number" min="0" step="1"
            value={newWeight}
            onChange={e => setNewWeight(e.target.value)}
            placeholder="250"
          />
          <span className="text-xs text-gray-500 shrink-0">g</span>
          <button
            className="btn-primary text-xs px-2 py-1 flex items-center gap-1 shrink-0"
            onClick={() => createMut.mutate()}
            disabled={!newBrand.trim() || !newWeight || createMut.isPending}
          >
            <Plus size={12} /> {t('common.add')}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Generic name-list section (subtypes / materials / brands) ─────────────────

function NameListSection({
  title,
  hint,
  queryKey,
  fetchFn,
  createFn,
  updateFn,
  deleteFn,
  placeholder,
  noEntries,
}: {
  title: string
  hint?: string
  queryKey: string
  fetchFn: () => Promise<FilamentSubtype[]>
  createFn: (name: string) => Promise<FilamentSubtype>
  updateFn: (id: number, name: string) => Promise<FilamentSubtype>
  deleteFn: (id: number) => Promise<void>
  placeholder: string
  noEntries: string
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [newName, setNewName] = useState('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editName, setEditName] = useState('')

  const { data: entries = [] } = useQuery<FilamentSubtype[]>({
    queryKey: [queryKey],
    queryFn: fetchFn,
  })

  const inv = () => qc.invalidateQueries({ queryKey: [queryKey] })

  const createMut = useMutation({
    mutationFn: () => createFn(newName.trim()),
    onSuccess: () => { inv(); setNewName('') },
  })
  const updateMut = useMutation({
    mutationFn: ({ id }: { id: number }) => updateFn(id, editName.trim()),
    onSuccess: () => { inv(); setEditingId(null) },
  })
  const deleteMut = useMutation({ mutationFn: deleteFn, onSuccess: inv })

  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-300 mb-1">{title}</h3>
      {hint && <p className="text-xs text-gray-500 mb-3">{hint}</p>}

      <div className="card space-y-2">
        {entries.length === 0 && (
          <p className="text-xs text-gray-500 py-1">{noEntries}</p>
        )}

        {entries.map(e => (
          <div key={e.id} className="flex items-center gap-2">
            {editingId === e.id ? (
              <>
                <input
                  className="input flex-1 text-sm py-1"
                  value={editName}
                  onChange={ev => setEditName(ev.target.value)}
                  autoFocus
                  onKeyDown={ev => ev.key === 'Enter' && editName.trim() && updateMut.mutate({ id: e.id })}
                />
                <button
                  className="btn-primary text-xs px-2 py-1"
                  onClick={() => updateMut.mutate({ id: e.id })}
                  disabled={!editName.trim()}
                >{t('common.save')}</button>
                <button className="btn-ghost p-1" onClick={() => setEditingId(null)}><X size={12} /></button>
              </>
            ) : (
              <>
                <span className="flex-1 text-sm text-white">{e.name}</span>
                <button className="btn-ghost p-1" onClick={() => { setEditingId(e.id); setEditName(e.name) }}><Pencil size={12} /></button>
                <button className="btn-ghost p-1 text-red-400" onClick={() => deleteMut.mutate(e.id)}><Trash2 size={12} /></button>
              </>
            )}
          </div>
        ))}

        <div className="flex items-center gap-2 pt-2 border-t border-surface-3">
          <input
            className="input flex-1 text-sm py-1"
            value={newName}
            onChange={e => setNewName(e.target.value)}
            placeholder={placeholder}
            onKeyDown={e => e.key === 'Enter' && newName.trim() && createMut.mutate()}
          />
          <button
            className="btn-primary text-xs px-2 py-1 flex items-center gap-1 shrink-0"
            onClick={() => createMut.mutate()}
            disabled={!newName.trim() || createMut.isPending}
          >
            <Plus size={12} /> {t('common.add')}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Data Transfer ─────────────────────────────────────────────────────────────

function DataTransferSection() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [exporting, setExporting] = useState(false)
  const [exportingSpoolman, setExportingSpoolman] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<Record<string, number> | null>(null)
  const [importError, setImportError] = useState<string | null>(null)

  const handleExport = async () => {
    setExporting(true)
    try {
      const blob = await api.exportData()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `filament_manager_export_${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e: unknown) {
      alert('Export failed: ' + (e instanceof Error ? e.message : String(e)))
    } finally {
      setExporting(false)
    }
  }

  const handleExportSpoolman = async () => {
    setExportingSpoolman(true)
    try {
      const blob = await api.exportSpoolman()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `spoolman_export_${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e: unknown) {
      alert('Export failed: ' + (e instanceof Error ? e.message : String(e)))
    } finally {
      setExportingSpoolman(false)
    }
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setImporting(true)
    setImportResult(null)
    setImportError(null)
    try {
      const text = await file.text()
      const bundle = JSON.parse(text)
      const result = await api.importData(bundle)
      setImportResult(result.imported)
      qc.invalidateQueries()
    } catch (e: unknown) {
      setImportError(e instanceof Error ? e.message : String(e))
    } finally {
      setImporting(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-300 mb-1">{t('settings.dataTransfer.title')}</h3>
      <p className="text-xs text-gray-500 mb-4">{t('settings.dataTransfer.exportHint')}</p>

      <div className="flex flex-wrap gap-3 mb-4">
        <button
          onClick={handleExport}
          disabled={exporting}
          className="btn-primary flex items-center gap-2"
        >
          <Download size={14} />
          {exporting ? t('settings.dataTransfer.exporting') : t('settings.dataTransfer.exportBtn')}
        </button>

        <button
          onClick={handleExportSpoolman}
          disabled={exportingSpoolman}
          className="btn-ghost flex items-center gap-2"
        >
          <Download size={14} />
          {exportingSpoolman ? t('settings.dataTransfer.exporting') : t('settings.dataTransfer.exportSpoolmanBtn')}
          <span className="ml-1 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-yellow-900/60 text-yellow-400 border border-yellow-700">
            {t('settings.dataTransfer.experimental')}
          </span>
        </button>

        <label className={`btn-ghost flex items-center gap-2 cursor-pointer ${importing ? 'opacity-50 pointer-events-none' : ''}`}>
          <Upload size={14} />
          {importing ? t('settings.dataTransfer.importing') : t('settings.dataTransfer.importBtn')}
          <input
            ref={fileRef}
            type="file"
            accept=".json"
            className="hidden"
            onChange={handleFileChange}
            disabled={importing}
          />
        </label>
      </div>

      {importResult && (
        <div className="rounded-lg bg-green-900/30 border border-green-700 p-4 text-sm text-green-300 mb-3">
          <div className="flex items-center gap-2 font-medium mb-2">
            <CheckCircle size={16} /> {t('settings.dataTransfer.importSuccessTitle')}
          </div>
          <ul className="grid grid-cols-2 gap-x-6 gap-y-1 text-green-400">
            {Object.entries(importResult).map(([key, count]) => (
              <li key={key} className="flex justify-between">
                <span className="capitalize">{key.replace(/_/g, ' ')}</span>
                <span className="font-medium">{count}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {importError && (
        <div className="rounded-lg bg-red-900/30 border border-red-700 p-4 text-sm text-red-300 flex items-start gap-2 mb-3">
          <AlertCircle size={16} className="mt-0.5 shrink-0" />
          <span>{importError}</span>
        </div>
      )}

      <p className="text-xs text-gray-500">{t('settings.dataTransfer.importNote')}</p>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Settings() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<PrinterConfig | null>(null)

  const { data: printers = [] } = useQuery<PrinterConfig[]>({
    queryKey: ['printers'],
    queryFn: api.getPrinters,
  })
  const { data: haStatus } = useQuery({
    queryKey: ['ha-status'],
    queryFn: api.getHAStatus,
    refetchInterval: 15_000,
  })
  const { data: versionData } = useQuery({
    queryKey: ['version'],
    queryFn: api.getVersion,
    staleTime: Infinity,
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['printers'] })

  const createMut = useMutation({ mutationFn: api.createPrinter, onSuccess: () => { invalidate(); setShowForm(false) } })
  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: unknown }) => api.updatePrinter(id, data),
    onSuccess: () => { invalidate(); setEditing(null) },
  })
  const deleteMut = useMutation({ mutationFn: api.deletePrinter, onSuccess: invalidate })

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-bold">{t('settings.title')}</h2>
        {versionData && <span className="text-xs text-gray-500">v{versionData.version}</span>}
      </div>

      {/* HA Connection */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">{t('settings.ha.title')}</h3>
        <div className="flex items-center gap-2">
          {haStatus?.ha_available
            ? <><CheckCircle size={16} className="text-green-400" /><span className="text-sm text-green-400">{t('settings.ha.connected')}</span></>
            : <><AlertCircle size={16} className="text-red-400" /><span className="text-sm text-red-400">{t('settings.ha.disconnected')}</span></>
          }
        </div>
        <p className="text-xs text-gray-500 mt-2">{t('settings.ha.hint')}</p>
      </div>

      {/* Bambu Lab Cloud */}
      <BambuCloudSection />

      {/* Printers */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-300">{t('settings.printers.title')}</h3>
          <button className="btn-primary flex items-center gap-1.5 text-xs" onClick={() => setShowForm(true)}>
            <Plus size={13} /> {t('settings.printers.addPrinter')}
          </button>
        </div>
        {printers.length === 0 && (
          <p className="text-sm text-gray-500">{t('settings.printers.noPrintersHint')}</p>
        )}
        <div className="space-y-3">
          {printers.map(p => (
            <PrinterCard
              key={p.id}
              printer={p}
              onEdit={() => setEditing(p)}
              onDelete={() => {
                if (confirm(t('settings.printers.confirmDelete', { name: p.name }))) {
                  deleteMut.mutate(p.id)
                }
              }}
            />
          ))}
        </div>
      </div>

      {/* Brand Spool Weights */}
      <BrandWeightsSection />

      {/* Brands */}
      <NameListSection
        title={t('settings.brands.title')}
        queryKey="filament-brands"
        fetchFn={api.getFilamentBrands}
        createFn={api.createFilamentBrand}
        updateFn={api.updateFilamentBrand}
        deleteFn={api.deleteFilamentBrand}
        placeholder={t('settings.brands.placeholder')}
        noEntries={t('settings.brands.noEntries')}
      />

      {/* Materials */}
      <NameListSection
        title={t('settings.materials.title')}
        queryKey="filament-materials"
        fetchFn={api.getFilamentMaterials}
        createFn={api.createFilamentMaterial}
        updateFn={api.updateFilamentMaterial}
        deleteFn={api.deleteFilamentMaterial}
        placeholder={t('settings.materials.placeholder')}
        noEntries={t('settings.materials.noEntries')}
      />

      {/* Subtypes */}
      <NameListSection
        title={t('settings.subtypes.title')}
        queryKey="filament-subtypes"
        fetchFn={api.getFilamentSubtypes}
        createFn={api.createFilamentSubtype}
        updateFn={api.updateFilamentSubtype}
        deleteFn={api.deleteFilamentSubtype}
        placeholder={t('settings.subtypes.placeholder')}
        noEntries={t('settings.subtypes.noEntries')}
      />

      {/* Purchase Locations */}
      <NameListSection
        title={t('settings.purchaseLocations.title')}
        queryKey="purchase-locations"
        fetchFn={api.getPurchaseLocations}
        createFn={api.createPurchaseLocation}
        updateFn={api.updatePurchaseLocation}
        deleteFn={api.deletePurchaseLocation}
        placeholder={t('settings.purchaseLocations.placeholder')}
        noEntries={t('settings.purchaseLocations.noEntries')}
      />

      {/* Data Transfer */}
      <DataTransferSection />

      {(showForm || editing) && (
        <Modal>
          <PrinterForm
            initial={editing ?? undefined}
            onSave={data => {
              if (editing) updateMut.mutate({ id: editing.id, data })
              else createMut.mutate(data)
            }}
            onCancel={() => { setShowForm(false); setEditing(null) }}
          />
        </Modal>
      )}
    </div>
  )
}
