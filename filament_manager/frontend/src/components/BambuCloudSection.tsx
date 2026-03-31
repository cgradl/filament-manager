import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { CheckCircle, AlertCircle, Wifi, WifiOff, LogOut } from 'lucide-react'
import { api } from '../api'
import type { PrinterConfig, BambuCloudDevice } from '../types'

export default function BambuCloudSection() {
  const { t } = useTranslation()
  const qc = useQueryClient()

  const [step, setStep] = useState<'form' | '2fa'>('form')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { data: cloudStatus, refetch: refetchStatus } = useQuery({
    queryKey: ['bambu-cloud-status'],
    queryFn: api.getBambuCloudStatus,
    refetchInterval: 30_000,
  })

  const { data: devices = [] } = useQuery<BambuCloudDevice[]>({
    queryKey: ['bambu-cloud-devices'],
    queryFn: api.getBambuCloudDevices,
    enabled: cloudStatus?.status === 'connected',
  })

  const { data: printers = [] } = useQuery<PrinterConfig[]>({
    queryKey: ['printers'],
    queryFn: api.getPrinters,
  })

  const isConnected = cloudStatus?.status === 'connected'
  const isPending2fa = cloudStatus?.status === 'pending_2fa' || step === '2fa'

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const res = await api.bambuCloudLogin(email, password)
      if (res.requires_2fa) {
        setStep('2fa')
        refetchStatus()
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
    } finally {
      setBusy(false)
    }
  }

  const handleSourceChange = async (printer: PrinterConfig, source: string, serial: string) => {
    await api.updatePrinter(printer.id, {
      ...printer,
      bambu_source: source,
      bambu_serial: source === 'cloud' ? serial : printer.bambu_serial,
    })
    qc.invalidateQueries({ queryKey: ['printers'] })
  }

  return (
    <div className="card">
      {/* Header */}
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-sm font-semibold text-gray-300">{t('settings.bambuCloud.title')}</h3>
        <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-yellow-900/60 text-yellow-400 border border-yellow-700">
          {t('settings.bambuCloud.experimental')}
        </span>
      </div>
      <p className="text-xs text-gray-500 mb-4">{t('settings.bambuCloud.hint')}</p>

      {/* ── Connected state ── */}
      {isConnected && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm text-green-400">
              <Wifi size={15} />
              <span>{t('settings.bambuCloud.connectedAs', { email: cloudStatus?.email })}</span>
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

          {/* Device list */}
          {devices.length > 0 && (
            <div>
              <p className="text-xs font-medium text-gray-400 mb-2">{t('settings.bambuCloud.devices')}</p>
              <div className="space-y-1.5">
                {devices.map(d => (
                  <div key={d.serial} className="flex items-center gap-2 text-xs text-gray-300 bg-surface-2 rounded px-3 py-2">
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${d.online ? 'bg-green-400' : 'bg-gray-600'}`} />
                    <span className="font-medium">{d.name}</span>
                    <span className="text-gray-500">{d.model}</span>
                    <span className="ml-auto text-gray-600 font-mono text-[10px]">{d.serial}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Per-printer source selector */}
          {printers.length > 0 && (
            <div>
              <p className="text-xs font-medium text-gray-400 mb-2">{t('settings.bambuCloud.printerSource')}</p>
              <div className="space-y-2">
                {printers.map(p => (
                  <div key={p.id} className="flex items-center gap-3 text-xs">
                    <span className="text-gray-300 flex-1 truncate">{p.name}</span>
                    <select
                      value={p.bambu_source || 'ha'}
                      onChange={e => {
                        const serial = p.bambu_serial || (devices[0]?.serial ?? '')
                        handleSourceChange(p, e.target.value, serial)
                      }}
                      className="input py-1 text-xs w-36"
                    >
                      <option value="ha">{t('settings.bambuCloud.sourceHA')}</option>
                      <option value="cloud">{t('settings.bambuCloud.sourceCloud')}</option>
                    </select>
                    {p.bambu_source === 'cloud' && (
                      <select
                        value={p.bambu_serial || ''}
                        onChange={e => handleSourceChange(p, 'cloud', e.target.value)}
                        className="input py-1 text-xs w-44"
                      >
                        <option value="">{t('settings.bambuCloud.serialPlaceholder')}</option>
                        {devices.map(d => (
                          <option key={d.serial} value={d.serial}>{d.name} ({d.serial})</option>
                        ))}
                      </select>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
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
            <button type="button" onClick={() => { setStep('form'); setError(null) }} className="btn-ghost">
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
