export interface Spool {
  id: number
  custom_id: number | null
  brand: string
  material: string
  subtype: string | null
  subtype2: string | null
  color_name: string
  color_hex: string
  diameter_mm: number
  initial_weight_g: number
  current_weight_g: number
  spool_weight_g: number
  purchase_price: number | null
  purchased_at: string | null
  purchase_location: string | null
  ams_slot: string | null
  notes: string | null
  remaining_pct: number
  price_per_kg: number | null
  cost_per_gram: number | null
  created_at: string
  updated_at: string
}

export interface PrintUsage {
  id: number
  print_job_id: number
  spool_id: number
  grams_used: number
  meters_used: number | null
  ams_slot: string | null
  cost: number | null
  spool: Spool | null
}

export interface SuggestedUsage {
  ams_slot: string
  grams: number
  filament_type: string
  color: string | null
}

export interface PrintJob {
  id: number
  name: string
  model_name: string | null
  description: string | null
  started_at: string
  finished_at: string | null
  duration_seconds: number | null
  duration_hours: number | null
  success: boolean
  notes: string | null
  printer_name: string | null
  source: string
  total_grams: number
  total_cost: number
  usages: PrintUsage[]
  created_at: string
  print_weight_g: number | null
  suggested_usages: SuggestedUsage[] | null
}

export interface PrinterConfig {
  id: number
  name: string
  device_slug: string
  ams_device_slug: string | null
  ams_unit_count: number
  is_active: boolean
  bambu_serial: string | null
  bambu_source: string   // "ha" | "cloud"
  sensor_print_stage:    string | null
  sensor_print_progress: string | null
  sensor_remaining_time: string | null
  sensor_nozzle_temp:    string | null
  sensor_bed_temp:       string | null
  sensor_current_file:   string | null
  sensor_print_weight:   string | null
  ams_tray_pattern:  string | null
  ams_suffix_type:   string | null
  ams_suffix_color:  string | null
  ams_suffix_remain: string | null
}

export interface BambuCloudStatus {
  status: 'disconnected' | 'pending_2fa' | 'connected' | 'error'
  email: string | null
  error: string | null
}

export interface BambuCloudDevice {
  serial: string
  name: string
  model: string
  online: boolean
}

export interface BrandSpoolWeight {
  id: number
  brand: string
  spool_weight_g: number
}

export interface FilamentSubtype {
  id: number
  name: string
}

export interface AMSTray {
  slot_key: string
  ams_id: number
  tray: number
  ha_material: string | null
  ha_color_hex: string | null
  ha_remaining: string | null
  spool: Spool | null
}

export interface DiscoverResult {
  slug: string
  printer_entities: Record<string, { entity_id: string; found: boolean; state: string | null }>
  ams_preview: { ams_id: number; trays: { slot: number; entity_remaining: string; found: boolean; state: string | null }[] }[]
  all_matching: { entity_id: string; state: string; friendly_name: string }[]
}

export interface PrinterStatus {
  print_stage: string | null
  print_progress: string | null
  remaining_time: string | null
  nozzle_temp: string | null
  bed_temp: string | null
  current_file: string | null
  [key: string]: string | null
}

export interface MaterialBreakdown {
  material: string
  count: number
  current_kg: number
}

export interface PriceByLocation {
  location: string
  avg_price: number
  count: number
}

export interface PrinterHours {
  printer: string
  hours: number
}

export interface DashboardStats {
  total_spools: number
  active_spools: number
  empty_spools: number
  low_stock_spools: number
  total_filament_kg: number
  total_printed_kg: number
  total_available_kg: number
  total_filament_spent_eur: number
  total_print_cost_eur: number
  total_available_eur: number
  total_prints: number
  material_breakdown: MaterialBreakdown[]
  price_by_location: PriceByLocation[]
  printer_hours: PrinterHours[]
  recent_prints: PrintJob[]
  low_stock: Spool[]
}

export interface HAEntity {
  entity_id: string
  friendly_name: string
  state: string
}
