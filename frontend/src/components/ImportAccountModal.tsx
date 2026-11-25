import { FormEvent, useState } from 'react'
import { FileArchive, FileKey2, Smartphone, Upload, X } from 'lucide-react'
import { api } from '../api/client'
import type { AccountRole, ProxyItem } from '../types/api'

interface ImportAccountModalProps {
  proxies: ProxyItem[]
  onClose: () => void
  onSuccess: () => void
}

type ImportTab = 'tdata' | 'session' | 'phone'

/**
 * 三合一账号导入弹窗：支持 tdata 压缩包、.session 文件、手机号验证码/2FA 分步登录。
 */
export function ImportAccountModal({
  proxies,
  onClose,
  onSuccess,
}: ImportAccountModalProps) {
  const [activeTab, setActiveTab] = useState<ImportTab>('tdata')
  const availableProxies = proxies.filter((p) => p.bound_account_count < p.max_accounts)
  const [proxyId, setProxyId] = useState<string>(
    availableProxies[0] ? String(availableProxies[0].id) : '',
  )
  const [accountRole, setAccountRole] = useState<AccountRole>('worker')
  const [countryCode, setCountryCode] = useState('')
  const [twoFa, setTwoFa] = useState('')

  // Tab 1: tdata
  const [tdataFile, setTdataFile] = useState<File | null>(null)

  // Tab 2: session
  const [sessionFile, setSessionFile] = useState<File | null>(null)
  const [jsonFile, setJsonFile] = useState<File | null>(null)

  // Tab 3: phone login
  const [phone, setPhone] = useState('')
  const [platform, setPlatform] = useState<'android' | 'ios' | 'desktop'>('android')
  const [loginToken, setLoginToken] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [need2fa, setNeed2fa] = useState(false)

  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleTdataSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!tdataFile || !proxyId) {
      setError('请先选择可用代理和 tdata .zip 文件')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const formData = new FormData()
      formData.append('file', tdataFile)
      formData.append('proxy_id', proxyId)
      formData.append('account_role', accountRole)
      if (countryCode.trim()) formData.append('country_code', countryCode.trim())
      if (twoFa) formData.append('two_fa', twoFa)
      await api.importTdata(formData)
      onSuccess()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'tdata 导入失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleSessionSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!sessionFile || !proxyId) {
      setError('请先选择可用代理和 .session 文件')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const formData = new FormData()
      formData.append('session_file', sessionFile)
      if (jsonFile) formData.append('json_file', jsonFile)
      formData.append('proxy_id', proxyId)
      formData.append('account_role', accountRole)
      if (countryCode.trim()) formData.append('country_code', countryCode.trim())
      if (twoFa) formData.append('two_fa', twoFa)
      await api.importSession(formData)
      onSuccess()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Session 导入失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleSendCode = async (e: FormEvent) => {
    e.preventDefault()
    if (!phone.trim() || !proxyId) {
      setError('请输入国际格式手机号并选择可用代理')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const resp = await api.phoneSendCode({
        phone: phone.trim(),
        proxy_id: Number(proxyId),
        platform,
        country_code: countryCode.trim() || undefined,
        account_role: accountRole,
      })
      setLoginToken(resp.login_token)
    } catch (err) {
      setError(err instanceof Error ? err.message : '发送验证码失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleVerifyCode = async (e: FormEvent) => {
    e.preventDefault()
    if (!loginToken || !code.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      const resp = await api.phoneVerify({
        login_token: loginToken,
        code: code.trim(),
        two_fa: twoFa || undefined,
      })
      if (resp.need_2fa) {
        setNeed2fa(true)
        setError('该账号开启了二步验证，请输入 2FA 密码后再次提交')
        return
      }
      onSuccess()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : '验证码校验失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
      <div className="w-full max-w-xl rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-800">
          <h3 className="text-lg font-semibold">三合一账号安全导入</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 3 个导入 Tab */}
        <div className="grid grid-cols-3 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/40 text-sm">
          <button
            type="button"
            onClick={() => {
              setActiveTab('tdata')
              setError(null)
            }}
            className={`py-3 inline-flex items-center justify-center gap-2 font-medium border-b-2 transition-colors ${
              activeTab === 'tdata'
                ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
                : 'border-transparent text-slate-500'
            }`}
          >
            <FileArchive className="w-4 h-4" />
            tdata 压缩包
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveTab('session')
              setError(null)
            }}
            className={`py-3 inline-flex items-center justify-center gap-2 font-medium border-b-2 transition-colors ${
              activeTab === 'session'
                ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
                : 'border-transparent text-slate-500'
            }`}
          >
            <FileKey2 className="w-4 h-4" />
            .session 导入
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveTab('phone')
              setError(null)
            }}
            className={`py-3 inline-flex items-center justify-center gap-2 font-medium border-b-2 transition-colors ${
              activeTab === 'phone'
                ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
                : 'border-transparent text-slate-500'
            }`}
          >
            <Smartphone className="w-4 h-4" />
            手机号登录
          </button>
        </div>

        <div className="p-6 space-y-4">
          {/* 公共绑定参数：强制先选代理 */}
          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2">
              <label className="block text-xs text-slate-500 mb-1">绑定代理节点（必选，导入前强制探活）</label>
              <select
                value={proxyId}
                onChange={(e) => setProxyId(e.target.value)}
                className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
              >
                {availableProxies.length === 0 ? (
                  <option value="">暂无可用代理（请先去代理池添加）</option>
                ) : (
                  availableProxies.map((p) => (
                    <option key={p.id} value={p.id}>
                      #{p.id} {p.name} ({p.bound_account_count}/{p.max_accounts})
                    </option>
                  ))
                )}
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">账号角色</label>
              <select
                value={accountRole}
                onChange={(e) => setAccountRole(e.target.value as AccountRole)}
                className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
              >
                <option value="worker">任务号 (worker)</option>
                <option value="listener">常驻监听 (listener)</option>
                <option value="publisher">发帖号 (publisher)</option>
              </select>
            </div>
          </div>

          {error && (
            <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-600 dark:text-rose-400 text-xs">
              {error}
            </div>
          )}

          {activeTab === 'tdata' && (
            <form onSubmit={handleTdataSubmit} className="space-y-4">
              <label className="flex flex-col items-center justify-center p-6 border-2 border-dashed border-slate-300 dark:border-slate-700 rounded-xl cursor-pointer hover:border-indigo-500 transition-colors">
                <Upload className="w-8 h-8 text-slate-400 mb-2" />
                <span className="text-sm font-medium">
                  {tdataFile ? tdataFile.name : '点击选择包含 tdata/ 目录的 .zip 压缩包'}
                </span>
                <input
                  type="file"
                  accept=".zip"
                  className="hidden"
                  onChange={(e) => setTdataFile(e.target.files?.[0] ?? null)}
                />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <input
                  value={countryCode}
                  onChange={(e) => setCountryCode(e.target.value)}
                  placeholder="国家码（可选，如 US）"
                  className="px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
                <input
                  type="password"
                  value={twoFa}
                  onChange={(e) => setTwoFa(e.target.value)}
                  placeholder="2FA 密码（可选，加密保存）"
                  className="px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={submitting || !proxyId}
                  className="px-4 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50"
                >
                  {submitting ? '转换并探活中...' : '开始导入'}
                </button>
              </div>
            </form>
          )}

          {activeTab === 'session' && (
            <form onSubmit={handleSessionSubmit} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <label className="flex flex-col items-center justify-center p-4 border-2 border-dashed border-slate-300 dark:border-slate-700 rounded-xl cursor-pointer hover:border-indigo-500">
                  <span className="text-xs font-medium text-center">
                    {sessionFile ? sessionFile.name : '选择 .session 文件（必选）'}
                  </span>
                  <input
                    type="file"
                    accept=".session"
                    className="hidden"
                    onChange={(e) => setSessionFile(e.target.files?.[0] ?? null)}
                  />
                </label>
                <label className="flex flex-col items-center justify-center p-4 border-2 border-dashed border-slate-300 dark:border-slate-700 rounded-xl cursor-pointer hover:border-indigo-500">
                  <span className="text-xs font-medium text-center text-slate-500">
                    {jsonFile ? jsonFile.name : '选择设备 .json（可选）'}
                  </span>
                  <input
                    type="file"
                    accept=".json"
                    className="hidden"
                    onChange={(e) => setJsonFile(e.target.files?.[0] ?? null)}
                  />
                </label>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <input
                  value={countryCode}
                  onChange={(e) => setCountryCode(e.target.value)}
                  placeholder="国家码（可选，如 US）"
                  className="px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
                <input
                  type="password"
                  value={twoFa}
                  onChange={(e) => setTwoFa(e.target.value)}
                  placeholder="2FA 密码（可选）"
                  className="px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={submitting || !proxyId}
                  className="px-4 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50"
                >
                  {submitting ? '校验并固化指纹中...' : '验证并导入'}
                </button>
              </div>
            </form>
          )}

          {activeTab === 'phone' && (
            <form
              onSubmit={loginToken ? handleVerifyCode : handleSendCode}
              className="space-y-4"
            >
              <div className="grid grid-cols-3 gap-3">
                <input
                  required
                  disabled={Boolean(loginToken)}
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="手机号（如 +12025550101）"
                  className="col-span-2 px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 disabled:opacity-60"
                />
                <select
                  disabled={Boolean(loginToken)}
                  value={platform}
                  onChange={(e) =>
                    setPlatform(e.target.value as 'android' | 'ios' | 'desktop')
                  }
                  className="px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                >
                  <option value="android">Android 指纹</option>
                  <option value="ios">iOS 指纹</option>
                  <option value="desktop">Desktop 指纹</option>
                </select>
              </div>

              {loginToken && (
                <div className="space-y-3 p-4 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700">
                  <input
                    required
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    placeholder="输入收到的 5 位 Telegram 验证码"
                    className="w-full px-3 py-2 text-sm rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700"
                  />
                  {need2fa && (
                    <input
                      required
                      type="password"
                      value={twoFa}
                      onChange={(e) => setTwoFa(e.target.value)}
                      placeholder="输入二步验证（2FA）密码"
                      className="w-full px-3 py-2 text-sm rounded-lg bg-white dark:bg-slate-900 border border-amber-500/60"
                    />
                  )}
                </div>
              )}

              <div className="flex justify-end gap-2">
                {loginToken && (
                  <button
                    type="button"
                    onClick={() => {
                      setLoginToken(null)
                      setCode('')
                      setNeed2fa(false)
                    }}
                    className="px-4 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700"
                  >
                    重填手机号
                  </button>
                )}
                <button
                  type="submit"
                  disabled={submitting || !proxyId}
                  className="px-4 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50"
                >
                  {submitting
                    ? '处理中...'
                    : loginToken
                      ? '提交登录'
                      : '发送验证码'}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}

