import type { AMSTray, Spool } from '../types'

// Strip '#' prefix and alpha channel suffix, uppercase — e.g. "#ff5733ff" → "FF5733"
function normalizeHex(hex: string): string {
  return hex.replace(/^#/, '').slice(0, 6).toUpperCase()
}

/**
 * Find the best spool for a given AMS tray based on material + color match.
 * Tie-breaking: lowest remaining weight first (use partial spools), then oldest
 * purchase date (FiFo).  Returns null if no spool matches or tray has no MQTT data.
 */
export function findBestSpoolMatch(tray: AMSTray, spools: Spool[]): Spool | null {
  if (!tray.ha_material || !tray.ha_color_hex) return null

  const mat = tray.ha_material.toLowerCase()
  const col = normalizeHex(tray.ha_color_hex)

  const candidates = spools.filter(s => {
    const spoolMat = s.subtype
      ? `${s.material} ${s.subtype}`.toLowerCase()
      : s.material.toLowerCase()
    return (
      (s.material.toLowerCase() === mat || spoolMat === mat) &&
      normalizeHex(s.color_hex) === col &&
      s.current_weight_g > 0
    )
  })

  if (candidates.length === 0) return null

  return [...candidates].sort((a, b) => {
    const dw = a.current_weight_g - b.current_weight_g
    if (dw !== 0) return dw
    const aDate = a.purchased_at ? new Date(a.purchased_at).getTime() : Infinity
    const bDate = b.purchased_at ? new Date(b.purchased_at).getTime() : Infinity
    return aDate - bDate
  })[0]
}
