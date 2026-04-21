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
  storage_location: string | null
  article_number: string | null
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
  spool_id: number | null
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
  fm_project_id: number | null
  project_name: string | null
  print_weight_g: number | null
  nozzle_diameter: string | null
  suggested_usages: SuggestedUsage[] | null
  design_title: string | null
  url: string | null
  energy_kwh: number | null
  energy_cost: number | null
}

export interface Project {
  id: number
  name: string
  description: string | null
  print_count: number
  total_duration_seconds: number
  total_cost: number
  total_grams: number
  total_energy_kwh: number | null
  total_energy_cost: number | null
  nozzle_diameters: string[]
  materials: string[]
  date_first: string | null
  date_last: string | null
  created_at: string
}

export interface ProjectDetail extends Project {
  print_jobs: PrintJob[]
}

export interface PrinterConfig {
  id: number
  name: string
  ams_unit_count: number
  is_active: boolean
  auto_deduct: boolean
  bambu_serial: string | null
  bambu_source: string   // always "cloud"
  energy_sensor_entity_id: string | null
  price_sensor_entity_id: string | null
}

export interface BambuCloudStatus {
  status: 'disconnected' | 'pending_2fa' | 'connected' | 'error'
  email: string | null
  error: string | null
  region: string | null
}

export interface BambuCloudDevice {
  serial: string
  name: string
  model: string
  online: boolean
}

export interface SpoolAuditEntry {
  id: number
  changed_at: string
  action: string
  delta_g: number
  weight_before: number | null
  weight_after: number | null
  print_job_id: number | null
  print_name: string | null
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

export interface FilamentCatalog {
  id: number
  brand: string
  material: string
  subtype: string | null
  subtype2: string | null
  color_name: string
  color_hex: string
  article_number: string | null
  created_at: string
  updated_at: string
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


export interface PrinterStatus {
  print_stage: string | null
  print_progress: string | null
  remaining_time: string | null
  nozzle_temp: string | null
  bed_temp: string | null
  current_file: string | null
  print_weight: string | null
  ams_active: string | null
  active_tray: string | null
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
  running_job: PrintJob | null
  prints_per_day: { date: string; count: number }[]
}

