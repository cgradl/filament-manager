/**
 * Parse a user-entered decimal number that may use either a comma or a dot
 * as the decimal separator (German keyboards/locales enter "12,50").
 *
 * Returns null for empty input or anything that is not a plain decimal —
 * Number() (unlike parseFloat) rejects trailing garbage, so "12,50" never
 * silently truncates to 12.
 */
export function parseDecimal(raw: string): number | null {
  const s = raw.trim().replace(',', '.')
  if (s === '') return null
  const n = Number(s)
  return Number.isFinite(n) ? n : null
}
