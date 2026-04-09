// Relative base — works correctly behind HA ingress
const BASE = 'api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}/${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status}: ${text}`)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

// ── Spools ───────────────────────────────────────────────────────────────────
import type { Spool, PrintJob, PrinterConfig, PrinterStatus, DashboardStats, HAEntity, FilamentSubtype } from './types'

export const api = {
  // Spools
  getSpools: () => request<Spool[]>('spools'),
  getSpool: (id: number) => request<Spool>(`spools/${id}`),
  createSpool: (data: Partial<Spool>) =>
    request<Spool>('spools', { method: 'POST', body: JSON.stringify(data) }),
  updateSpool: (id: number, data: Partial<Spool>) =>
    request<Spool>(`spools/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteSpool: (id: number) =>
    request<void>(`spools/${id}`, { method: 'DELETE' }),
  getMaterials: () => request<string[]>('spools/materials/list'),
  getSubtypes: () => request<string[]>('spools/subtypes/list'),

  // Prints
  getPrints: (limit = 50, offset = 0, search?: string, dateFrom?: string, dateTo?: string, tz?: string) => {
    const p = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    if (search) p.set('search', search)
    if (dateFrom) p.set('date_from', dateFrom)
    if (dateTo) p.set('date_to', dateTo)
    if (tz) p.set('timezone', tz)
    return request<PrintJob[]>(`prints?${p}`)
  },
  getPrintsTotal: (search?: string, dateFrom?: string, dateTo?: string, tz?: string) => {
    const p = new URLSearchParams()
    if (search) p.set('search', search)
    if (dateFrom) p.set('date_from', dateFrom)
    if (dateTo) p.set('date_to', dateTo)
    if (tz) p.set('timezone', tz)
    const qs = p.toString()
    return request<{ total: number }>(`prints/count${qs ? `?${qs}` : ''}`)
  },
  getPrint: (id: number) => request<PrintJob>(`prints/${id}`),
  createPrint: (data: unknown) =>
    request<PrintJob>('prints', { method: 'POST', body: JSON.stringify(data) }),
  updatePrint: (id: number, data: unknown) =>
    request<PrintJob>(`prints/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deletePrint: (id: number) =>
    request<void>(`prints/${id}`, { method: 'DELETE' }),

  // Printers
  getPrinters: () => request<PrinterConfig[]>('printers'),
  createPrinter: (data: unknown) =>
    request<PrinterConfig>('printers', { method: 'POST', body: JSON.stringify(data) }),
  updatePrinter: (id: number, data: unknown) =>
    request<PrinterConfig>(`printers/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deletePrinter: (id: number) =>
    request<void>(`printers/${id}`, { method: 'DELETE' }),
  getPrinterStatus: (id: number) =>
    request<PrinterStatus>(`printers/${id}/status`),
  discoverPrinter: (device: string, amsDevice?: string) => {
    const params = new URLSearchParams({ device })
    if (amsDevice) params.set('ams_device', amsDevice)
    return request<import('./types').DiscoverResult>(`printers/discover?${params}`)
  },
  getPrinterAMS: (id: number) =>
    request<import('./types').AMSTray[]>(`printers/${id}/ams`),
  assignAMSTray: (printerId: number, slotKey: string, spoolId: number | null) =>
    request<{ ok: boolean; previous_slot: string | null }>(`printers/${printerId}/ams/${slotKey}/assign`, {
      method: 'POST',
      body: JSON.stringify({ spool_id: spoolId }),
    }),
  syncAMSWeights: (printerId: number) =>
    request<{ updated: { slot_key: string; spool_id: number; spool_name: string; remaining_pct: number; new_weight_g: number }[] }>(
      `printers/${printerId}/ams/sync`, { method: 'POST' }
    ),
  syncAMSTrayWeight: (printerId: number, slotKey: string) =>
    request<{ slot_key: string; spool_id: number; spool_name: string; remaining_pct: number; new_weight_g: number }>(
      `printers/${printerId}/ams/${slotKey}/sync`, { method: 'POST' }
    ),

  // Dashboard
  getDashboard: () => request<DashboardStats>('dashboard'),
  getHAStatus: () => request<{ ha_available: boolean }>('dashboard/ha-status'),

  // App settings
  getBrandWeights: () => request<import('./types').BrandSpoolWeight[]>('settings/brand-weights'),
  createBrandWeight: (data: { brand: string; spool_weight_g: number }) =>
    request<import('./types').BrandSpoolWeight>('settings/brand-weights', { method: 'POST', body: JSON.stringify(data) }),
  updateBrandWeight: (id: number, data: { brand: string; spool_weight_g: number }) =>
    request<import('./types').BrandSpoolWeight>(`settings/brand-weights/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteBrandWeight: (id: number) =>
    request<void>(`settings/brand-weights/${id}`, { method: 'DELETE' }),

  getFilamentSubtypes: () => request<FilamentSubtype[]>('settings/subtypes'),
  createFilamentSubtype: (name: string) =>
    request<FilamentSubtype>('settings/subtypes', { method: 'POST', body: JSON.stringify({ name }) }),
  updateFilamentSubtype: (id: number, name: string) =>
    request<FilamentSubtype>(`settings/subtypes/${id}`, { method: 'PATCH', body: JSON.stringify({ name }) }),
  deleteFilamentSubtype: (id: number) =>
    request<void>(`settings/subtypes/${id}`, { method: 'DELETE' }),

  getFilamentMaterials: () => request<FilamentSubtype[]>('settings/materials'),
  createFilamentMaterial: (name: string) =>
    request<FilamentSubtype>('settings/materials', { method: 'POST', body: JSON.stringify({ name }) }),
  updateFilamentMaterial: (id: number, name: string) =>
    request<FilamentSubtype>(`settings/materials/${id}`, { method: 'PATCH', body: JSON.stringify({ name }) }),
  deleteFilamentMaterial: (id: number) =>
    request<void>(`settings/materials/${id}`, { method: 'DELETE' }),

  getFilamentBrands: () => request<FilamentSubtype[]>('settings/brands'),
  createFilamentBrand: (name: string) =>
    request<FilamentSubtype>('settings/brands', { method: 'POST', body: JSON.stringify({ name }) }),
  updateFilamentBrand: (id: number, name: string) =>
    request<FilamentSubtype>(`settings/brands/${id}`, { method: 'PATCH', body: JSON.stringify({ name }) }),
  deleteFilamentBrand: (id: number) =>
    request<void>(`settings/brands/${id}`, { method: 'DELETE' }),

  getPurchaseLocations: () => request<FilamentSubtype[]>('settings/purchase-locations'),
  createPurchaseLocation: (name: string) =>
    request<FilamentSubtype>('settings/purchase-locations', { method: 'POST', body: JSON.stringify({ name }) }),
  updatePurchaseLocation: (id: number, name: string) =>
    request<FilamentSubtype>(`settings/purchase-locations/${id}`, { method: 'PATCH', body: JSON.stringify({ name }) }),
  deletePurchaseLocation: (id: number) =>
    request<void>(`settings/purchase-locations/${id}`, { method: 'DELETE' }),

  // Version
  getVersion: () => request<{ version: string }>('settings/version'),
  getHALocale: () => request<{ language: string; time_zone: string }>('settings/ha-locale'),

  // Bambu Cloud
  getBambuCloudStatus: () =>
    request<import('./types').BambuCloudStatus>('bambu-cloud/status'),
  bambuCloudLogin: (email: string, password: string, region: string) =>
    request<{ requires_2fa: boolean }>('bambu-cloud/login', {
      method: 'POST',
      body: JSON.stringify({ email, password, region }),
    }),
  bambuCloudVerify: (code: string) =>
    request<{ ok: boolean }>('bambu-cloud/verify', {
      method: 'POST',
      body: JSON.stringify({ code }),
    }),
  bambuCloudLogout: () =>
    request<void>('bambu-cloud/logout', { method: 'DELETE' }),
  bambuCloudCancel2fa: () =>
    request<void>('bambu-cloud/cancel-2fa', { method: 'POST' }),
  getBambuCloudDevices: () =>
    request<import('./types').BambuCloudDevice[]>('bambu-cloud/devices'),
  getBambuCloudPrinterStatus: (serial: string) =>
    request<Record<string, string | null>>(`bambu-cloud/printer/${serial}/status`),
  getBambuCloudDebug: () =>
    request<{
      printer_status_cache: Record<string, Record<string, unknown>>
      ams_cache: Record<string, Record<string, { remain: number | null; material: string; color: string | null; remain_flag: number | null }>>
      mqtt_clients: Record<string, { connected: boolean; printer_id: number | null }>
    }>('bambu-cloud/debug'),
  bambuCloudReconnect: () =>
    request<{ ok: boolean; error?: string }>('bambu-cloud/reconnect', { method: 'POST' }),
  bambuCloudImportPrints: () =>
    request<{ ok: boolean; imported: number; skipped: number; total: number }>('bambu-cloud/import-prints', { method: 'POST' }),
  getBambuCloudPrinterAMS: (serial: string) =>
    request<{ slot_key: string; ha_material: string | null; ha_color_hex: string | null; ha_remaining: string | null }[]>(`bambu-cloud/printer/${serial}/ams`),

  // Data transfer
  exportData: () => fetch(`${BASE}/data/export`).then(r => r.blob()),
  exportSpoolman: () => fetch(`${BASE}/data/export-spoolman`).then(r => r.blob()),
  importData: (bundle: unknown) =>
    request<{ ok: boolean; imported: Record<string, number> }>('data/import', {
      method: 'POST',
      body: JSON.stringify(bundle),
    }),
}
