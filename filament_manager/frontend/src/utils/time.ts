/**
 * Timezone-aware date formatting utilities.
 *
 * All timestamps from the backend are naive UTC (no 'Z' suffix).
 * parseUTC() forces correct UTC interpretation before formatting.
 * All display functions accept an IANA timezone string (e.g. "Europe/Berlin")
 * sourced from the HA configuration.
 */

/** Parse a backend ISO string as UTC (appends 'Z' if no offset present). */
export function parseUTC(isoStr: string): Date {
  if (!isoStr) return new Date(NaN)
  const hasOffset = isoStr.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(isoStr)
  return new Date(hasOffset ? isoStr : isoStr + 'Z')
}

/** Format a UTC ISO string as "dd.MM.yyyy HH:mm" in the given timezone. */
export function formatDateTimeTZ(isoStr: string, tz: string): string {
  const d = parseUTC(isoStr)
  if (isNaN(d.getTime())) return ''
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
    hour12: false,
    timeZone: tz,
  }).format(d)
}

/** Format a UTC ISO string as a short date "dd.MM.yyyy" in the given timezone. */
export function formatDateTZ(isoStr: string, tz: string): string {
  const d = parseUTC(isoStr)
  if (isNaN(d.getTime())) return ''
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    timeZone: tz,
  }).format(d)
}

/**
 * Format a YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS date as "dd.MM.yyyy" without
 * timezone conversion — for calendar-date-only fields like purchase_date.
 */
export function formatDateOnly(isoStr: string): string {
  if (!isoStr) return ''
  const [y, m, d] = isoStr.slice(0, 10).split('-')
  if (!y || !m || !d) return ''
  return `${d}.${m}.${y}`
}

/**
 * Convert a UTC ISO string to a local date string "YYYY-MM-DD" in the given
 * timezone — suitable for date-range comparisons.
 */
export function toLocalDateStr(isoStr: string, tz: string): string {
  const d = parseUTC(isoStr)
  if (isNaN(d.getTime())) return ''
  return new Intl.DateTimeFormat('en-CA', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    timeZone: tz,
  }).format(d)
}

/**
 * Return the current datetime as a "YYYY-MM-DDTHH:mm" string in the given
 * timezone — suitable as the default value for <input type="datetime-local">.
 */
export function nowInTZ(tz: string): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
    hour12: false,
    timeZone: tz,
  }).formatToParts(new Date())
  const get = (t: string) => parts.find(p => p.type === t)?.value ?? '00'
  return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`
}
