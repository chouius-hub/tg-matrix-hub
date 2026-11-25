import { useEffect, useMemo, useState } from 'react'
import {
  HeartPulse,
  PauseCircle,
  PlayCircle,
  Plus,
  RefreshCw,
  Search,
  Trash2,
} from 'lucide-react'
import { api } from '../api/client'
import { ImportAccountModal } from '../components/ImportAccountModal'
import { StatusBadge } from '../components/StatusBadge'
import type { Account, ProxyItem } from '../types/api'

function formatCooldownRemaining(cooldownUntil: string | null): string | null {
  if (!cooldownUntil) return null
  const diffMs = new Date(cooldownUntil).getTime() - Date.now()
  if (diffMs <= 0) return null
  const totalSec = Math.ceil(diffMs / 1000)
  const mins = Math.floor(totalSec / 60)
  const secs = totalSec % 60
  return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`
}

/**
 * 账号管理页：支持筛选、批量 @SpamBot 体检、冻结/解冻、配额管理与三合一导入。
 */
export function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [proxies, setProxies] = useState<ProxyItem[]>([])
  const [statusFilter, setStatusFilter] = useState('')
  const [searchText, setSearchText] = useState('')
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [loading, setLoading] = useState(true)
  const [checkingIds, setCheckingIds] = useState<Set<number>>(new Set())
  const [showImportModal, setShowImportModal] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadData = async () => {
    setLoading(true)
    try {
      const [accData, proxyData] = await Promise.all([
        api.getAccounts({
          status: statusFilter || undefined,
          search: searchText.trim() || undefined,
        }),
        api.getProxies(),
      ])
      setAccounts(accData)
      setProxies(proxyData)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载账号数据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [statusFilter])

  const proxyMap = useMemo(() => {
    const map = new Map<number, ProxyItem>()
    for (const p of proxies) map.set(p.id, p)
    return map
  }, [proxies])

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id],
    )
  }

  const toggleSelectAll = () => {
    if (selectedIds.length === accounts.length) {
      setSelectedIds([])
    } else {
      setSelectedIds(accounts.map((a) => a.id))
    }
  }

  const handleHealthCheck = async (accountId: number) => {
    setCheckingIds((prev) => new Set(prev).add(accountId))
    try {
      await api.healthCheckAccount(accountId)
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : '体检失败')
    } finally {
      setCheckingIds((prev) => {
        const next = new Set(prev)
        next.delete(accountId)
        return next
      })
    }
  }

  const handleBatchHealthCheck = async () => {
    if (selectedIds.length === 0) return
    setCheckingIds(new Set(selectedIds))
    try {
      await api.batchHealthCheck(selectedIds)
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : '批量体检失败')
    } finally {
      setCheckingIds(new Set())
    }
  }

  const handleToggleFreeze = async (account: Account) => {
    const targetStatus = account.status === 'frozen' ? 'active' : 'frozen'
    try {
      await api.updateAccount(account.id, { status: targetStatus })
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : '修改账号状态失败')
    }
  }

  const handleDelete = async (accountId: number) => {
    try {
      await api.deleteAccount(accountId)
      setSelectedIds((prev) => prev.filter((id) => id !== accountId))
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除账号失败')
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">账号资产管理</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            统一管理设备指纹、绑定代理、健康分与每日安全配额
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleBatchHealthCheck}
            disabled={selectedIds.length === 0 || checkingIds.size > 0}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50"
          >
            <HeartPulse className="w-4 h-4 text-rose-500" />
            批量体检 ({selectedIds.length})
          </button>
          <button
            onClick={() => setShowImportModal(true)}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-500"
          >
            <Plus className="w-4 h-4" />
            导入账号
          </button>
        </div>
      </div>

      {/* 搜索与筛选栏 */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[220px] max-w-sm">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') loadData()
            }}
            placeholder="搜索手机号 / @username（回车查询）"
            className="w-full pl-9 pr-3 py-2 text-sm rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-2 text-sm rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800"
        >
          <option value="">全部状态</option>
          <option value="active">正常 (active)</option>
          <option value="cooldown">冷却中 (cooldown)</option>
          <option value="restricted">已受限 (restricted)</option>
          <option value="frozen">已冻结 (frozen)</option>
          <option value="invalid">已失效 (invalid)</option>
          <option value="banned">已封禁 (banned)</option>
        </select>
        <button
          onClick={loadData}
          className="inline-flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          刷新
        </button>
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-600 dark:text-rose-400 text-sm">
          {error}
        </div>
      )}

      {/* 账号表格 */}
      <div className="rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead className="bg-slate-50 dark:bg-slate-800/60 text-xs uppercase text-slate-500 dark:text-slate-400">
            <tr>
              <th className="px-4 py-3 w-10">
                <input
                  type="checkbox"
                  checked={accounts.length > 0 && selectedIds.length === accounts.length}
                  onChange={toggleSelectAll}
                />
              </th>
              <th className="px-4 py-3">账号信息</th>
              <th className="px-4 py-3">角色 / 国家</th>
              <th className="px-4 py-3">绑定代理</th>
              <th className="px-4 py-3">固化指纹</th>
              <th className="px-4 py-3">健康分</th>
              <th className="px-4 py-3">状态 / 冷却</th>
              <th className="px-4 py-3">今日配额</th>
              <th className="px-4 py-3 text-right">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
            {accounts.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-4 py-12 text-center text-slate-500">
                  暂无账号数据，点击右上角「导入账号」通过 tdata / .session / 手机号安全接入
                </td>
              </tr>
            ) : (
              accounts.map((acc) => {
                const proxy = proxyMap.get(acc.proxy_id)
                const remaining = formatCooldownRemaining(acc.cooldown_until)
                const isChecking = checkingIds.has(acc.id)

                return (
                  <tr key={acc.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(acc.id)}
                        onChange={() => toggleSelect(acc.id)}
                      />
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-medium font-mono text-xs">{acc.phone}</div>
                      <div className="text-xs text-slate-500">
                        {acc.username ? `@${acc.username}` : acc.first_name || `ID #${acc.id}`}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-xs">
                      <span className="px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800">
                        {acc.account_role}
                      </span>{' '}
                      <span className="text-slate-500">{acc.country_code || '-'}</span>
                    </td>
                    <td className="px-4 py-3 text-xs">
                      {proxy ? `${proxy.name} (${proxy.host})` : `代理 #${acc.proxy_id}`}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500 dark:text-slate-400">
                      {acc.device_profile
                        ? `${acc.device_profile.platform} · ${acc.device_profile.device_model}`
                        : '-'}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-14 h-1.5 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
                          <div
                            className={`h-full ${
                              acc.health_score >= 80
                                ? 'bg-emerald-500'
                                : acc.health_score >= 50
                                  ? 'bg-amber-500'
                                  : 'bg-rose-500'
                            }`}
                            style={{ width: `${acc.health_score}%` }}
                          />
                        </div>
                        <span className="text-xs font-mono">{acc.health_score}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col gap-1">
                        <StatusBadge value={acc.status} />
                        {remaining && (
                          <span className="text-[11px] font-mono text-amber-500">
                            剩余 {remaining}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">
                      {acc.daily_action_count} / {acc.daily_action_limit}
                    </td>
                    <td className="px-4 py-3 text-right space-x-1">
                      <button
                        title="@SpamBot 体检"
                        disabled={isChecking}
                        onClick={() => handleHealthCheck(acc.id)}
                        className="p-1.5 rounded-md hover:bg-slate-100 dark:hover:bg-slate-800 text-indigo-500 disabled:opacity-40"
                      >
                        <HeartPulse className={`w-4 h-4 ${isChecking ? 'animate-pulse' : ''}`} />
                      </button>
                      {(acc.status === 'active' || acc.status === 'frozen') && (
                        <button
                          title={acc.status === 'frozen' ? '解冻账号' : '冻结账号'}
                          onClick={() => handleToggleFreeze(acc)}
                          className="p-1.5 rounded-md hover:bg-slate-100 dark:hover:bg-slate-800 text-sky-500"
                        >
                          {acc.status === 'frozen' ? (
                            <PlayCircle className="w-4 h-4" />
                          ) : (
                            <PauseCircle className="w-4 h-4" />
                          )}
                        </button>
                      )}
                      <button
                        title="删除账号"
                        onClick={() => handleDelete(acc.id)}
                        className="p-1.5 rounded-md hover:bg-rose-500/10 text-rose-500"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {showImportModal && (
        <ImportAccountModal
          proxies={proxies}
          onClose={() => setShowImportModal(false)}
          onSuccess={loadData}
        />
      )}
    </div>
  )
}

