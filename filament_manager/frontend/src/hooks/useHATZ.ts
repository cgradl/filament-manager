import { useQuery } from '@tanstack/react-query'
import { api } from '../api'

/** Returns the IANA timezone string configured in Home Assistant (e.g. "Europe/Berlin"). */
export function useHATZ(): string {
  const { data } = useQuery({
    queryKey: ['ha-locale'],
    queryFn: api.getHALocale,
    staleTime: Infinity,
  })
  return data?.time_zone ?? 'UTC'
}
