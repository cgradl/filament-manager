import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api } from '../api'
import type { Spool, BrandSpoolWeight } from '../types'
import { Plus, Pencil, Trash2, X, LayoutGrid, Table2, ChevronUp, ChevronDown, ChevronsUpDown, Copy } from 'lucide-react'
import Modal from '../components/Modal'
import { formatDateOnly } from '../utils/time'

// ── Spool Form ────────────────────────────────────────────────────────────────

const EMPTY_FORM = {
  custom_id: '',
  brand: '', material: 'PLA', subtype: '', subtype2: '', color_name: '', color_hex: '#888888',
  diameter_mm: 1.75, initial_weight_g: 1000, current_weight_g: 1000,
  purchase_price: '', purchased_at: '', purchase_location: '',
  ams_slot: '', notes: '',
}

function SpoolForm({
  initial,
  isNew,
  onSave,
  onCancel,
}: {
  initial?: Partial<Spool>
  isNew?: boolean
  onSave: (data: typeof EMPTY_FORM, quantity: number) => void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  const [form, setForm] = useState({
    ...EMPTY_FORM,
    ...initial,
    subtype: initial?.subtype ?? '',
    subtype2: initial?.subtype2 ?? '',
    purchase_price: initial?.purchase_price?.toString() ?? '',
    purchased_at: initial?.purchased_at ? initial.purchased_at.slice(0, 10) : '',
    purchase_location: initial?.purchase_location ?? '',
    initial_weight_g: initial?.initial_weight_g ?? 1000,
    current_weight_g: initial?.current_weight_g ?? 1000,
  })

  const [measuredTotal, setMeasuredTotal] = useState('')
  const [quantity, setQuantity] = useState(1)

  const { data: materials = [] } = useQuery({ queryKey: ['materials'], queryFn: api.getMaterials })
  const { data: subtypes = [] } = useQuery({ queryKey: ['subtypes'], queryFn: api.getSubtypes })
  const { data: brandWeights = [] } = useQuery<BrandSpoolWeight[]>({ queryKey: ['brand-weights'], queryFn: api.getBrandWeights })
  const { data: brands = [] } = useQuery<{ id: number; name: string }[]>({ queryKey: ['filament-brands'], queryFn: api.getFilamentBrands })
  const { data: locations = [] } = useQuery<{ id: number; name: string }[]>({ queryKey: ['purchase-locations'], queryFn: api.getPurchaseLocations })

  const matchedBrand = brandWeights.find(b => b.brand.toLowerCase() === form.brand.toLowerCase())
  const tareG = matchedBrand?.spool_weight_g ?? 0

  const onBrandChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm(f => ({ ...f, brand: e.target.value }))
  }

  const onMeasuredChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value
    setMeasuredTotal(val)
    const totalG = parseFloat(val)
    if (!isNaN(totalG)) {
      const remaining = Math.max(0, totalG - tareG)
      setForm(f => ({ ...f, current_weight_g: remaining }))
    }
  }

  const set = (k: keyof typeof EMPTY_FORM) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) => setForm(f => ({ ...f, [k]: e.target.value }))

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-surface-2 border border-surface-3 rounded-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-surface-3">
          <h2 className="font-semibold">{initial?.id ? t('spools.editSpool') : t('spools.addSpool')}</h2>
          <button onClick={onCancel} className="btn-ghost p-1"><X size={16} /></button>
        </div>

        <div className="p-5 space-y-4">
          <div>
            <label className="label">{t('spools.form.customId')}</label>
            <input
              className="input w-28"
              type="number"
              min="1"
              max="9999"
              step="1"
              placeholder="—"
              value={form.custom_id ?? ''}
              onChange={e => {
                const v = e.target.value.replace(/\D/g, '').slice(0, 4)
                setForm(f => ({ ...f, custom_id: v }))
              }}
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="label">{t('spools.form.brand')} *</label>
              <input className="input" value={form.brand} onChange={onBrandChange}
                placeholder={t('spools.form.brandPlaceholder')}
                list="brand-list" />
              <datalist id="brand-list">
                {brands.map(b => <option key={b.id} value={b.name} />)}
              </datalist>
            </div>
            <div>
              <label className="label">{t('spools.form.material')} *</label>
              <select className="input" value={form.material} onChange={set('material')}>
                {materials.map(m => <option key={m}>{m}</option>)}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="label">{t('spools.form.subtype')}</label>
              <select className="input" value={form.subtype ?? ''} onChange={set('subtype')}>
                <option value="">{t('common.none')}</option>
                {subtypes.map(s => <option key={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label className="label">{t('spools.form.subtype2')}</label>
              <select className="input" value={form.subtype2 ?? ''} onChange={set('subtype2')}>
                <option value="">{t('common.none')}</option>
                {subtypes.map(s => <option key={s}>{s}</option>)}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="label">{t('spools.form.diameter')}</label>
              <select className="input" value={form.diameter_mm} onChange={set('diameter_mm')}>
                <option value={1.75}>1.75 mm</option>
                <option value={2.85}>2.85 mm</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="label">{t('spools.form.colorName')} *</label>
              <input className="input" value={form.color_name} onChange={set('color_name')}
                placeholder={t('spools.form.colorPlaceholder')} />
            </div>
            <div>
              <label className="label">{t('spools.form.colorSwatch')}</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  className="h-9 w-16 rounded cursor-pointer bg-surface-3 border border-surface-3"
                  value={form.color_hex}
                  onChange={set('color_hex')}
                />
                <input className="input flex-1" value={form.color_hex} onChange={set('color_hex')} placeholder="#ffffff" />
              </div>
            </div>
          </div>

          {/* Weight section */}
          <div className="rounded-xl border border-surface-3 p-3 space-y-3 bg-surface-3/20">
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">{t('spools.form.weight')}</p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="label">{t('spools.form.nominalWeight')} *</label>
                <div className="flex items-center gap-2">
                  <input
                    className="input" type="number" step="50" min="0"
                    value={form.initial_weight_g}
                    onChange={e => setForm(f => ({
                      ...f,
                      initial_weight_g: parseFloat(e.target.value) || 0,
                      current_weight_g: initial?.id ? f.current_weight_g : parseFloat(e.target.value) || 0,
                    }))}
                    placeholder="1000"
                  />
                  <span className="text-xs text-gray-500 shrink-0">g</span>
                </div>
                <p className="text-xs text-gray-500 mt-0.5">{t('spools.form.nominalWeightHint')}</p>
              </div>

              <div>
                <label className="label">{t('spools.form.emptySpoolTare')}</label>
                <div className="flex items-center gap-2">
                  <div className="input bg-surface-3/50 text-gray-300 cursor-default select-none flex-1">
                    {tareG > 0 ? `${tareG} g` : '—'}
                  </div>
                </div>
                {matchedBrand ? (
                  <p className="text-xs text-green-500 mt-0.5">{t('spools.form.brandConfig', { brand: form.brand })}</p>
                ) : form.brand ? (
                  <p className="text-xs text-gray-500 mt-0.5">{t('spools.form.noBrandConfig')}</p>
                ) : null}
              </div>
            </div>

            {/* Scale-based remaining calculator */}
            <div className="border-t border-surface-3 pt-3">
              <p className="text-xs text-gray-400 mb-2">{t('spools.form.scaleHint')}</p>
              <div className="flex items-center gap-2">
                <div className="flex-1">
                  <label className="label">{t('spools.form.scaleReading')}</label>
                  <div className="flex items-center gap-2">
                    <input
                      className="input" type="number" step="1" min="0"
                      value={measuredTotal}
                      onChange={onMeasuredChange}
                      placeholder="750"
                    />
                    <span className="text-xs text-gray-500 shrink-0">g</span>
                  </div>
                </div>
                <div className="text-gray-500 text-xs mt-4">→</div>
                <div className="flex-1">
                  <label className="label">{t('spools.form.remainingFilament')}</label>
                  <div className="flex items-center gap-2">
                    <input
                      className="input" type="number" step="1" min="0"
                      value={form.current_weight_g}
                      onChange={e => {
                        setMeasuredTotal('')
                        setForm(f => ({ ...f, current_weight_g: parseFloat(e.target.value) || 0 }))
                      }}
                    />
                    <span className="text-xs text-gray-500 shrink-0">g</span>
                  </div>
                </div>
              </div>
              {form.initial_weight_g > 0 && (
                <p className="text-xs text-gray-500 mt-1.5">
                  {t('spools.form.percentRemaining', { pct: ((form.current_weight_g / form.initial_weight_g) * 100).toFixed(1) })}
                </p>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="label">{t('spools.form.purchasePrice')}</label>
              <input className="input" type="number" step="0.01" value={form.purchase_price} onChange={set('purchase_price')} placeholder="11.59" />
            </div>
            <div>
              <label className="label">{t('spools.form.purchaseDate')}</label>
              <input className="input" type="date" value={form.purchased_at} onChange={set('purchased_at')} />
            </div>
          </div>

          <div>
            <label className="label">{t('spools.form.purchaseLocation')}</label>
            <select className="input" value={form.purchase_location} onChange={set('purchase_location')}>
              <option value="">{t('common.select')}</option>
              {locations.map(l => <option key={l.id} value={l.name}>{l.name}</option>)}
            </select>
          </div>

          <div>
            <label className="label">{t('spools.form.amsSlot')}</label>
            <input className="input" value={form.ams_slot ?? ''} onChange={set('ams_slot')} placeholder="ams1_tray1" />
          </div>

          <div>
            <label className="label">{t('spools.form.notes')}</label>
            <textarea className="input h-16 resize-none" value={form.notes ?? ''} onChange={set('notes')} />
          </div>

        </div>

        <div className="flex items-center justify-between px-5 py-4 border-t border-surface-3 gap-3">
          {isNew && (
            <div className="flex items-center gap-2 shrink-0">
              <label className="text-xs text-gray-400">{t('spools.form.qty')}</label>
              <input
                className="input w-16 text-sm py-1 text-center"
                type="number" min="1" max="50"
                value={quantity}
                onChange={e => setQuantity(Math.max(1, parseInt(e.target.value) || 1))}
              />
            </div>
          )}
          <div className="flex gap-2 ml-auto">
            <button className="btn-ghost" onClick={onCancel}>{t('common.cancel')}</button>
            <button
              className="btn-primary"
              onClick={() => onSave(form as typeof EMPTY_FORM, quantity)}
              disabled={!form.brand || !form.material || !form.color_name}
            >
              {isNew && quantity > 1 ? t('spools.form.addN', { n: quantity }) : t('common.save')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Spool Card ────────────────────────────────────────────────────────────────

function SpoolCard({ spool, onEdit, onDuplicate, onDelete }: {
  spool: Spool; onEdit: () => void; onDuplicate: () => void; onDelete: () => void
}) {
  const { t } = useTranslation()
  const pct = spool.remaining_pct
  const barColor = pct > 40 ? '#3b82f6' : pct > 15 ? '#f59e0b' : '#ef4444'

  return (
    <div className="card">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="w-4 h-4 rounded-full shrink-0 ring-1 ring-white/10" style={{ background: spool.color_hex }} />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-white truncate">
              {spool.brand} {spool.material}
              {spool.subtype ? ` ${spool.subtype}` : ''}
              {spool.subtype2 ? ` · ${spool.subtype2}` : ''}
            </p>
            <p className="text-xs text-gray-400">{spool.color_name}</p>
          </div>
        </div>
        <div className="flex gap-1 shrink-0 ml-2">
          <button onClick={onEdit} className="btn-ghost p-1" title={t('spools.actions.edit')}><Pencil size={13} /></button>
          <button onClick={onDuplicate} className="btn-ghost p-1 text-blue-400" title={t('spools.actions.duplicate')}><Copy size={13} /></button>
          <button onClick={onDelete} className="btn-ghost p-1 text-red-400 hover:text-red-300" title={t('spools.actions.delete')}><Trash2 size={13} /></button>
        </div>
      </div>
      <div className="mb-2">
        <div className="flex justify-between text-xs text-gray-400 mb-1">
          <span>{(spool.current_weight_g / 1000).toFixed(3)} kg {t('spools.remaining')}</span>
          <span>{pct}%</span>
        </div>
        <div className="h-1.5 rounded-full bg-surface-3 overflow-hidden">
          <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: barColor }} />
        </div>
        <p className="text-xs text-gray-500 mt-1">{t('spools.of')} {(spool.initial_weight_g / 1000).toFixed(2)} kg</p>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400 mt-3">
        {spool.price_per_kg != null && <span>€{spool.price_per_kg.toFixed(2)}/kg</span>}
        {spool.purchase_price != null && <span>€{spool.purchase_price.toFixed(2)}</span>}
        {spool.purchased_at && <span>{formatDateOnly(spool.purchased_at)}</span>}
        {spool.ams_slot && <span className="text-blue-400">{spool.ams_slot}</span>}
      </div>
    </div>
  )
}

// ── Table View ────────────────────────────────────────────────────────────────

type SortKey = 'custom_id' | 'brand' | 'material' | 'subtype' | 'color_name' | 'remaining_pct' |
               'current_weight_g' | 'initial_weight_g' | 'purchase_price' |
               'price_per_kg' | 'purchased_at' | 'purchase_location' | 'ams_slot'
type SortDir = 'asc' | 'desc'

function SortIcon({ col, sort }: { col: SortKey; sort: { key: SortKey; dir: SortDir } }) {
  if (sort.key !== col) return <ChevronsUpDown size={12} className="text-gray-600" />
  return sort.dir === 'asc'
    ? <ChevronUp size={12} className="text-accent" />
    : <ChevronDown size={12} className="text-accent" />
}

function SpoolTable({ spools, onEdit, onDuplicate, onDelete }: {
  spools: Spool[]; onEdit: (s: Spool) => void; onDuplicate: (s: Spool) => void; onDelete: (s: Spool) => void
}) {
  const { t } = useTranslation()
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({ key: 'ams_slot', dir: 'asc' })
  const [filters, setFilters] = useState<Partial<Record<SortKey, string>>>({})

  const setFilter = (k: SortKey, v: string) =>
    setFilters(f => ({ ...f, [k]: v }))

  const toggleSort = (k: SortKey) =>
    setSort(s => s.key === k ? { key: k, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key: k, dir: 'asc' })

  const NUMERIC_COLS = new Set<SortKey>([
    'custom_id', 'remaining_pct', 'current_weight_g', 'initial_weight_g', 'purchase_price', 'price_per_kg',
  ])

  const processed = useMemo(() => {
    let rows = [...spools]

    for (const [k, v] of Object.entries(filters)) {
      if (!v) continue
      const key = k as SortKey

      if (NUMERIC_COLS.has(key)) {
        const op = v.startsWith('>=') ? '>=' : v.startsWith('<=') ? '<=' : v.startsWith('>') ? '>' : v.startsWith('<') ? '<' : '='
        const numStr = v.replace(/^[><=]+/, '').trim()
        const threshold = parseFloat(numStr)
        if (isNaN(threshold)) continue
        rows = rows.filter(s => {
          const raw = s[key as keyof Spool]
          const num = typeof raw === 'number' ? raw : parseFloat(String(raw ?? ''))
          if (isNaN(num)) return false
          const cmpVal = (key === 'current_weight_g' || key === 'initial_weight_g')
            ? num / 1000
            : num
          if (op === '>=') return cmpVal >= threshold
          if (op === '<=') return cmpVal <= threshold
          if (op === '>')  return cmpVal >  threshold
          if (op === '<')  return cmpVal <  threshold
          return cmpVal === threshold
        })
      } else {
        const lower = v.toLowerCase()
        rows = rows.filter(s => {
          const val = s[key as keyof Spool]
          if (val == null) return false
          return String(val).toLowerCase().includes(lower)
        })
      }
    }

    rows.sort((a, b) => {
      if (sort.key === 'ams_slot') {
        const aHas = a.ams_slot != null ? 1 : 0
        const bHas = b.ams_slot != null ? 1 : 0
        if (aHas !== bHas) return bHas - aHas
        const slotCmp = (a.ams_slot ?? '').localeCompare(b.ams_slot ?? '')
        if (slotCmp !== 0) return sort.dir === 'asc' ? slotCmp : -slotCmp
        return b.remaining_pct - a.remaining_pct
      }
      const av = a[sort.key] ?? ''
      const bv = b[sort.key] ?? ''
      const cmp = typeof av === 'number' && typeof bv === 'number'
        ? av - bv
        : String(av).localeCompare(String(bv))
      return sort.dir === 'asc' ? cmp : -cmp
    })
    return rows
  }, [spools, sort, filters])

  const cols: { key: SortKey; label: string; width?: string }[] = [
    { key: 'custom_id',        label: '#',                            width: 'w-14' },
    { key: 'brand',            label: t('spools.table.brand'),        width: 'w-24' },
    { key: 'material',         label: t('spools.table.material'),     width: 'w-20' },
    { key: 'subtype',          label: t('spools.table.subtype'),      width: 'w-24' },
    { key: 'color_name',       label: t('spools.table.color'),        width: 'w-32' },
    { key: 'remaining_pct',    label: t('spools.table.remaining'),    width: 'w-28' },
    { key: 'current_weight_g', label: t('spools.table.currentWeight'),width: 'w-24' },
    { key: 'initial_weight_g', label: t('spools.table.initialWeight'),width: 'w-20' },
    { key: 'purchase_price',   label: t('spools.table.price'),        width: 'w-20' },
    { key: 'price_per_kg',     label: t('spools.table.pricePerKg'),   width: 'w-20' },
    { key: 'purchased_at',     label: t('spools.table.purchaseDate'), width: 'w-24' },
    { key: 'purchase_location',label: t('spools.table.location'),     width: 'w-24' },
    { key: 'ams_slot',         label: t('spools.table.amsSlot'),      width: 'w-24' },
  ]

  return (
    <div className="overflow-x-auto rounded-xl border border-surface-3">
      <table className="w-full text-xs text-left">
        <thead>
          <tr className="border-b border-surface-3">
            {cols.map(c => (
              <th
                key={c.key}
                className={`px-3 py-2 text-gray-400 font-medium whitespace-nowrap cursor-pointer select-none hover:text-white ${c.width ?? ''}`}
                onClick={() => toggleSort(c.key)}
              >
                <span className="flex items-center gap-1">
                  {c.label} <SortIcon col={c.key} sort={sort} />
                </span>
              </th>
            ))}
            <th className="px-3 py-2 w-16" />
          </tr>
          <tr className="border-b border-surface-3 bg-surface-3/30">
            {cols.map(c => (
              <td key={c.key} className="px-2 py-1">
                <input
                  className="w-full bg-surface-3 rounded px-2 py-0.5 text-xs text-gray-100 placeholder-gray-600
                             focus:outline-none focus:ring-1 focus:ring-accent"
                  placeholder={NUMERIC_COLS.has(c.key) ? '=, >=, <…' : 'filter…'}
                  value={filters[c.key] ?? ''}
                  onChange={e => setFilter(c.key, e.target.value)}
                />
              </td>
            ))}
            <td className="px-2 py-1">
              <button
                className="text-xs text-gray-500 hover:text-white"
                onClick={() => setFilters({})}
                title="Clear all filters"
              >
                ✕
              </button>
            </td>
          </tr>
        </thead>
        <tbody>
          {processed.map(s => {
            const pct = s.remaining_pct
            const barColor = pct > 40 ? '#3b82f6' : pct > 15 ? '#f59e0b' : '#ef4444'
            return (
              <tr
                key={s.id}
                className="border-b border-surface-3/50 hover:bg-surface-3/40 transition-colors"
              >
                <td className="px-3 py-2 whitespace-nowrap text-gray-400 font-mono">{s.custom_id ?? '—'}</td>
                <td className="px-3 py-2 font-medium text-white whitespace-nowrap">{s.brand}</td>
                <td className="px-3 py-2 whitespace-nowrap">{s.material}</td>
                <td className="px-3 py-2 whitespace-nowrap text-gray-300">
                  {[s.subtype, s.subtype2].filter(Boolean).join(' · ') || '—'}
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  <span className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full shrink-0 ring-1 ring-white/10" style={{ background: s.color_hex }} />
                    {s.color_name}
                  </span>
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  <div className="flex items-center gap-2">
                    <div className="w-16 h-1.5 rounded-full bg-surface-3 overflow-hidden">
                      <div className="h-full rounded-full" style={{ width: `${pct}%`, background: barColor }} />
                    </div>
                    <span style={{ color: barColor }}>{pct}%</span>
                  </div>
                </td>
                <td className="px-3 py-2 whitespace-nowrap text-gray-300">
                  {(s.current_weight_g / 1000).toFixed(3)} kg
                </td>
                <td className="px-3 py-2 whitespace-nowrap text-gray-400">
                  {(s.initial_weight_g / 1000).toFixed(2)} kg
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  {s.purchase_price != null ? `€${s.purchase_price.toFixed(2)}` : '—'}
                </td>
                <td className="px-3 py-2 whitespace-nowrap text-gray-400">
                  {s.price_per_kg != null ? `€${s.price_per_kg.toFixed(2)}` : '—'}
                </td>
                <td className="px-3 py-2 whitespace-nowrap text-gray-400">
                  {s.purchased_at ? formatDateOnly(s.purchased_at) : '—'}
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  {s.purchase_location
                    ? <span className="text-xs bg-surface-3 px-1.5 py-0.5 rounded text-gray-400">{s.purchase_location}</span>
                    : <span className="text-gray-600">—</span>
                  }
                </td>
                <td className="px-3 py-2 whitespace-nowrap text-blue-400">
                  {s.ams_slot ?? '—'}
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  <div className="flex gap-1">
                    <button onClick={() => onEdit(s)} className="btn-ghost p-1" title={t('spools.actions.edit')}><Pencil size={12} /></button>
                    <button onClick={() => onDuplicate(s)} className="btn-ghost p-1 text-blue-400" title={t('spools.actions.duplicate')}><Copy size={12} /></button>
                    <button onClick={() => onDelete(s)} className="btn-ghost p-1 text-red-400" title={t('spools.actions.delete')}><Trash2 size={12} /></button>
                  </div>
                </td>
              </tr>
            )
          })}
          {processed.length === 0 && (
            <tr>
              <td colSpan={cols.length + 1} className="px-3 py-6 text-center text-gray-500">
                {t('spools.noMatch')}
              </td>
            </tr>
          )}
        </tbody>
        {processed.length > 0 && (() => {
          const n = processed.length
          const avgPct = processed.reduce((s, r) => s + r.remaining_pct, 0) / n
          const totalRemKg = processed.reduce((s, r) => s + r.current_weight_g, 0) / 1000
          const withPrice = processed.filter(r => r.purchase_price != null)
          const avgPrice = withPrice.length
            ? withPrice.reduce((s, r) => s + r.purchase_price!, 0) / withPrice.length
            : null
          const withPpkg = processed.filter(r => r.price_per_kg != null)
          const avgPpkg = withPpkg.length
            ? withPpkg.reduce((s, r) => s + r.price_per_kg!, 0) / withPpkg.length
            : null
          return (
            <tfoot>
              <tr className="border-t-2 border-surface-3 bg-surface-3/40 text-gray-300 font-medium">
                <td className="px-3 py-2 text-xs text-gray-400" colSpan={4}>
                  {n} {n !== 1 ? t('dashboard.chart.spools') : t('dashboard.chart.spool')}
                </td>
                <td className="px-3 py-2 whitespace-nowrap text-xs">
                  <span className="text-gray-300">{avgPct.toFixed(1)}%</span>
                </td>
                <td className="px-3 py-2 whitespace-nowrap text-xs">
                  {totalRemKg.toFixed(3)} kg
                </td>
                <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-400">
                  {(processed.reduce((s, r) => s + r.initial_weight_g, 0) / 1000).toFixed(2)} kg
                </td>
                <td className="px-3 py-2 whitespace-nowrap text-xs">
                  {avgPrice != null ? `€${avgPrice.toFixed(2)}` : '—'}
                </td>
                <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-400">
                  {avgPpkg != null ? `€${avgPpkg.toFixed(2)}` : '—'}
                </td>
                <td colSpan={4} />
              </tr>
            </tfoot>
          )
        })()}
      </table>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Spools() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<Spool | null>(null)
  const [duplicating, setDuplicating] = useState<Spool | null>(null)
  const [view, setView] = useState<'cards' | 'table'>('table')

  const { data: spools = [], isLoading } = useQuery<Spool[]>({
    queryKey: ['spools'],
    queryFn: () => api.getSpools(),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['spools'] })

  const createMut = useMutation({ mutationFn: api.createSpool, onSuccess: invalidate })
  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Spool> }) => api.updateSpool(id, data),
    onSuccess: () => { invalidate(); setEditing(null) },
  })
  const deleteMut = useMutation({ mutationFn: api.deleteSpool, onSuccess: invalidate })

  const buildPayload = (form: typeof EMPTY_FORM) => ({
    ...form,
    custom_id: form.custom_id !== '' ? parseInt(form.custom_id as string, 10) || null : null,
    purchase_price: form.purchase_price ? parseFloat(form.purchase_price as string) : null,
    purchased_at: form.purchased_at || null,
    purchase_location: form.purchase_location || null,
    subtype: form.subtype || null,
    subtype2: form.subtype2 || null,
    ams_slot: form.ams_slot || null,
    notes: form.notes || null,
  })

  const handleSave = async (form: typeof EMPTY_FORM, quantity: number) => {
    const payload = buildPayload(form)
    if (editing) {
      updateMut.mutate({ id: editing.id, data: payload })
    } else {
      for (let i = 0; i < quantity; i++) {
        await api.createSpool(payload)
      }
      invalidate()
      setShowForm(false)
      setDuplicating(null)
    }
  }

  const handleDelete = (spool: Spool) => {
    if (confirm(t('spools.confirmDelete', { brand: spool.brand, color: spool.color_name }))) {
      deleteMut.mutate(spool.id)
    }
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-lg font-bold">{t('spools.title')} ({spools.length})</h2>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border border-surface-3 overflow-hidden">
            <button
              className={`px-2.5 py-1.5 text-xs flex items-center gap-1 transition-colors ${view === 'cards' ? 'bg-accent text-white' : 'text-gray-400 hover:text-white hover:bg-surface-3'}`}
              onClick={() => setView('cards')}
              title={t('spools.viewGrid')}
            >
              <LayoutGrid size={13} />
            </button>
            <button
              className={`px-2.5 py-1.5 text-xs flex items-center gap-1 transition-colors ${view === 'table' ? 'bg-accent text-white' : 'text-gray-400 hover:text-white hover:bg-surface-3'}`}
              onClick={() => setView('table')}
              title={t('spools.viewTable')}
            >
              <Table2 size={13} />
            </button>
          </div>

          <button className="btn-primary flex items-center gap-1.5" onClick={() => setShowForm(true)}>
            <Plus size={14} /> {t('spools.addSpool')}
          </button>
        </div>
      </div>

      {isLoading && <p className="text-gray-500 text-sm">{t('common.loading')}</p>}

      {view === 'cards' ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {spools.map(spool => (
            <SpoolCard
              key={spool.id}
              spool={spool}
              onEdit={() => setEditing(spool)}
              onDuplicate={() => setDuplicating(spool)}
              onDelete={() => handleDelete(spool)}
            />
          ))}
        </div>
      ) : (
        <SpoolTable
          spools={spools}
          onEdit={s => setEditing(s)}
          onDuplicate={s => setDuplicating(s)}
          onDelete={handleDelete}
        />
      )}

      {editing && (
        <Modal>
          <SpoolForm
            initial={editing}
            onSave={handleSave}
            onCancel={() => setEditing(null)}
          />
        </Modal>
      )}

      {showForm && (
        <Modal>
          <SpoolForm
            isNew
            onSave={handleSave}
            onCancel={() => setShowForm(false)}
          />
        </Modal>
      )}

      {duplicating && (
        <Modal>
          <SpoolForm
            isNew
            initial={{
              ...duplicating,
              purchase_price: null,
              purchased_at: null,
              purchase_location: null,
              ams_slot: null,
            }}
            onSave={handleSave}
            onCancel={() => setDuplicating(null)}
          />
        </Modal>
      )}
    </div>
  )
}
