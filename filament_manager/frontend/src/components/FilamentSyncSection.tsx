import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { RefreshCw, ArrowDownToLine, ArrowUpFromLine, ArrowLeftRight, Ban } from 'lucide-react'
import { api } from '../api'
import type { SyncMode } from '../types'
import { formatDateTimeTZ } from '../utils/time'
import { useHATZ } from '../hooks/useHATZ'
import SyncReviewModal from './SyncReviewModal'

const MODES: { value: SyncMode; icon: React.ReactNode }[] = [
  { value: 'off',           icon: <Ban size={12} /> },
  { value: 'pull',          icon: <ArrowDownToLine size={12} /> },
  { value: 'push',          icon: <ArrowUpFromLine size={12} /> },
  { value: 'bidirectional', icon: <ArrowLeftRight size={12} /> },
]

export default function FilamentSyncSection({ isCloudConnected }: { isCloudConnected: boolean }) {
  const { t } = useTranslation()
  const tz = useHATZ()
  const qc = useQueryClient()
  const [showModal, setShowModal] = useState(false)

  const { data: syncStatus, isLoading } = useQuery({
    queryKey: ['filament-sync-status'],
    queryFn: api.getFilamentSyncStatus,
    refetchInterval: 30_000,
  })

  const settingsMut = useMutation({
    mutationFn: api.patchFilamentSyncSettings,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['filament-sync-status'] }),
  })

  if (isLoading || !syncStatus) return null

  if (!isCloudConnected) {
    return <p className="text-xs text-yellow-500">{t('settings.filamentSync.requiresCloud')}</p>
  }

  const currentMode = syncStatus.sync_mode ?? 'off'
  const busy = settingsMut.isPending

  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500">{t('settings.filamentSync.hint')}</p>

      {/* Mode selector */}
      <div>
        <label className="label mb-1">{t('settings.filamentSync.syncMode')}</label>
        <div className="flex gap-2 flex-wrap">
          {MODES.map(({ value, icon }) => (
            <button
              key={value}
              onClick={() => settingsMut.mutate({ sync_mode: value })}
              disabled={busy}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs border transition-colors
                ${currentMode === value
                  ? 'bg-blue-600 border-blue-500 text-white'
                  : 'bg-surface-2 border-gray-600 text-gray-400 hover:border-gray-400 hover:text-gray-200'}`}
            >
              {busy && currentMode !== value ? null : icon}
              {t(`settings.filamentSync.mode_${value}`)}
            </button>
          ))}
        </div>
        <p className="text-xs text-gray-500 mt-1.5">
          {t(`settings.filamentSync.modeHint_${currentMode}`)}
        </p>
      </div>

      {/* Stats */}
      {currentMode !== 'off' && (
        <div className="flex flex-wrap gap-4 text-xs text-gray-400">
          <span>
            {t('settings.filamentSync.linked', {
              n: syncStatus.linked_spools,
              total: syncStatus.total_spools,
            })}
          </span>
          {syncStatus.last_sync_at && (
            <span>
              {t('settings.filamentSync.lastSync', {
                date: formatDateTimeTZ(syncStatus.last_sync_at, tz),
              })}
            </span>
          )}
        </div>
      )}

      {/* Sync Now button */}
      {currentMode !== 'off' && (
        <button
          onClick={() => setShowModal(true)}
          className="btn-primary flex items-center gap-1.5 text-xs"
        >
          <RefreshCw size={13} />
          {t('settings.filamentSync.syncNow')}
        </button>
      )}

      {showModal && (
        <SyncReviewModal
          syncMode={currentMode as Exclude<SyncMode, 'off'>}
          onClose={() => {
            setShowModal(false)
            qc.invalidateQueries({ queryKey: ['filament-sync-status'] })
            qc.invalidateQueries({ queryKey: ['spools'] })
          }}
        />
      )}
    </div>
  )
}
