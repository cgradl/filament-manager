import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { AlertCircle, Wifi, WifiOff, LogOut } from 'lucide-react'
import { api } from '../api'
import type { BambuCloudDevice } from '../types'

export default function BambuCloudSection() {
  const { t } = useTranslation()
  const qc = useQueryClient()

  const [step, setStep] = useState<'form' | '2fa'>('form')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [region, setRegion] = useState('us')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { data: cloudStatus, refetch: refetchStatus } = useQuery({
    queryKey: ['bambu-cloud-status'],
    queryFn: api.getBambuCloudStatus,
    refetchInterval: 5_000,
  })

  const { data: devices = [] } = useQuery<BambuCloudDevice[]>({
    queryKey: ['bambu-cloud-devices'],
    queryFn: api.getBambuCloudDevices,
    enabled: cloudStatus?.status === 'connected',
  })

  const isConnected = cloudStatus?.status === 'connected'
  const isPending2fa = cloudStatus?.status === 'pending_2fa' || step === '2fa'

  // When backend auto-triggers 2FA (expired token refresh), show the code form
  useEffect(() => {
    if (cloudStatus?.status === 'pending_2fa' && step === 'form') {
      setStep('2fa')
    }
  }, [cloudStatus?.status])

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const res = await api.bambuCloudLogin(email, password, region)
      if (res.requires_2fa) {
        setStep('2fa')
        refetchStatus()
      } else {
        refetchStatus()
        qc.invalidateQueries({ queryKey: ['bambu-cloud-devices'] })
        qc.invalidateQueries({ queryKey: ['printers'] })
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await api.bambuCloudVerify(code)
      setStep('form')
      setCode('')
      refetchStatus()
      qc.invalidateQueries({ queryKey: ['bambu-cloud-devices'] })
      qc.invalidateQueries({ queryKey: ['printers'] })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleLogout = async () => {
    setBusy(true)
    try {
      await api.bambuCloudLogout()
      setStep('form')
      setEmail('')
      setPassword('')
      refetchStatus()
      qc.invalidateQueries({ queryKey: ['bambu-cloud-devices'] })
      qc.invalidateQueries({ queryKey: ['printers'] })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      {/* ── Connected state ── */}
      {isConnected && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm text-green-400">
              <Wifi size={15} />
              <span>{t('settings.bambuCloud.connectedAs', { email: cloudStatus?.email })}</span>
              {cloudStatus?.region && cloudStatus.region !== 'us' && (
                <span className="text-[10px] font-mono text-gray-500 uppercase">{cloudStatus.region}</span>
              )}
            </div>
            <button
              onClick={handleLogout}
              disabled={busy}
              className="btn-ghost flex items-center gap-1.5 text-xs text-red-400 hover:text-red-300"
            >
              <LogOut size={13} />
              {t('settings.bambuCloud.disconnect')}
            </button>
          </div>

          <div>
            <p className="text-xs font-medium text-gray-400 mb-2">{t('settings.bambuCloud.devices')}</p>
            {devices.length === 0 ? (
              <p className="text-xs text-gray-500">{t('settings.bambuCloud.noDevices')}</p>
            ) : (
              <div className="space-y-1.5">
                {(devices as BambuCloudDevice[]).map(d => (
                  <div key={d.serial} className="flex items-center gap-2 text-xs text-gray-300 bg-surface-2 rounded px-3 py-2">
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${d.online ? 'bg-green-400' : 'bg-gray-600'}`} />
                    <span className="font-medium">{d.name}</span>
                    <span className="text-gray-500">{d.model}</span>
                    <span className="ml-auto text-gray-600 font-mono text-[10px]">{'•'.repeat(8)}{d.serial.slice(-4)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <p className="text-[11px] text-gray-600">{t('settings.bambuCloud.securityNote')}</p>
        </div>
      )}

      {/* ── Backend error/session-expired banner ── */}
      {!isConnected && !isPending2fa && cloudStatus?.error && (
        <div className="flex items-start gap-2 text-xs text-yellow-400 bg-yellow-900/20 border border-yellow-800 rounded px-3 py-2 mb-3">
          <AlertCircle size={13} className="mt-0.5 shrink-0" />
          <span>{cloudStatus.error}</span>
        </div>
      )}

      {/* ── 2FA step ── */}
      {!isConnected && isPending2fa && (
        <form onSubmit={handleVerify} className="space-y-3">
          <div className="flex items-center gap-2 text-xs text-yellow-400 mb-1">
            <AlertCircle size={14} />
            <span>{t('settings.bambuCloud.twoFaPrompt')}</span>
          </div>
          <div>
            <label className="label">{t('settings.bambuCloud.twoFaCode')}</label>
            <input
              className="input font-mono tracking-widest text-center text-lg"
              value={code}
              onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="000000"
              maxLength={6}
              required
              autoFocus
            />
          </div>
          {error && (
            <div className="flex items-start gap-2 text-xs text-red-400">
              <AlertCircle size={13} className="mt-0.5 shrink-0" />
              <span>{t('settings.bambuCloud.errorVerify', { error })}</span>
            </div>
          )}
          <div className="flex gap-2">
            <button type="submit" disabled={busy || code.length !== 6} className="btn-primary">
              {busy ? t('settings.bambuCloud.verifying') : t('settings.bambuCloud.verify')}
            </button>
            <button
              type="button"
              onClick={async () => {
                setStep('form')
                setError(null)
                setCode('')
                await api.bambuCloudCancel2fa()
                refetchStatus()
              }}
              className="btn-ghost"
            >
              {t('common.cancel')}
            </button>
          </div>
        </form>
      )}

      {/* ── Login form ── */}
      {!isConnected && !isPending2fa && (
        <form onSubmit={handleLogin} className="space-y-3">
          <div>
            <label className="label">{t('settings.bambuCloud.email')}</label>
            <input
              type="email"
              className="input"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
          </div>
          <div>
            <label className="label">{t('settings.bambuCloud.password')}</label>
            <input
              type="password"
              className="input"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
          </div>
          <div>
            <label className="label">{t('settings.bambuCloud.region')}</label>
            <select className="input" value={region} onChange={e => setRegion(e.target.value)}>
              <option value="us">{t('settings.bambuCloud.regionUS')}</option>
              <option value="eu">{t('settings.bambuCloud.regionEU')}</option>
              <option value="cn">{t('settings.bambuCloud.regionCN')}</option>
            </select>
          </div>
          {error && (
            <div className="flex items-start gap-2 text-xs text-red-400">
              <AlertCircle size={13} className="mt-0.5 shrink-0" />
              <span>{t('settings.bambuCloud.errorConnect', { error })}</span>
            </div>
          )}
          <div className="flex items-center gap-3">
            <button type="submit" disabled={busy} className="btn-primary flex items-center gap-2">
              <WifiOff size={13} />
              {busy ? t('settings.bambuCloud.connecting') : t('settings.bambuCloud.connect')}
            </button>
            <p className="text-[11px] text-gray-600">{t('settings.bambuCloud.securityNote')}</p>
          </div>
        </form>
      )}
    </div>
  )
}
