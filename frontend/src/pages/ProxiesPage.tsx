import { FormEvent, useEffect, useState } from 'react'
import { Activity, Plus, RefreshCw, Trash2, Upload } from 'lucide-react'
import { api } from '../api/client'
import { StatusBadge } from '../components/StatusBadge'
import type { ProxyItem } from '../types/api'

/**
 * 代理池管理页：支持新增、批量导入、一键测速探活与删除。
 */
export function ProxiesPage() {
  const [proxies, setProxies] = useState<ProxyItem[]>([])
  const [loading, setLoading] = useState(true)
  const [checkingId, setCheckingId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [showAddModal, setShowAddModal] = useState(false)
  const [showBatchModal, setShowBatchModal] = useState(false)

  // 单个新增表单状态
  const [name, setName] = useState('')
  const [protocol, setProtocol] = useState<'socks5' | 'http'>('socks5')
  const [host, setHost] = useState('')
  const [port, setPort] = useState('1080')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [countryCode, setCountryCode] = useState('US')
  const [maxAccounts, setMaxAccounts] = useState('2')

  // 批量导入文本状态
  const [batchText, setBatchText] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const loadProxies = async () => {
    setLoading(true)
    try {
      const data = await api.getProxies()
      setProxies(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载代理列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadProxies()
  }, [])

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await api.createProxy({
        name: name.trim(),
        protocol,
        host: host.trim(),
        port: Number(port),
        username: username.trim() || null,
        password: password || null,
        country_code: countryCode.trim() || null,
        max_accounts: Number(maxAccounts),
      })
      setShowAddModal(false)
      setName('')
      setHost('')
      setUsername('')
      setPassword('')
      await loadProxies()
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建代理失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleBatchImport = async (e: FormEvent) => {
    e.preventDefault()
    const lines = batchText
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean)
    if (lines.length === 0) return

    setSubmitting(true)
    setError(null)
    try {
      for (let idx = 0; idx < lines.length; idx++) {
        const line = lines[idx]
        // 支持 socks5://user:pass@host:port 或 host:port:user:pass 或 host:port
        if (line.includes('://')) {
          const url = new URL(line)
          await api.createProxy({
            name: `批量代理-${idx + 1}`,
            protocol: url.protocol.startsWith('http') ? 'http' : 'socks5',
            host: url.hostname,
            port: Number(url.port || 1080),
            username: url.username ? decodeURIComponent(url.username) : null,
            password: url.password ? decodeURIComponent(url.password) : null,
            max_accounts: 2,
          })
        } else {
          const parts = line.split(':')
          if (parts.length < 2) {
            throw new Error(`第 ${idx + 1} 行格式无法解析: ${line}`)
          }
          await api.createProxy({
            name: `批量代理-${idx + 1}`,
            protocol: 'socks5',
            host: parts[0],
            port: Number(parts[1]),
            username: parts[2] || null,
            password: parts[3] || null,
            max_accounts: 2,
          })
        }
      }
      setShowBatchModal(false)
      setBatchText('')
      await loadProxies()
    } catch (err) {
      setError(err instanceof Error ? err.message : '批量导入失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleCheck = async (proxyId: number) => {
    setCheckingId(proxyId)
    try {
      await api.checkProxy(proxyId)
      await loadProxies()
    } catch (err) {
      setError(err instanceof Error ? err.message : '代理测速失败')
    } finally {
      setCheckingId(null)
    }
  }

  const handleDelete = async (proxyId: number) => {
    try {
      await api.deleteProxy(proxyId)
      await loadProxies()
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除代理失败')
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">代理池管理</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            严格绑定单 IP 账号上限（建议 1-3 个），任何操作前强制探活，绝不直连
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadProxies}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
          <button
            onClick={() => setShowBatchModal(true)}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            <Upload className="w-4 h-4" />
            批量导入
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-500"
          >
            <Plus className="w-4 h-4" />
            新增代理
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-600 dark:text-rose-400 text-sm">
          {error}
        </div>
      )}

      <div className="rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead className="bg-slate-50 dark:bg-slate-800/60 text-xs uppercase text-slate-500 dark:text-slate-400">
            <tr>
              <th className="px-4 py-3">名称</th>
              <th className="px-4 py-3">协议与地址</th>
              <th className="px-4 py-3">国家</th>
              <th className="px-4 py-3">绑定容量</th>
              <th className="px-4 py-3">状态</th>
              <th className="px-4 py-3">延迟</th>
              <th className="px-4 py-3 text-right">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
            {proxies.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-slate-500">
                  暂无代理，请先点击右上角「新增代理」或「批量导入」
                </td>
              </tr>
            ) : (
              proxies.map((proxy) => (
                <tr key={proxy.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                  <td className="px-4 py-3 font-medium">
                    #{proxy.id} {proxy.name}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">
                    {proxy.protocol}://{proxy.host}:{proxy.port}
                    {proxy.username ? ` (${proxy.username})` : ''}
                  </td>
                  <td className="px-4 py-3">{proxy.country_code || '-'}</td>
                  <td className="px-4 py-3">
                    <span
                      className={
                        proxy.bound_account_count >= proxy.max_accounts
                          ? 'text-amber-500 font-medium'
                          : ''
                      }
                    >
                      {proxy.bound_account_count} / {proxy.max_accounts}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge value={proxy.status} />
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">
                    {proxy.latency_ms != null ? `${proxy.latency_ms} ms` : '-'}
                  </td>
                  <td className="px-4 py-3 text-right space-x-2">
                    <button
                      onClick={() => handleCheck(proxy.id)}
                      disabled={checkingId === proxy.id}
                      className="inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded-md border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50"
                    >
                      <Activity
                        className={`w-3.5 h-3.5 ${checkingId === proxy.id ? 'animate-pulse text-indigo-500' : ''}`}
                      />
                      {checkingId === proxy.id ? '测速中...' : '探活测速'}
                    </button>
                    <button
                      onClick={() => handleDelete(proxy.id)}
                      className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded-md text-rose-500 hover:bg-rose-500/10"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* 新增代理弹窗 */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <form
            onSubmit={handleCreate}
            className="w-full max-w-md rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-6 space-y-4 shadow-xl"
          >
            <h3 className="text-lg font-semibold">新增代理节点</h3>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="block text-xs text-slate-500 mb-1">节点名称</label>
                <input
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="例如：US-住宅静态-01"
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">协议</label>
                <select
                  value={protocol}
                  onChange={(e) => setProtocol(e.target.value as 'socks5' | 'http')}
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                >
                  <option value="socks5">SOCKS5</option>
                  <option value="http">HTTP</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">国家码</label>
                <input
                  value={countryCode}
                  onChange={(e) => setCountryCode(e.target.value)}
                  placeholder="US"
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">主机 / IP</label>
                <input
                  required
                  value={host}
                  onChange={(e) => setHost(e.target.value)}
                  placeholder="1.2.3.4"
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">端口</label>
                <input
                  required
                  type="number"
                  value={port}
                  onChange={(e) => setPort(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">用户名（可选）</label>
                <input
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">密码（加密存储）</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
              <div className="col-span-2">
                <label className="block text-xs text-slate-500 mb-1">单 IP 最大绑定账号数</label>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={maxAccounts}
                  onChange={(e) => setMaxAccounts(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700"
              >
                取消
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="px-4 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50"
              >
                {submitting ? '提交中...' : '确认添加'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* 批量导入代理弹窗 */}
      {showBatchModal && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <form
            onSubmit={handleBatchImport}
            className="w-full max-w-lg rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-6 space-y-4 shadow-xl"
          >
            <h3 className="text-lg font-semibold">批量导入代理</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              每行一条，支持 `socks5://user:pass@host:port` 或 `host:port:user:pass` 格式
            </p>
            <textarea
              rows={6}
              value={batchText}
              onChange={(e) => setBatchText(e.target.value)}
              placeholder={'socks5://user:pass@1.2.3.4:1080\n5.6.7.8:1080:user:pass'}
              className="w-full px-3 py-2 text-xs font-mono rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowBatchModal(false)}
                className="px-4 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700"
              >
                取消
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="px-4 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50"
              >
                {submitting ? '导入中...' : '开始导入'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}

