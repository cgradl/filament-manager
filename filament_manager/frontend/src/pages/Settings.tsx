import { useState, useRef, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api } from '../api'
import type { PrinterConfig, AMSTray, Spool, BrandSpoolWeight, FilamentSubtype, BambuCloudStatus, BambuCloudDevice, FilamentCatalog } from '../types'
import { Plus, Trash2, X, RefreshCw, CheckCircle, AlertCircle, Pencil, ChevronDown, ChevronUp, ChevronsUpDown, Download, Upload, Wifi, WifiOff } from 'lucide-react'
import Modal from '../components/Modal'
import BambuCloudSection from '../components/BambuCloudSection'

// ── Cloud Printer Form ────────────────────────────────────────────────────────

function CloudPrinterFormContent({
  initial,
  onSave,
  onCancel,
  cloudStatus,
  existingPrinters,
}: {
  initial?: PrinterConfig
  onSave: (data: Record<string, unknown>) => void
  onCancel: () => void
  cloudStatus: BambuCloudStatus | undefined
  existingPrinters: PrinterConfig[]
}) {
  const { t } = useTranslation()
  const [selectedSerial, setSelectedSerial] = useState(initial?.bambu_serial ?? '')
  const [name, setName] = useState(initial?.name ?? '')
  const [isActive, setIsActive] = useState(initial?.is_active ?? true)
  const [autoDeduct, setAutoDeduct] = useState(initial?.auto_deduct ?? false)
  const [activeAmsUnit, setActiveAmsUnit] = useState(1)

  const isConnected = cloudStatus?.status === 'connected'

  // Serials already configured as cloud printers (excluding the one being edited)
  const configuredSerials = new Set(
    existingPrinters
      .filter(p => p.bambu_source === 'cloud' && p.bambu_serial && p.id !== initial?.id)
      .map(p => p.bambu_serial!)
  )

  const { data: devices = [] } = useQuery<BambuCloudDevice[]>({
    queryKey: ['bambu-cloud-devices'],
    queryFn: api.getBambuCloudDevices,
    enabled: isConnected,
  })

  // Devices not yet configured as a cloud printer
  const availableDevices = (devices as BambuCloudDevice[]).filter(d => !configuredSerials.has(d.serial))

  const { data: liveStatus } = useQuery({
    queryKey: ['cloud-status', selectedSerial],
    queryFn: () => api.getBambuCloudPrinterStatus(selectedSerial),
    enabled: !!selectedSerial,
    refetchInterval: 10_000,
  })

  const { data: amsTrays } = useQuery({
    queryKey: ['cloud-ams', selectedSerial],
    queryFn: () => api.getBambuCloudPrinterAMS(selectedSerial),
    enabled: !!selectedSerial,
    refetchInterval: 10_000,
  })

  const handleSelectDevice = (serial: string, deviceName: string) => {
    setSelectedSerial(serial)
    if (!initial && !name) setName(deviceName)
  }

  // Detect AMS units from tray slot_keys
  const amsUnits = amsTrays
    ? Array.from(new Set(amsTrays.map(tr => {
        const m = tr.slot_key.match(/^ams(\d+)_/)
        return m ? parseInt(m[1]) : 1
      }))).sort()
    : []
  const visibleAmsUnit = amsUnits.includes(activeAmsUnit) ? activeAmsUnit : (amsUnits[0] ?? 1)

  const STATUS_LABELS: Record<string, string> = {
    print_stage: 'Stage', print_progress: 'Progress',
    remaining_time: 'Remaining', nozzle_temp: 'Nozzle',
    bed_temp: 'Bed', current_file: 'File',
  }
  const STATUS_UNITS: Record<string, string> = {
    nozzle_temp: '°C', bed_temp: '°C', print_progress: '%', remaining_time: ' min',
  }

  const statusEntries = liveStatus
    ? Object.entries(liveStatus as Record<string, string | null>).filter(([, v]) => v != null && v !== '')
    : []

  const canSave = isConnected && !!selectedSerial && !!name.trim()

  return (
    <>
      <div className="p-5 space-y-4">
        {!isConnected ? (
          <div className="flex items-start gap-2 text-xs text-yellow-400 bg-yellow-900/20 border border-yellow-800 rounded px-3 py-3">
            <AlertCircle size={13} className="mt-0.5 shrink-0" />
            <span>{t('settings.bambuCloud.notConnectedHint')}</span>
          </div>
        ) : (
          <>
            {/* Device picker — dropdown for new printers; locked serial for edit */}
            {!initial ? (
              <div>
                <label className="label">{t('settings.bambuCloud.selectDevice')}</label>
                {availableDevices.length === 0 && devices.length > 0 ? (
                  <p className="text-xs text-gray-500">All cloud printers are already configured.</p>
                ) : availableDevices.length === 0 ? (
                  <p className="text-xs text-gray-500">{t('settings.bambuCloud.noDevices')}</p>
                ) : (
                  <select
                    className="input w-full"
                    value={selectedSerial}
                    onChange={e => {
                      const serial = e.target.value
                      const device = availableDevices.find(d => d.serial === serial)
                      if (device) handleSelectDevice(serial, device.name)
                      else setSelectedSerial('')
                    }}
                  >
                    <option value="">{t('settings.bambuCloud.selectDevice')}…</option>
                    {availableDevices.map(d => (
                      <option key={d.serial} value={d.serial}>
                        {d.name}  {d.model}
                      </option>
                    ))}
                  </select>
                )}
              </div>
            ) : (
              <div className="flex items-center gap-2 text-xs bg-surface-3/40 rounded-lg px-3 py-2">
                <span className="text-gray-400">{t('settings.bambuCloud.serial')}:</span>
                <span className="font-mono text-gray-300">{'•'.repeat(8)}{initial.bambu_serial?.slice(-4)}</span>
                <span className="text-gray-600 text-[10px] ml-1">(locked)</span>
              </div>
            )}

            <div>
              <label className="label">{t('settings.printers.name')} *</label>
              <input className="input" value={name} onChange={e => setName(e.target.value)} placeholder="My Printer" />
            </div>

            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={isActive} onChange={e => setIsActive(e.target.checked)} />
              {t('settings.printers.monitorPrinter')}
            </label>

            {/* Live preview when a device is selected */}
            {selectedSerial && (
              <div className="bg-surface-3/40 rounded-xl p-3 space-y-3">
                {statusEntries.length > 0 ? (
                  <div className="grid grid-cols-3 gap-x-4 gap-y-1 text-xs text-gray-400">
                    {statusEntries.map(([key, val]) => (
                      <span key={key}>{STATUS_LABELS[key] ?? key}: <span className="text-white">{val}{STATUS_UNITS[key] ?? ''}</span></span>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-gray-500">{t('settings.bambuCloud.noStatusData')}</p>
                )}

                {amsTrays && amsTrays.length > 0 && (
                  <div className="border-t border-surface-3 pt-2">
                    <div className="flex items-center gap-2 mb-2">
                      <p className="text-xs font-medium text-gray-400">{t('settings.printers.amsAssignment')}</p>
                      {amsUnits.length > 1 && (
                        <div className="flex rounded overflow-hidden border border-surface-3 text-xs">
                          {amsUnits.map(u => (
                            <button
                              key={u}
                              onClick={() => setActiveAmsUnit(u)}
                              className={`px-2.5 py-0.5 transition-colors ${
                                visibleAmsUnit === u ? 'bg-blue-700 text-white' : 'text-gray-400 hover:text-gray-200'
                              }`}
                            >
                              AMS {u}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="space-y-1">
                      {amsTrays
                        .filter(tr => {
                          const m = tr.slot_key.match(/^ams(\d+)_/)
                          return m ? parseInt(m[1]) === visibleAmsUnit : true
                        })
                        .map(tr => (
                          <div key={tr.slot_key} className="flex items-center gap-2 bg-surface-3/40 rounded px-2 py-1 text-xs">
                            <span className="font-mono text-gray-400 w-20 shrink-0">{tr.slot_key}</span>
                            {tr.ha_color_hex ? (
                              <span className="w-3 h-3 rounded-full border border-white/20 shrink-0" style={{ background: tr.ha_color_hex }} />
                            ) : (
                              <span className="w-3 h-3 rounded-full bg-surface-3 border border-white/10 shrink-0" />
                            )}
                            <span className="text-gray-300 flex-1">{tr.ha_material ?? '—'}</span>
                            <span className="text-gray-400">{tr.ha_remaining != null ? `${tr.ha_remaining}%` : '—'}</span>
                          </div>
                        ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>

      <div className="flex justify-end gap-2 px-5 py-4 border-t border-surface-3">
        <button className="btn-ghost" onClick={onCancel}>{t('common.cancel')}</button>
        <button
          className="btn-primary"
          onClick={() => onSave({
            name: name.trim(),
            bambu_serial: selectedSerial,
            bambu_source: 'cloud',
            is_active: isActive,
            auto_deduct: autoDeduct,
          })}
          disabled={!canSave}
        >
          {t('common.save')}
        </button>
      </div>
    </>
  )
}

// ── Printer Form Modal ────────────────────────────────────────────────────────

function PrinterFormModal({
  initial,
  onSave,
  onCancel,
  cloudStatus,
  existingPrinters,
}: {
  initial?: PrinterConfig
  onSave: (data: Record<string, unknown>) => void
  onCancel: () => void
  cloudStatus: BambuCloudStatus | undefined
  existingPrinters: PrinterConfig[]
}) {
  const { t } = useTranslation()
  const title = initial ? t('settings.printers.editPrinter') : t('settings.printers.addPrinter')

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-surface-2 border border-surface-3 rounded-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-surface-3">
          <h2 className="font-semibold">{title}</h2>
          <button onClick={onCancel} className="btn-ghost p-1"><X size={16} /></button>
        </div>
        <CloudPrinterFormContent initial={initial} onSave={onSave} onCancel={onCancel} cloudStatus={cloudStatus} existingPrinters={existingPrinters} />
      </div>
    </div>
  )
}

// ── AMS Tray Panel ────────────────────────────────────────────────────────────

function AMSTrayPanel({ printer }: { printer: PrinterConfig }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [activeUnit, setActiveUnit] = useState(1)

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
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ['printer-ams'] })  // all printers — spool may have moved
      qc.invalidateQueries({ queryKey: ['spools'] })
      if (result.previous_slot) {
        const parts = result.previous_slot.split(':')
        const [prevPrinter, prevSlot] = parts.length === 2 ? parts : ['', parts[0]]
        const slotLabel = prevSlot.replace(/ams(\d+)_tray(\d+)/, 'AMS $1 Tray $2')
        const location = prevPrinter ? `${prevPrinter} / ${slotLabel}` : slotLabel
        alert(`Spool was already assigned to ${location} — it has been moved here.`)
      }
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

  const syncAllMut = useMutation({
    mutationFn: () => api.syncAMSWeights(printer.id),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ['spools'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
      const n = result.updated.length
      alert(n > 0 ? `Synced ${n} Bambu Lab spool${n > 1 ? 's' : ''}` : 'No Bambu Lab spools to sync')
    },
    onError: (err) => {
      alert(err instanceof Error ? err.message : 'Sync all failed')
    },
  })

  if (isLoading) return <p className="text-xs text-gray-500 py-2">{t('settings.printers.loadingAMS')}</p>
  if (!trays?.length) return <p className="text-xs text-gray-500 py-2">{t('settings.printers.noAMSData')}</p>

  const units = Array.from(new Set(trays.map(t => t.ams_id))).sort()
  const visibleUnit = units.includes(activeUnit) ? activeUnit : units[0]

  return (
    <div className="mt-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <p className="text-xs font-medium text-gray-400">{t('settings.printers.amsAssignment')}</p>
          {units.length > 1 && (
            <div className="flex rounded overflow-hidden border border-surface-3 text-xs">
              {units.map(u => (
                <button
                  key={u}
                  onClick={() => setActiveUnit(u)}
                  className={`px-2.5 py-0.5 transition-colors ${
                    visibleUnit === u ? 'bg-blue-700 text-white' : 'text-gray-400 hover:text-gray-200'
                  }`}
                >
                  AMS {u}
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            className="btn-ghost px-2 py-0.5 text-xs"
            onClick={() => syncAllMut.mutate()}
            disabled={syncAllMut.isPending}
            title="Sync remaining % for all Bambu Lab spools"
          >
            {syncAllMut.isPending ? <RefreshCw size={10} className="animate-spin" /> : t('settings.printers.syncAll')}
          </button>
          <button className="btn-ghost p-1" onClick={() => refetch()} title="Refresh display">
            <RefreshCw size={11} />
          </button>
        </div>
      </div>

      <div className="space-y-1.5">
        {trays.filter(t => t.ams_id === visibleUnit).map(tray => (
          <AMSTrayRow
            key={tray.slot_key}
            tray={tray}
            spools={spools}
            onAssign={(spoolId) => assignMut.mutate({ slot: tray.slot_key, spoolId })}
            saving={assignMut.isPending}
            onSyncWeight={() => syncSlotMut.mutate(tray.slot_key)}
            syncingWeight={syncingSlot === tray.slot_key}
            canSync={tray.ha_remaining != null && parseFloat(tray.ha_remaining) >= 0}
          />
        ))}
      </div>
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
  canSync,
}: {
  tray: AMSTray
  spools: Spool[]
  onAssign: (spoolId: number | null) => void
  saving: boolean
  onSyncWeight: () => void
  syncingWeight: boolean
  canSync: boolean
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
        {tray.ha_remaining != null ? `${Math.round(parseFloat(tray.ha_remaining))}%` : '—'}
      </span>

      <select
        className="input text-xs flex-1 py-1 min-w-0"
        value={selectedId ?? ''}
        disabled={saving}
        onChange={e => onAssign(e.target.value ? Number(e.target.value) : null)}
      >
        <option value="">{t('settings.printers.unassigned')}</option>
        {spools.filter(s => Math.round(s.remaining_pct) > 0).map(s => (
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
          {canSync ? (
            <button
              className="btn-ghost p-1 shrink-0 text-gray-400 hover:text-white"
              onClick={onSyncWeight}
              disabled={syncingWeight}
              title="Sync weight from AMS"
            >
              <RefreshCw size={10} className={syncingWeight ? 'animate-spin' : ''} />
            </button>
          ) : (
            <span className="w-6 h-6 shrink-0" />
          )}
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

  const { data: status, refetch, isFetching } = useQuery({
    queryKey: ['printer-status', printer.id],
    queryFn: () => api.getPrinterStatus(printer.id),
    refetchInterval: 30_000,
    enabled: printer.is_active,
  })

  const stage = (status as Record<string, string | null> | undefined)?.print_stage?.toLowerCase() ?? 'unknown'
  const isPrinting = ['printing', 'auto_bed_leveling', 'heatbed_preheating'].includes(stage)

  const LABELS: Record<string, string> = {
    print_progress: 'Progress', remaining_time: 'Remaining',
    nozzle_temp: 'Nozzle', bed_temp: 'Bed', current_file: 'File',
  }
  const UNITS: Record<string, string> = {
    nozzle_temp: '°C', bed_temp: '°C', print_progress: '%', remaining_time: ' min',
  }

  return (
    <div className="bg-surface-2 border border-surface-3 rounded-xl p-4">
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2">
            <p className="font-semibold text-white">{printer.name}</p>
          </div>
          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
            <span className={`text-xs px-2 py-0.5 rounded-full ${
              isPrinting ? 'bg-blue-900 text-blue-300' :
              stage === 'finish' ? 'bg-green-900 text-green-300' :
              'bg-surface-3 text-gray-400'
            }`}>{stage}</span>
          </div>
        </div>
        <div className="flex gap-1 shrink-0">
          <button className="btn-ghost p-1" onClick={() => refetch()} title="Refresh">
            <RefreshCw size={12} className={isFetching ? 'animate-spin' : ''} />
          </button>
          <button className="btn-ghost p-1" onClick={onEdit}><Pencil size={12} /></button>
          <button className="btn-ghost p-1 text-red-400" onClick={onDelete}><Trash2 size={12} /></button>
        </div>
      </div>

      {/* Status values */}
      {status && (
        <div className="grid grid-cols-3 gap-x-4 gap-y-1 text-xs text-gray-400 mb-3">
          {Object.entries(status as unknown as Record<string, string | null>).map(([key, val]) => (
            val && key !== 'print_stage' ? (
              key === 'current_file' ? (
                <span key={key} className="col-span-3 flex gap-1 min-w-0">
                  <span className="shrink-0">{LABELS[key]}:</span>
                  <span className="text-white truncate" title={val}>{val}</span>
                </span>
              ) : (
                <span key={key}>{LABELS[key] ?? key}: <span className="text-white">{val}{UNITS[key] ?? ''}</span></span>
              )
            ) : null
          ))}
        </div>
      )}

      {/* AMS tray assignment — always visible */}
      <AMSTrayPanel printer={printer} />
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
      <h3 className="text-sm font-semibold text-gray-300 mb-1">{t('settings.brandWeights.title')}</h3>
      <p className="text-xs text-gray-500 mb-3">{t('settings.brandWeights.hint')}</p>

      <div className="card space-y-2">
        <div className="flex items-center gap-2 pb-2 border-b border-surface-3">
          <input
            className="input flex-1 text-sm py-1"
            value={newBrand}
            onChange={e => setNewBrand(e.target.value)}
            placeholder={t('settings.brandWeights.brandPlaceholder')}
            onKeyDown={e => e.key === 'Enter' && newBrand.trim() && newWeight && createMut.mutate()}
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
                  autoFocus
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
                <button className="btn-ghost p-1 text-red-400" onClick={() => deleteMut.mutate(e.id)}><Trash2 size={12} /></button>
              </>
            )}
          </div>
        ))}
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
        <div className="flex items-center gap-2 pb-2 border-b border-surface-3">
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
  const [importingCloud, setImportingCloud] = useState(false)
  const [cloudImportResult, setCloudImportResult] = useState<{ imported: number; skipped: number; total: number } | null>(null)
  const [cloudImportError, setCloudImportError] = useState<string | null>(null)

  const { data: cloudStatus } = useQuery({
    queryKey: ['bambu-cloud-status'],
    queryFn: api.getBambuCloudStatus,
  })
  const cloudConnected = cloudStatus?.status === 'connected'

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

  const handleCloudImport = async () => {
    setImportingCloud(true)
    setCloudImportResult(null)
    setCloudImportError(null)
    try {
      const result = await api.bambuCloudImportPrints()
      setCloudImportResult({ imported: result.imported, skipped: result.skipped, total: result.total })
      qc.invalidateQueries({ queryKey: ['prints'] })
      qc.invalidateQueries({ queryKey: ['prints-count'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
    } catch (e: unknown) {
      setCloudImportError(e instanceof Error ? e.message : String(e))
    } finally {
      setImportingCloud(false)
    }
  }

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-300 mb-1">{t('settings.dataTransfer.title')}</h3>
      <p className="text-xs text-gray-500 mb-4">{t('settings.dataTransfer.exportHint')}</p>

      <div className="flex flex-wrap gap-3 mb-4">
        <button onClick={handleExport} disabled={exporting} className="btn-primary flex items-center gap-2">
          <Download size={14} />
          {exporting ? t('settings.dataTransfer.exporting') : t('settings.dataTransfer.exportBtn')}
        </button>

        <button onClick={handleExportSpoolman} disabled={exportingSpoolman} className="btn-ghost flex items-center gap-2">
          <Download size={14} />
          {exportingSpoolman ? t('settings.dataTransfer.exporting') : t('settings.dataTransfer.exportSpoolmanBtn')}
          <span className="ml-1 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-yellow-900/60 text-yellow-400 border border-yellow-700">
            {t('settings.dataTransfer.experimental')}
          </span>
        </button>

        <label className={`btn-ghost flex items-center gap-2 cursor-pointer ${importing ? 'opacity-50 pointer-events-none' : ''}`}>
          <Upload size={14} />
          {importing ? t('settings.dataTransfer.importing') : t('settings.dataTransfer.importBtn')}
          <input ref={fileRef} type="file" accept=".json" className="hidden" onChange={handleFileChange} disabled={importing} />
        </label>

        <button
          onClick={handleCloudImport}
          disabled={importingCloud || !cloudConnected}
          title={!cloudConnected ? 'Connect to Bambu Cloud first (Settings → Bambu Cloud)' : undefined}
          className="btn-ghost flex items-center gap-2 disabled:opacity-40"
        >
          <Download size={14} />
          {importingCloud ? t('settings.dataTransfer.importingCloud') : t('settings.dataTransfer.importCloudBtn')}
        </button>
      </div>

      {cloudImportResult && (
        <div className="rounded-lg bg-green-900/30 border border-green-700 p-3 text-sm text-green-300 mb-3">
          <CheckCircle size={14} className="inline mr-1.5 mb-0.5" />
          {t('settings.dataTransfer.importCloudResult', cloudImportResult)}
        </div>
      )}

      {cloudImportError && (
        <div className="rounded-lg bg-red-900/30 border border-red-700 p-3 text-sm text-red-300 flex items-start gap-2 mb-3">
          <AlertCircle size={14} className="mt-0.5 shrink-0" />
          <span>{t('settings.dataTransfer.importCloudError', { error: cloudImportError })}</span>
        </div>
      )}

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

// ── Filament Catalog Section ──────────────────────────────────────────────────

type CatalogEntry = Omit<FilamentCatalog, 'id' | 'created_at' | 'updated_at'>

const EMPTY_CATALOG: CatalogEntry = {
  brand: '', material: '', subtype: null, subtype2: null,
  color_name: '', color_hex: '#888888', article_number: null,
}

type CatalogSortKey = 'brand' | 'material' | 'subtype' | 'subtype2' | 'color_name' | 'color_hex' | 'article_number'
type CatalogSortDir = 'asc' | 'desc'

function CatalogSortIcon({ col, sort }: { col: CatalogSortKey; sort: { key: CatalogSortKey; dir: CatalogSortDir } }) {
  if (sort.key !== col) return <ChevronsUpDown size={12} className="text-gray-600" />
  return sort.dir === 'asc'
    ? <ChevronUp size={12} className="text-accent" />
    : <ChevronDown size={12} className="text-accent" />
}

// Module-level component — NOT defined inside FilamentDataSection to avoid remount on every render
function CatalogEditRow({ entry, editForm, setEditForm, onSave, onCancel, brands, materials, subtypes }: {
  entry: FilamentCatalog
  editForm: CatalogEntry
  setEditForm: (f: CatalogEntry) => void
  onSave: () => void
  onCancel: () => void
  brands: FilamentSubtype[]
  materials: FilamentSubtype[]
  subtypes: FilamentSubtype[]
}) {
  const { t } = useTranslation()
  const set = (k: keyof CatalogEntry, v: string) => setEditForm({ ...editForm, [k]: v })
  const canSave = editForm.brand.trim() && editForm.material.trim() && editForm.color_name.trim()
  return (
    <tr className="border-b border-surface-3 bg-surface-2">
      <td className="px-2 py-1">
        <div className="flex gap-1">
          <button className="btn-primary text-xs px-2 py-0.5" onClick={onSave} disabled={!canSave}>{t('common.save')}</button>
          <button className="btn-ghost text-xs px-2 py-0.5" onClick={onCancel}>{t('common.cancel')}</button>
        </div>
      </td>
      <td className="px-2 py-1"><select className="input text-xs py-0.5 w-full" value={editForm.brand} onChange={e => set('brand', e.target.value)}>
        <option value="">—</option>{brands.map(b => <option key={b.id} value={b.name}>{b.name}</option>)}
      </select></td>
      <td className="px-2 py-1"><select className="input text-xs py-0.5 w-full" value={editForm.material} onChange={e => set('material', e.target.value)}>
        <option value="">—</option>{materials.map(m => <option key={m.id} value={m.name}>{m.name}</option>)}
      </select></td>
      <td className="px-2 py-1"><select className="input text-xs py-0.5 w-full" value={editForm.subtype ?? ''} onChange={e => set('subtype', e.target.value)}>
        <option value="">—</option>{subtypes.map(s => <option key={s.id} value={s.name}>{s.name}</option>)}
      </select></td>
      <td className="px-2 py-1"><select className="input text-xs py-0.5 w-full" value={editForm.subtype2 ?? ''} onChange={e => set('subtype2', e.target.value)}>
        <option value="">—</option>{subtypes.map(s => <option key={s.id} value={s.name}>{s.name}</option>)}
      </select></td>
      <td className="px-2 py-1"><input className="input text-xs py-0.5 w-full" value={editForm.color_name} onChange={e => set('color_name', e.target.value)} /></td>
      <td className="px-2 py-1">
        <div className="flex items-center gap-1">
          <input type="color" className="w-6 h-6 rounded cursor-pointer border border-surface-3 bg-transparent p-0 shrink-0" value={editForm.color_hex} onChange={e => set('color_hex', e.target.value)} />
          <input className="input text-xs py-0.5 w-20 font-mono" value={editForm.color_hex} onChange={e => set('color_hex', e.target.value)} maxLength={7} />
        </div>
      </td>
      <td className="px-2 py-1"><input className="input text-xs py-0.5 w-full" value={editForm.article_number ?? ''} onChange={e => set('article_number', e.target.value)} /></td>
    </tr>
  )
}

function FilamentDataSection() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState<CatalogEntry>({ ...EMPTY_CATALOG })
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editForm, setEditForm] = useState<CatalogEntry>({ ...EMPTY_CATALOG })
  const [importResult, setImportResult] = useState<{ added: number; updated: number } | null>(null)
  const csvInputRef = useRef<HTMLInputElement>(null)
  const [sort, setSort] = useState<{ key: CatalogSortKey; dir: CatalogSortDir }>({ key: 'brand', dir: 'asc' })
  const [filters, setFilters] = useState<Partial<Record<CatalogSortKey, string>>>({})

  const setFilter = (k: CatalogSortKey, v: string) => setFilters(f => ({ ...f, [k]: v }))
  const toggleSort = (k: CatalogSortKey) =>
    setSort(s => s.key === k ? { key: k, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key: k, dir: 'asc' })

  const { data: catalog = [] } = useQuery<FilamentCatalog[]>({
    queryKey: ['filament-catalog'],
    queryFn: api.getFilamentCatalog,
  })
  const { data: brands = [] } = useQuery<FilamentSubtype[]>({
    queryKey: ['filament-brands'], queryFn: api.getFilamentBrands,
  })
  const { data: materials = [] } = useQuery<FilamentSubtype[]>({
    queryKey: ['filament-materials'], queryFn: api.getFilamentMaterials,
  })
  const { data: subtypes = [] } = useQuery<FilamentSubtype[]>({
    queryKey: ['filament-subtypes'], queryFn: api.getFilamentSubtypes,
  })

  const inv = () => qc.invalidateQueries({ queryKey: ['filament-catalog'] })

  const createMut = useMutation({
    mutationFn: () => api.createFilamentCatalog({
      ...form,
      subtype: form.subtype || null,
      subtype2: form.subtype2 || null,
      article_number: form.article_number || null,
    }),
    onSuccess: () => { inv(); setForm({ ...EMPTY_CATALOG }); setShowAdd(false) },
  })
  const updateMut = useMutation({
    mutationFn: (id: number) => api.updateFilamentCatalog(id, {
      ...editForm,
      subtype: editForm.subtype || null,
      subtype2: editForm.subtype2 || null,
      article_number: editForm.article_number || null,
    }),
    onSuccess: () => { inv(); setEditingId(null) },
  })
  const deleteMut = useMutation({ mutationFn: api.deleteFilamentCatalog, onSuccess: inv })

  const importMut = useMutation({
    mutationFn: api.importFilamentCatalog,
    onSuccess: (result) => { inv(); setImportResult(result) },
  })

  const handleCsvFile = (file: File) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      // Strip UTF-8 BOM if present (Excel exports often include it)
      let text = (e.target?.result as string).replace(/^\uFEFF/, '')
      const lines = text.split(/\r?\n/).filter(l => l.trim())
      if (lines.length < 2) return
      // Detect delimiter from header line
      const header = lines[0]
      const delim = header.includes(';') ? ';' : ','
      // Strip surrounding quotes and lowercase — handles Excel-quoted CSV headers
      const unquote = (s: string) => s.trim().replace(/^["']|["']$/g, '')
      const cols = header.split(delim).map(c => unquote(c).toLowerCase())
      // Map known column names to our fields
      const idx = (names: string[]) => names.map(n => cols.findIndex(c => c === n)).find(i => i >= 0) ?? -1
      const iBrand   = idx(['marke', 'brand'])
      const iMat     = idx(['material'])
      const iSub1    = idx(['subtype', 'subtype 1', 'subtype1'])
      const iSub2    = idx(['subtype 2', 'subtype2'])
      const iColor   = idx(['color name', 'colorname', 'farbe', 'color'])
      const iArticle = idx(['artikel nummer', 'artikel numner', 'article number', 'article_number', 'articlenumber'])
      const iHex     = idx(['hex-code', 'hex code', 'hexcode', 'color_hex', 'color hex'])
      const rows = lines.slice(1).map(line => {
        const cells = line.split(delim).map(c => unquote(c))
        return {
          brand:          iBrand   >= 0 ? cells[iBrand]   ?? '' : '',
          material:       iMat     >= 0 ? cells[iMat]     ?? '' : '',
          subtype:        iSub1    >= 0 ? cells[iSub1]    || null : null,
          subtype2:       iSub2    >= 0 ? cells[iSub2]    || null : null,
          color_name:     iColor   >= 0 ? cells[iColor]   ?? '' : '',
          color_hex:      iHex     >= 0 ? (cells[iHex] || '#888888') : '#888888',
          article_number: iArticle >= 0 ? cells[iArticle] || null : null,
        }
      }).filter(r => r.brand && r.material && r.color_name)
      if (rows.length > 0) {
        importMut.mutate(rows)
      } else {
        alert(t('settings.filamentCatalog.importNoRows'))
      }
    }
    reader.readAsText(file, 'UTF-8')
  }

  const startEdit = (e: FilamentCatalog) => {
    setEditingId(e.id)
    setEditForm({ brand: e.brand, material: e.material, subtype: e.subtype ?? '', subtype2: e.subtype2 ?? '', color_name: e.color_name, color_hex: e.color_hex, article_number: e.article_number ?? '' })
  }

  const canAdd = form.brand.trim() && form.material.trim() && form.color_name.trim()

  const processed = useMemo(() => {
    let rows = [...catalog]
    for (const [k, v] of Object.entries(filters)) {
      if (!v) continue
      const lower = v.toLowerCase()
      rows = rows.filter(e => {
        const val = e[k as keyof FilamentCatalog]
        if (val == null) return false
        return String(val).toLowerCase().includes(lower)
      })
    }
    rows.sort((a, b) => {
      const av = a[sort.key] ?? ''
      const bv = b[sort.key] ?? ''
      const cmp = String(av).localeCompare(String(bv))
      return sort.dir === 'asc' ? cmp : -cmp
    })
    return rows
  }, [catalog, sort, filters])

  const hasFilter = Object.values(filters).some(v => v)

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-300">{t('settings.filamentCatalog.title')}</h3>
        <div className="flex items-center gap-2">
          <input
            ref={csvInputRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if (f) { handleCsvFile(f); e.target.value = '' } }}
          />
          <button
            className="btn-ghost text-xs px-2 py-1 flex items-center gap-1"
            onClick={() => { setImportResult(null); csvInputRef.current?.click() }}
            disabled={importMut.isPending}
          >
            <Upload size={12} /> {t('settings.filamentCatalog.importCsv')}
          </button>
          <button
            className="btn-primary text-xs px-2 py-1 flex items-center gap-1"
            onClick={() => { setShowAdd(v => !v); setEditingId(null) }}
          >
            <Plus size={12} /> {t('common.add')}
          </button>
        </div>
      </div>

      {importResult && (
        <div className="text-xs px-3 py-2 rounded bg-green-900/40 border border-green-700/50 text-green-300 flex items-center justify-between">
          <span>{t('settings.filamentCatalog.importResult', { added: importResult.added, updated: importResult.updated })}</span>
          <button className="ml-4 text-green-400 hover:text-white" onClick={() => setImportResult(null)}>✕</button>
        </div>
      )}

      {/* Add form — shown above the table, not inside it */}
      {showAdd && (
        <div className="card space-y-3">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div>
              <label className="label text-xs">{t('settings.filamentCatalog.brand')} *</label>
              <select className="input text-xs py-1 w-full" value={form.brand} onChange={e => setForm(f => ({ ...f, brand: e.target.value }))}>
                <option value="">—</option>
                {brands.map(b => <option key={b.id} value={b.name}>{b.name}</option>)}
              </select>
            </div>
            <div>
              <label className="label text-xs">{t('settings.filamentCatalog.material')} *</label>
              <select className="input text-xs py-1 w-full" value={form.material} onChange={e => setForm(f => ({ ...f, material: e.target.value }))}>
                <option value="">—</option>
                {materials.map(m => <option key={m.id} value={m.name}>{m.name}</option>)}
              </select>
            </div>
            <div>
              <label className="label text-xs">{t('settings.filamentCatalog.subtype')}</label>
              <select className="input text-xs py-1 w-full" value={form.subtype ?? ''} onChange={e => setForm(f => ({ ...f, subtype: e.target.value }))}>
                <option value="">—</option>
                {subtypes.map(s => <option key={s.id} value={s.name}>{s.name}</option>)}
              </select>
            </div>
            <div>
              <label className="label text-xs">{t('settings.filamentCatalog.subtype2')}</label>
              <select className="input text-xs py-1 w-full" value={form.subtype2 ?? ''} onChange={e => setForm(f => ({ ...f, subtype2: e.target.value }))}>
                <option value="">—</option>
                {subtypes.map(s => <option key={s.id} value={s.name}>{s.name}</option>)}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div>
              <label className="label text-xs">{t('settings.filamentCatalog.colorName')} *</label>
              <input className="input text-xs py-1 w-full" value={form.color_name} onChange={e => setForm(f => ({ ...f, color_name: e.target.value }))} placeholder="Black" />
            </div>
            <div>
              <label className="label text-xs">{t('settings.filamentCatalog.colorHex')}</label>
              <div className="flex items-center gap-2">
                <input type="color" className="w-8 h-8 rounded cursor-pointer border border-surface-3 bg-transparent p-0.5 shrink-0" value={form.color_hex} onChange={e => setForm(f => ({ ...f, color_hex: e.target.value }))} />
                <input className="input text-xs py-1 font-mono flex-1" value={form.color_hex} onChange={e => setForm(f => ({ ...f, color_hex: e.target.value }))} maxLength={7} />
              </div>
            </div>
            <div>
              <label className="label text-xs">{t('settings.filamentCatalog.articleNumber')}</label>
              <input className="input text-xs py-1 w-full" value={form.article_number ?? ''} onChange={e => setForm(f => ({ ...f, article_number: e.target.value }))} placeholder="BL-PLA-BK-1KG" />
            </div>
            <div className="flex items-end gap-2">
              <button className="btn-primary text-xs px-3 py-1.5" onClick={() => createMut.mutate()} disabled={!canAdd || createMut.isPending}>
                {t('common.add')}
              </button>
              <button className="btn-ghost text-xs px-3 py-1.5" onClick={() => { setShowAdd(false); setForm({ ...EMPTY_CATALOG }) }}>
                {t('common.cancel')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-surface-3">
        <table className="w-full text-xs text-left" style={{ minWidth: '700px' }}>
          <thead>
            <tr className="border-b border-surface-3">
              <th className="px-3 py-2 w-16" />
              {([
                ['brand',          t('settings.filamentCatalog.brand')],
                ['material',       t('settings.filamentCatalog.material')],
                ['subtype',        t('settings.filamentCatalog.subtype')],
                ['subtype2',       t('settings.filamentCatalog.subtype2')],
                ['color_name',     t('settings.filamentCatalog.colorName')],
                ['color_hex',      t('settings.filamentCatalog.colorHex')],
                ['article_number', t('settings.filamentCatalog.articleNumber')],
              ] as [CatalogSortKey, string][]).map(([key, label]) => (
                <th
                  key={key}
                  className="px-3 py-2 text-gray-400 font-medium whitespace-nowrap cursor-pointer select-none hover:text-white"
                  onClick={() => toggleSort(key)}
                >
                  <span className="flex items-center gap-1">
                    {label} <CatalogSortIcon col={key} sort={sort} />
                  </span>
                </th>
              ))}
            </tr>
            <tr className="border-b border-surface-3 bg-surface-3/30">
              <td className="px-2 py-1">
                <button
                  className="text-xs text-gray-500 hover:text-white"
                  onClick={() => setFilters({})}
                  title={t('common.clear')}
                >✕</button>
              </td>
              {(['brand', 'material', 'subtype', 'subtype2', 'color_name', 'color_hex', 'article_number'] as CatalogSortKey[]).map(key => (
                <td key={key} className="px-2 py-1">
                  <input
                    className="w-full bg-surface-3 rounded px-2 py-0.5 text-xs text-gray-100 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-accent"
                    placeholder="filter…"
                    value={filters[key] ?? ''}
                    onChange={e => setFilter(key, e.target.value)}
                  />
                </td>
              ))}
            </tr>
          </thead>
          <tbody>
            {processed.length === 0 && (
              <tr><td colSpan={8} className="text-xs text-gray-500 py-4 px-3">
                {hasFilter ? t('settings.filamentCatalog.noResults') : t('settings.filamentCatalog.noEntries')}
              </td></tr>
            )}
            {processed.map(entry => editingId === entry.id ? (
              <CatalogEditRow
                key={entry.id}
                entry={entry}
                editForm={editForm}
                setEditForm={setEditForm}
                onSave={() => updateMut.mutate(entry.id)}
                onCancel={() => setEditingId(null)}
                brands={brands}
                materials={materials}
                subtypes={subtypes}
              />
            ) : (
              <tr key={entry.id} className="border-b border-surface-3/50 hover:bg-surface-3/40 transition-colors">
                <td className="px-3 py-2 whitespace-nowrap">
                  <div className="flex gap-1">
                    <button className="btn-ghost p-1 text-gray-400 hover:text-white" onClick={() => startEdit(entry)}><Pencil size={12} /></button>
                    <button className="btn-ghost p-1 text-red-400 hover:text-red-300" onClick={() => deleteMut.mutate(entry.id)}><Trash2 size={12} /></button>
                  </div>
                </td>
                <td className="px-3 py-2 font-medium text-white whitespace-nowrap">{entry.brand}</td>
                <td className="px-3 py-2 whitespace-nowrap">{entry.material}</td>
                <td className="px-3 py-2 whitespace-nowrap text-gray-400">{entry.subtype ?? '—'}</td>
                <td className="px-3 py-2 whitespace-nowrap text-gray-400">{entry.subtype2 ?? '—'}</td>
                <td className="px-3 py-2 whitespace-nowrap">
                  <span className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full shrink-0 ring-1 ring-white/10" style={{ background: entry.color_hex }} />
                    {entry.color_name}
                  </span>
                </td>
                <td className="px-3 py-2 whitespace-nowrap font-mono text-gray-400">{entry.color_hex}</td>
                <td className="px-3 py-2 whitespace-nowrap text-gray-400">{entry.article_number ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

type MainTab = 'printers' | 'data' | 'transfer' | 'experiments'
type DataSubTab = 'brandWeights' | 'brands' | 'materials' | 'subtypes' | 'locations' | 'storageLocations' | 'filamentData'

// ── Cloud printer live status (used in Experiments tab) ───────────────────────

function CloudPrinterStatus({ printer }: { printer: PrinterConfig }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [reconnecting, setReconnecting] = useState(false)

  const { data: status, refetch, isFetching } = useQuery({
    queryKey: ['cloud-status', printer.bambu_serial],
    queryFn: () => api.getBambuCloudPrinterStatus(printer.bambu_serial!),
    refetchInterval: 10_000,
    enabled: !!printer.bambu_serial,
  })

  const { data: trays, refetch: refetchTrays } = useQuery({
    queryKey: ['cloud-ams', printer.bambu_serial],
    queryFn: () => api.getBambuCloudPrinterAMS(printer.bambu_serial!),
    refetchInterval: 10_000,
    enabled: !!printer.bambu_serial,
  })

  const { data: debugInfo, refetch: refetchDebug } = useQuery({
    queryKey: ['cloud-debug'],
    queryFn: () => api.getBambuCloudDebug(),
    refetchInterval: 10_000,
  })
  const rawCache = printer.bambu_serial && debugInfo?.printer_status_cache
    ? debugInfo.printer_status_cache[printer.bambu_serial] ?? {}
    : {}
  const rawAmsCache = printer.bambu_serial && debugInfo?.ams_cache
    ? debugInfo.ams_cache[printer.bambu_serial] ?? {}
    : {}

  // MQTT connection status for this serial
  const mqttInfo = printer.bambu_serial && debugInfo?.mqtt_clients
    ? debugInfo.mqtt_clients[printer.bambu_serial] ?? null
    : null
  const mqttConnected = mqttInfo?.connected === true

  const handleReconnect = async () => {
    setReconnecting(true)
    try {
      await api.bambuCloudReconnect()
      // Poll debug endpoint until MQTT shows connected for this serial (max 15s)
      const serial = printer.bambu_serial
      if (serial) {
        for (let i = 0; i < 15; i++) {
          await new Promise(r => setTimeout(r, 1000))
          const dbg = await api.getBambuCloudDebug()
          if (dbg.mqtt_clients?.[serial]?.connected) break
        }
      }
      await Promise.all([refetch(), refetchTrays(), refetchDebug()])
      qc.invalidateQueries({ queryKey: ['printer-ams'] })
    } finally {
      setReconnecting(false)
    }
  }

  const handleRefreshAll = () => {
    refetch()
    refetchTrays()
    refetchDebug()
  }

  const [activeUnit, setActiveUnit] = useState(1)
  const [showRaw, setShowRaw] = useState(false)
  const [downloadingTasks, setDownloadingTasks] = useState(false)

  const handleDownloadTasks = async () => {
    if (!printer.bambu_serial) return
    setDownloadingTasks(true)
    try {
      const data = await api.getBambuCloudTasksRaw(printer.bambu_serial)
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `tasks_${printer.bambu_serial}.json`
      a.click()
      URL.revokeObjectURL(url)
    } finally {
      setDownloadingTasks(false)
    }
  }

  const LABELS: Record<string, string> = {
    print_stage: 'Stage', print_progress: 'Progress',
    remaining_time: 'Remaining', nozzle_temp: 'Nozzle',
    bed_temp: 'Bed', current_file: 'File',
    active_tray: 'Active tray',
  }
  const UNITS: Record<string, string> = {
    nozzle_temp: '°C', bed_temp: '°C', print_progress: '%', remaining_time: ' min',
  }

  const statusEntries = status
    ? Object.entries(status as Record<string, string | null>).filter(([, v]) => v != null && v !== '')
    : []

  // Group AMS trays by unit
  const amsUnits = trays
    ? Array.from(new Set(trays.map(tr => {
        const m = tr.slot_key.match(/^ams(\d+)_/)
        return m ? parseInt(m[1]) : 1
      }))).sort()
    : []
  const visibleUnit = amsUnits.includes(activeUnit) ? activeUnit : (amsUnits[0] ?? 1)

  return (
    <div className="bg-surface-2 border border-surface-3 rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="font-semibold text-white">{printer.name}</p>
          <div className="flex items-center gap-2 mt-0.5">
            <p className="text-xs text-gray-500">{'•'.repeat(8)}{printer.bambu_serial?.slice(-4) ?? '—'}</p>
            {/* MQTT connection indicator */}
            {mqttInfo !== null && (
              mqttConnected
                ? <span className="flex items-center gap-1 text-[10px] text-green-400"><Wifi size={10} /> MQTT</span>
                : <span className="flex items-center gap-1 text-[10px] text-red-400"><WifiOff size={10} /> not connected</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            className="btn-ghost p-1 text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1"
            onClick={handleDownloadTasks}
            disabled={downloadingTasks}
            title="Download full task list from Bambu Cloud as JSON"
          >
            <Download size={11} className={downloadingTasks ? 'animate-pulse' : ''} />
            {downloadingTasks ? 'Fetching…' : 'Tasks'}
          </button>
          <button
            className="btn-ghost p-1 text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
            onClick={handleReconnect}
            disabled={reconnecting}
            title="Reconnect MQTT and request fresh data"
          >
            <RefreshCw size={11} className={reconnecting ? 'animate-spin' : ''} />
            {reconnecting ? 'Connecting…' : 'Reconnect'}
          </button>
          <button className="btn-ghost p-1" onClick={handleRefreshAll} title="Refresh cache">
            <RefreshCw size={12} className={isFetching ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Printer sensor values */}
      {statusEntries.length > 0 ? (
        <div className="grid grid-cols-3 gap-x-4 gap-y-1 text-xs text-gray-400 mb-3">
          {statusEntries.map(([key, val]) => (
            key === 'current_file' ? (
              <span key={key} className="col-span-3 flex gap-1 min-w-0">
                <span className="shrink-0">{LABELS[key]}:</span>
                <span className="text-white truncate" title={val ?? ''}>{val}</span>
              </span>
            ) : (
              <span key={key}>{LABELS[key] ?? key}: <span className="text-white">{val}{UNITS[key] ?? ''}</span></span>
            )
          ))}
        </div>
      ) : (
        <p className="text-xs text-gray-500 mb-3">{t('settings.bambuCloud.noStatusData')}</p>
      )}

      {/* AMS tray values — grouped by unit */}
      {trays && trays.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <p className="text-xs font-medium text-gray-400">{t('settings.printers.amsAssignment')}</p>
            {amsUnits.length > 1 && (
              <div className="flex rounded overflow-hidden border border-surface-3 text-xs">
                {amsUnits.map(u => (
                  <button
                    key={u}
                    onClick={() => setActiveUnit(u)}
                    className={`px-2.5 py-0.5 transition-colors ${
                      visibleUnit === u ? 'bg-blue-700 text-white' : 'text-gray-400 hover:text-gray-200'
                    }`}
                  >
                    AMS {u}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="space-y-1">
            {trays
              .filter(tr => {
                const m = tr.slot_key.match(/^ams(\d+)_/)
                return m ? parseInt(m[1]) === visibleUnit : true
              })
              .map(tray => (
                <div key={tray.slot_key} className="flex items-center gap-2 bg-surface-3/40 rounded-lg px-3 py-1.5 text-xs">
                  <span className="font-mono text-gray-400 w-20 shrink-0">{tray.slot_key}</span>
                  {tray.ha_color_hex ? (
                    <span className="w-3 h-3 rounded-full border border-white/20 shrink-0" style={{ background: tray.ha_color_hex }} />
                  ) : (
                    <span className="w-3 h-3 rounded-full bg-surface-3 border border-white/10 shrink-0" />
                  )}
                  <span className="text-gray-300 flex-1">{tray.ha_material ?? '—'}</span>
                  <span className="text-gray-400">{tray.ha_remaining != null ? `${tray.ha_remaining}%` : '—'}</span>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Raw MQTT cache dump */}
      <div className="mt-3 border-t border-surface-3 pt-2">
        <div className="flex items-center justify-between gap-2">
          <button
            className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1"
            onClick={() => setShowRaw(r => !r)}
          >
            {showRaw ? '▾' : '▸'} Raw MQTT cache ({Object.keys(rawCache).length} printer fields, {Object.keys(rawAmsCache).length} AMS slots)
          </button>
          {debugInfo && printer.bambu_serial && (
            <button
              className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1"
              title="Download full MQTT cache as JSON"
              onClick={() => {
                const serial = printer.bambu_serial!
                const payload = {
                  serial,
                  exported_at: new Date().toISOString(),
                  printer_status: debugInfo.printer_status_cache?.[serial] ?? {},
                  ams_cache: debugInfo.ams_cache?.[serial] ?? {},
                  mqtt_client: debugInfo.mqtt_clients?.[serial] ?? {},
                }
                const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
                const url = URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = url
                a.download = `mqtt_cache_${serial}.json`
                a.click()
                URL.revokeObjectURL(url)
              }}
            >
              <Download size={11} /> Download JSON
            </button>
          )}
        </div>
        {showRaw && (
          <div className="mt-2 space-y-3">
            {/* Printer status fields */}
            <div>
              <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1">Printer status</p>
              {Object.keys(rawCache).length === 0 ? (
                <span className="text-[11px] font-mono text-gray-600">No data in cache yet</span>
              ) : (
                <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11px] font-mono">
                  {Object.entries(rawCache).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => (
                    <span key={k} className="text-gray-500 truncate">
                      {k}: <span className="text-gray-300">{String(v)}</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
            {/* AMS tray fields */}
            <div>
              <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1">AMS tray cache</p>
              {Object.keys(rawAmsCache).length === 0 ? (
                <span className="text-[11px] font-mono text-gray-600">No AMS data in cache yet</span>
              ) : (
                <div className="space-y-1">
                  {Object.entries(rawAmsCache).sort(([a], [b]) => a.localeCompare(b)).map(([slot, td]) => (
                    <div key={slot} className="text-[11px] font-mono">
                      <span className="text-blue-400">{slot}</span>
                      <span className="text-gray-600"> → </span>
                      {Object.entries(td as Record<string, unknown>).map(([k, v]) => (
                        <span key={k} className="text-gray-500 mr-3">
                          {k}: <span className="text-gray-300">{String(v)}</span>
                        </span>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function Settings() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [mainTab, setMainTab] = useState<MainTab>('printers')
  const [dataTab, setDataTab] = useState<DataSubTab>('brandWeights')
  const [activePrinterId, setActivePrinterId] = useState<number | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<PrinterConfig | null>(null)

  const { data: printers = [] } = useQuery<PrinterConfig[]>({
    queryKey: ['printers'],
    queryFn: api.getPrinters,
  })
  const { data: cloudStatus } = useQuery({
    queryKey: ['bambu-cloud-status'],
    queryFn: api.getBambuCloudStatus,
    refetchInterval: 5_000,
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

  const isCloudConnected = cloudStatus?.status === 'connected'
  const invalidate = () => qc.invalidateQueries({ queryKey: ['printers'] })

  const createMut = useMutation({ mutationFn: api.createPrinter, onSuccess: () => { invalidate(); setShowForm(false) } })
  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: unknown }) => api.updatePrinter(id, data),
    onSuccess: () => { invalidate(); setEditing(null) },
  })
  const deleteMut = useMutation({ mutationFn: api.deletePrinter, onSuccess: invalidate })

  const activePrinter = printers.find(p => p.id === activePrinterId) ?? printers[0] ?? null

  const MAIN_TABS: { id: MainTab; label: string; dot?: boolean }[] = [
    { id: 'printers',    label: t('settings.tabs.printers') },
    { id: 'data',        label: t('settings.tabs.data') },
    { id: 'transfer',    label: t('settings.tabs.transfer') },
    { id: 'experiments', label: t('settings.tabs.experiments'), dot: isCloudConnected },
  ]

  const DATA_SUBTABS: { id: DataSubTab; label: string }[] = [
    { id: 'brandWeights', label: t('settings.dataTabs.brandWeights') },
    { id: 'brands',       label: t('settings.dataTabs.brands') },
    { id: 'materials',    label: t('settings.dataTabs.materials') },
    { id: 'subtypes',     label: t('settings.dataTabs.subtypes') },
    { id: 'locations',        label: t('settings.dataTabs.locations') },
    { id: 'storageLocations', label: t('settings.dataTabs.storageLocations') },
    { id: 'filamentData',     label: t('settings.dataTabs.filamentData') },
  ]

  // Experiments tab: all printers with a serial (regardless of source)
  const cloudPrinters = printers.filter(p => p.bambu_serial)

  const isFilamentData = mainTab === 'data' && dataTab === 'filamentData'

  return (
    <div className={`space-y-4 ${isFilamentData ? '' : 'max-w-2xl'}`}>
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-bold">{t('settings.title')}</h2>
        {versionData && <span className="text-xs text-gray-500">v{versionData.version}</span>}
      </div>

      {/* Main tab bar */}
      <div className="flex border-b border-surface-3 gap-0">
        {MAIN_TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setMainTab(tab.id)}
            className={`pb-2.5 pt-1 px-4 text-sm font-medium border-b-2 transition-colors flex items-center gap-1.5 -mb-px ${
              mainTab === tab.id
                ? 'border-blue-500 text-white'
                : 'border-transparent text-gray-400 hover:text-gray-200'
            }`}
          >
            {tab.label}
            {tab.dot && <span className="w-1.5 h-1.5 rounded-full bg-green-400 shrink-0" />}
          </button>
        ))}
      </div>

      {/* ── Tab: Printers ── */}
      {mainTab === 'printers' && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              {haStatus?.ha_available
                ? <><CheckCircle size={14} className="text-green-400" /><span className="text-sm text-green-400">{t('settings.ha.connected')}</span></>
                : <><AlertCircle size={14} className="text-red-400" /><span className="text-sm text-red-400">{t('settings.ha.disconnected')}</span></>
              }
            </div>
            <button className="btn-primary flex items-center gap-1.5 text-xs" onClick={() => setShowForm(true)}>
              <Plus size={13} /> {t('settings.printers.addPrinter')}
            </button>
          </div>

          {printers.length === 0 ? (
            <p className="text-sm text-gray-500">{t('settings.printers.noPrintersHint')}</p>
          ) : (
            <>
              {printers.length > 1 && (
                <div className="flex border-b border-surface-3 mb-4 gap-0 -mx-5 px-5 overflow-x-auto shrink-0">
                  {printers.map(p => (
                    <button
                      key={p.id}
                      onClick={() => setActivePrinterId(p.id)}
                      className={`pb-2.5 pt-2 px-3 text-xs font-medium border-b-2 transition-colors whitespace-nowrap flex-shrink-0 ${
                        activePrinter?.id === p.id
                          ? 'border-blue-500 text-white'
                          : 'border-transparent text-gray-400 hover:text-gray-200'
                      }`}
                    >
                      {p.name}
                    </button>
                  ))}
                </div>
              )}

              {activePrinter && (
                <PrinterCard
                  printer={activePrinter}
                  onEdit={() => setEditing(activePrinter)}
                  onDelete={() => {
                    if (confirm(t('settings.printers.confirmDelete', { name: activePrinter.name })))
                      deleteMut.mutate(activePrinter.id)
                  }}
                />
              )}
            </>
          )}
        </div>
      )}

      {/* ── Tab: Data ── */}
      {mainTab === 'data' && (
        <>
          {/* Subtab bar + small-list content stay inside a constrained card */}
          <div className={`card ${isFilamentData ? 'pb-0' : ''}`}>
            {/* Scrollable subtab bar — scrollbar hidden visually */}
            <div
              className="flex border-b border-surface-3 gap-0 -mx-5 px-5 pt-1"
              style={{ overflowX: 'auto', scrollbarWidth: 'none', msOverflowStyle: 'none' }}
            >
              {DATA_SUBTABS.map(st => (
                <button
                  key={st.id}
                  onClick={() => setDataTab(st.id)}
                  className={`pb-2.5 pt-1 px-3 text-xs font-medium border-b-2 transition-colors whitespace-nowrap -mb-px ${
                    dataTab === st.id
                      ? 'border-blue-500 text-white'
                      : 'border-transparent text-gray-400 hover:text-gray-200'
                  }`}
                >
                  {st.label}
                </button>
              ))}
            </div>

            {!isFilamentData && (
              <div className="mt-5">
                {dataTab === 'brandWeights' && <BrandWeightsSection />}
                {dataTab === 'brands' && (
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
                )}
                {dataTab === 'materials' && (
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
                )}
                {dataTab === 'subtypes' && (
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
                )}
                {dataTab === 'locations' && (
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
                )}
                {dataTab === 'storageLocations' && (
                  <NameListSection
                    title={t('settings.storageLocations.title')}
                    queryKey="storage-locations"
                    fetchFn={api.getStorageLocations}
                    createFn={api.createStorageLocation}
                    updateFn={api.updateStorageLocation}
                    deleteFn={api.deleteStorageLocation}
                    placeholder={t('settings.storageLocations.placeholder')}
                    noEntries={t('settings.storageLocations.noEntries')}
                  />
                )}
              </div>
            )}
          </div>

          {/* Filament Data renders outside the card for full-width table */}
          {isFilamentData && <FilamentDataSection />}
        </>
      )}

      {/* ── Tab: Export / Import ── */}
      {mainTab === 'transfer' && <DataTransferSection />}

      {/* ── Tab: Experiments ── */}
      {mainTab === 'experiments' && (
        <div className="space-y-4">
          <div className="card">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-300">{t('settings.bambuCloud.title')}</h3>
            </div>
            <p className="text-xs text-gray-500 mb-4">{t('settings.bambuCloud.hint')}</p>
            <BambuCloudSection />
          </div>

          {isCloudConnected && cloudPrinters.length > 0 && (
            <div className="space-y-3">
              <p className="text-xs font-medium text-gray-400 uppercase tracking-wide">
                {t('settings.bambuCloud.liveStatus')}
              </p>
              {cloudPrinters.map(p => (
                <CloudPrinterStatus key={p.id} printer={p} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Printer form modal */}
      {(showForm || editing) && (
        <Modal>
          <PrinterFormModal
            initial={editing ?? undefined}
            cloudStatus={cloudStatus}
            existingPrinters={printers}
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
