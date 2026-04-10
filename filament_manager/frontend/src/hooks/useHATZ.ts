import { useQuery } from '@tanstack/react-query'
import { api } from '../api'

function useHALocaleData() {
  return useQuery({
    queryKey: ['ha-locale'],
    queryFn: api.getHALocale,
    staleTime: Infinity,
  })
}

/** Returns the IANA timezone string configured in Home Assistant (e.g. "Europe/Berlin"). */
export function useHATZ(): string {
  const { data } = useHALocaleData()
  return data?.time_zone ?? 'UTC'
}

/** Returns the ISO 4217 currency code configured in Home Assistant (e.g. "EUR", "USD"). */
export function useHACurrency(): string {
  const { data } = useHALocaleData()
  return data?.currency ?? 'EUR'
}

/**
 * Returns an Intl.NumberFormat instance for formatting currency values using
 * the HA-configured currency and the current document locale (for symbol placement).
 */
export function useCurrencyFormatter(): (amount: number) => string {
  const currency = useHACurrency()
  const locale = typeof document !== 'undefined' ? document.documentElement.lang || undefined : undefined
  const fmt = new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return (amount: number) => fmt.format(amount)
}
