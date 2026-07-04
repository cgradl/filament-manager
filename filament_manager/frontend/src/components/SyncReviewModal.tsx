import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, AlertCircle, CheckCircle, RefreshCw, ChevronDown, ChevronRight } from 'lucide-react'
import { api } from '../api'
import type {
  SyncMode,
  FilamentSyncPlan,
  FilamentSyncResult,
  SyncMatchSuggestion,
  SyncCloudDeleted,
  ApplySyncRequest,
  DeletedAction,
} from '../types'
import Modal from './Modal'

type Phase = 'loading' | 'review' | 'applying' | 'done' | 'error'

interface Props {
  syncMode: Exclude<SyncMode, 'off'>
  onClose: () => void
}

function ColorDot({ hex, size = 10 }: { hex: string; size?: number }) {
  return (
    <span
      className="inline-block rounded-full shrink-0 ring-1 ring-white/10"
      style={{ width: size, height: size, background: hex }}
    />
  )
}

function ConfidenceBadge({ score }: { score: number }) {
  const color =
    score >= 80 ? 'bg-green-900/40 text-green-400 border-green-700' :
    score >= 60 ? 'bg-blue-900/40 text-blue-400 border-blue-700' :
                  'bg-yellow-900/40 text-yellow-400 border-yellow-700'
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${color}`}>
      {score}%
    </span>
  )
}

function Section({
  title,
  count,
  defaultOpen = true,
  children,
}: {
  title: string
  count: number
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border border-gray-700 rounded-lg overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-4 py-3 bg-surface-2 hover:bg-gray-700/50 text-left transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        <span className="text-sm font-medium text-gray-200">{title}</span>
        <span className="flex items-center gap-2">
          <span className="text-xs text-gray-500 bg-gray-700 rounded-full px-2 py-0.5">{count}</span>
          {open ? <ChevronDown size={14} className="text-gray-400" /> : <ChevronRight size={14} className="text-gray-400" />}
        </span>
      </button>
      {open && <div className="p-4 space-y-3 bg-surface-1">{children}</div>}
    </div>
  )
}

export default function SyncReviewModal({ syncMode, onClose }: Props) {
  const { t } = useTranslation()
  const [phase, setPhase] = useState<Phase>('loading')
  const [plan, setPlan] = useState<FilamentSyncPlan | null>(null)
  const [result, setResult] = useState<FilamentSyncResult | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // User selections
  const [checkedMatches, setCheckedMatches] = useState<Set<string>>(new Set())   // `${local_id}:${cloud_id}`
  const [checkedImport, setCheckedImport]   = useState<Set<string>>(new Set())   // cloud_ids
  const [checkedPush, setCheckedPush]       = useState<Set<number>>(new Set())   // local_ids
  const [deletedActions, setDeletedActions] = useState<Record<number, 'archive' | 'keep' | 'delete'>>({})

  // Fetch preview on mount
  useEffect(() => {
    let cancelled = false
    api.filamentSyncPreview()
      .then(p => {
        if (cancelled) return
        setPlan(p)
        // Pre-populate selections
        const matchSet = new Set<string>()
        p.match_suggestions.forEach(s => {
          if (s.pre_checked) matchSet.add(`${s.local_id}:${s.cloud_id}`)
        })
        setCheckedMatches(matchSet)
        setCheckedImport(new Set(p.cloud_only.map(c => c.cloud_id)))
        setCheckedPush(new Set(p.local_only.map(l => l.local_id)))
        const actions: Record<number, 'archive' | 'keep' | 'delete'> = {}
        p.cloud_deleted.forEach(d => { actions[d.local_id] = 'archive' })
        setDeletedActions(actions)
        setPhase('review')
      })
      .catch(err => {
        if (cancelled) return
        setErrorMsg(err instanceof Error ? err.message : String(err))
        setPhase('error')
      })
    return () => { cancelled = true }
  }, [])

  const toggleMatch = (key: string) =>
    setCheckedMatches(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })

  const toggleImport = (cloudId: string) =>
    setCheckedImport(prev => {
      const next = new Set(prev)
      next.has(cloudId) ? next.delete(cloudId) : next.add(cloudId)
      return next
    })

  const togglePush = (localId: number) =>
    setCheckedPush(prev => {
      const next = new Set(prev)
      next.has(localId) ? next.delete(localId) : next.add(localId)
      return next
    })

  const setDeleteAction = (localId: number, action: 'archive' | 'keep' | 'delete') =>
    setDeletedActions(prev => ({ ...prev, [localId]: action }))

  const handleApply = async () => {
    if (!plan) return
    setPhase('applying')

    const confirmed_matches = plan.match_suggestions
      .filter(s => checkedMatches.has(`${s.local_id}:${s.cloud_id}`))
      .map(s => ({ local_id: s.local_id, cloud_id: s.cloud_id }))

    const deleted_actions: DeletedAction[] = plan.cloud_deleted.map(d => ({
      local_id: d.local_id,
      action: deletedActions[d.local_id] ?? 'archive',
    }))

    const body: ApplySyncRequest = {
      confirmed_matches,
      import_from_cloud: Array.from(checkedImport),
      push_to_cloud: Array.from(checkedPush),
      deleted_actions,
    }

    try {
      const res = await api.filamentSyncApply(body)
      setResult(res)
      setPhase('done')
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : String(err))
      setPhase('error')
    }
  }

  const showImport = syncMode === 'pull' || syncMode === 'bidirectional'
  const showPush   = syncMode === 'push'  || syncMode === 'bidirectional'

  const hasAnything =
    (plan?.match_suggestions.length ?? 0) > 0 ||
    (showImport && (plan?.cloud_only.length ?? 0) > 0) ||
    (showPush   && (plan?.local_only.length ?? 0) > 0) ||
    (showImport && (plan?.cloud_deleted.length ?? 0) > 0)

  return (
    <Modal>
      {/* Full-screen overlay + backdrop, matching the app's other modals. Without it the
          portaled panel renders as an unpositioned in-flow block at the end of <body> —
          i.e. below the fold / invisible (the modal mounts and works, it just never shows). */}
      <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="flex flex-col bg-surface-2 border border-surface-3 rounded-2xl" style={{ maxHeight: '85vh', width: 'min(680px, 96vw)' }}>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-700 shrink-0">
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold text-gray-100">
              {t('settings.filamentSync.modal.title')}
            </h2>
            <span className="text-[10px] px-2 py-0.5 rounded bg-blue-900/40 border border-blue-700 text-blue-400 capitalize">
              {t(`settings.filamentSync.mode_${syncMode}`)}
            </span>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-200 transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1 px-5 py-4 space-y-3">
          {/* Loading */}
          {phase === 'loading' && (
            <div className="flex items-center gap-3 py-8 justify-center text-gray-400">
              <RefreshCw size={18} className="animate-spin" />
              <span className="text-sm">{t('settings.filamentSync.modal.loading')}</span>
            </div>
          )}

          {/* Error */}
          {phase === 'error' && (
            <div className="flex items-start gap-2 text-sm text-red-400 bg-red-900/20 border border-red-800 rounded px-3 py-2">
              <AlertCircle size={14} className="mt-0.5 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Done */}
          {phase === 'done' && result && (
            <div className="space-y-3">
              <div className="flex items-start gap-2 text-sm text-green-400 bg-green-900/20 border border-green-800 rounded px-3 py-2">
                <CheckCircle size={14} className="mt-0.5 shrink-0" />
                <span>
                  {t('settings.filamentSync.modal.result', {
                    matched:  result.matched,
                    imported: result.imported,
                    pushed:   result.pushed,
                    archived: result.archived,
                    deleted:  result.deleted,
                    errors:   result.errors,
                  })}
                </span>
              </div>
              {result.errors > 0 && (
                <p className="text-xs text-yellow-400">
                  {t('settings.filamentSync.modal.resultErrors', { n: result.errors })}
                </p>
              )}
            </div>
          )}

          {/* Review sections */}
          {(phase === 'review' || phase === 'applying') && plan && (
            <>
              {/* Already linked */}
              {plan.already_linked_count > 0 && (
                <Section
                  title={t('settings.filamentSync.modal.alreadyLinked')}
                  count={plan.already_linked_count}
                  defaultOpen={false}
                >
                  <p className="text-xs text-gray-400">
                    {t('settings.filamentSync.modal.alreadyLinkedDesc', {
                      n: plan.already_linked_count,
                    })}
                  </p>
                </Section>
              )}

              {/* Match suggestions */}
              {plan.match_suggestions.length > 0 && (
                <Section
                  title={t('settings.filamentSync.modal.suggestions')}
                  count={plan.match_suggestions.length}
                >
                  <p className="text-xs text-gray-500 mb-2">
                    {t('settings.filamentSync.modal.suggestionsHint')}
                  </p>
                  <div className="space-y-2">
                    {plan.match_suggestions.map(s => {
                      const key = `${s.local_id}:${s.cloud_id}`
                      const checked = checkedMatches.has(key)
                      return (
                        <label
                          key={key}
                          className={`flex items-center gap-3 p-2.5 rounded cursor-pointer border transition-colors
                            ${checked
                              ? 'bg-blue-900/20 border-blue-700'
                              : 'bg-surface-2 border-gray-700 hover:border-gray-500'}`}
                        >
                          <input
                            type="checkbox"
                            className="accent-blue-500 shrink-0"
                            checked={checked}
                            onChange={() => toggleMatch(key)}
                            disabled={phase === 'applying'}
                          />
                          <div className="flex items-center gap-1.5 min-w-0 flex-1">
                            <ColorDot hex={s.local_color_hex} />
                            <span className="text-xs text-gray-200 truncate">{s.local_summary}</span>
                          </div>
                          <span className="text-gray-500 text-xs shrink-0">↔</span>
                          <div className="flex items-center gap-1.5 min-w-0 flex-1">
                            <ColorDot hex={s.cloud_color_hex} />
                            <span className="text-xs text-gray-200 truncate">{s.cloud_summary}</span>
                          </div>
                          <ConfidenceBadge score={s.confidence} />
                        </label>
                      )
                    })}
                  </div>
                </Section>
              )}

              {/* Import from cloud */}
              {showImport && plan.cloud_only.length > 0 && (
                <Section
                  title={t('settings.filamentSync.modal.newFromCloud')}
                  count={plan.cloud_only.length}
                >
                  <p className="text-xs text-gray-500 mb-2">
                    {t('settings.filamentSync.modal.newFromCloudHint')}
                  </p>
                  <div className="space-y-1.5">
                    {plan.cloud_only.map(c => (
                      <label
                        key={c.cloud_id}
                        className={`flex items-center gap-3 p-2.5 rounded cursor-pointer border transition-colors
                          ${checkedImport.has(c.cloud_id)
                            ? 'bg-green-900/20 border-green-800'
                            : 'bg-surface-2 border-gray-700 hover:border-gray-500'}`}
                      >
                        <input
                          type="checkbox"
                          className="accent-green-500 shrink-0"
                          checked={checkedImport.has(c.cloud_id)}
                          onChange={() => toggleImport(c.cloud_id)}
                          disabled={phase === 'applying'}
                        />
                        <ColorDot hex={c.color_hex} />
                        <span className="text-xs text-gray-200 flex-1 truncate">{c.cloud_summary}</span>
                        <span className="text-xs text-gray-500 shrink-0">
                          {c.filament_type} · {c.current_weight_g}g
                        </span>
                      </label>
                    ))}
                  </div>
                </Section>
              )}

              {/* Push to cloud */}
              {showPush && plan.local_only.length > 0 && (
                <Section
                  title={t('settings.filamentSync.modal.pushToCloud')}
                  count={plan.local_only.length}
                >
                  <p className="text-xs text-gray-500 mb-2">
                    {t('settings.filamentSync.modal.pushToCloudHint')}
                  </p>
                  <div className="space-y-1.5">
                    {plan.local_only.map(l => (
                      <label
                        key={l.local_id}
                        className={`flex items-center gap-3 p-2.5 rounded cursor-pointer border transition-colors
                          ${checkedPush.has(l.local_id)
                            ? 'bg-blue-900/20 border-blue-700'
                            : 'bg-surface-2 border-gray-700 hover:border-gray-500'}`}
                      >
                        <input
                          type="checkbox"
                          className="accent-blue-500 shrink-0"
                          checked={checkedPush.has(l.local_id)}
                          onChange={() => togglePush(l.local_id)}
                          disabled={phase === 'applying'}
                        />
                        <ColorDot hex={l.color_hex} />
                        <span className="text-xs text-gray-200 flex-1 truncate">{l.local_summary}</span>
                      </label>
                    ))}
                  </div>
                </Section>
              )}

              {/* Deleted from cloud */}
              {showImport && plan.cloud_deleted.length > 0 && (
                <Section
                  title={t('settings.filamentSync.modal.deletedFromCloud')}
                  count={plan.cloud_deleted.length}
                >
                  <p className="text-xs text-gray-500 mb-2">
                    {t('settings.filamentSync.modal.deletedFromCloudHint')}
                  </p>
                  <div className="space-y-2">
                    {plan.cloud_deleted.map((d: SyncCloudDeleted) => (
                      <div key={d.local_id} className="flex items-center gap-3 p-2.5 rounded bg-surface-2 border border-yellow-800/50">
                        <span className="text-xs text-gray-200 flex-1 truncate">{d.local_summary}</span>
                        <div className="flex gap-1 shrink-0">
                          {(['archive', 'keep', 'delete'] as const).map(action => (
                            <button
                              key={action}
                              onClick={() => setDeleteAction(d.local_id, action)}
                              disabled={phase === 'applying'}
                              className={`px-2 py-1 rounded text-[10px] border transition-colors
                                ${deletedActions[d.local_id] === action
                                  ? action === 'delete'
                                    ? 'bg-red-700 border-red-600 text-white'
                                    : 'bg-blue-600 border-blue-500 text-white'
                                  : 'bg-surface-1 border-gray-600 text-gray-400 hover:border-gray-400'}`}
                            >
                              {t(`settings.filamentSync.modal.action_${action}`)}
                            </button>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </Section>
              )}

              {/* Empty state */}
              {!hasAnything && (
                <div className="py-8 text-center text-sm text-gray-500">
                  {t('settings.filamentSync.modal.nothingToDo')}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-gray-700 shrink-0">
          {phase === 'done' || phase === 'error' ? (
            <button onClick={onClose} className="btn-primary text-sm">
              {t('common.close')}
            </button>
          ) : (
            <>
              <button
                onClick={onClose}
                disabled={phase === 'applying'}
                className="btn-ghost text-sm"
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={handleApply}
                disabled={phase !== 'review' || !plan}
                className="btn-primary flex items-center gap-1.5 text-sm"
              >
                {phase === 'applying' && <RefreshCw size={13} className="animate-spin" />}
                {t('settings.filamentSync.modal.apply')}
              </button>
            </>
          )}
        </div>
      </div>
      </div>
    </Modal>
  )
}
