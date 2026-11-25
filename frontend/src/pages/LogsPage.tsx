import { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { api } from '../api/client'
import { StatusBadge } from '../components/StatusBadge'
import type { TaskLog } from '../types/api'

/**
 * 风控审计日志页：支持按账号 ID 与结果类型筛选，高亮展示风控熔断事件。
 */
export function LogsPage() {
  const [logs, setLogs] = useState<TaskLog[]>([])
  const [accountIdFilter, setAccountIdFilter] = useState('')
  const [resultFilter, setResultFilter] = useState('')
  const [loading, setLoading] = useState(true)

  const loadLogs = async () => {
    setLoading(true)
    try {
      const data = await api.getLogs({
        account_id: accountIdFilter ? Number(accountIdFilter) : undefined,
        result: resultFilter || undefined,
        limit: 150,
      })
      setLogs(data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadLogs()
  }, [resultFilter])

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">风控与任务审计日志</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            全量追踪每次协议操作、代理探活与 FloodWait / PeerFlood 熔断事件
          </p>
        </div>
        <button
          onClick={loadLogs}
          className="inline-flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          刷新
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <input
          type="number"
          value={accountIdFilter}
          onChange={(e) => setAccountIdFilter(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') loadLogs()
          }}
          placeholder="按账号 ID 筛选（回车查询）"
          className="w-56 px-3 py-2 text-sm rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800"
        />
        <select
          value={resultFilter}
          onChange={(e) => setResultFilter(e.target.value)}
          className="px-3 py-2 text-sm rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800"
        >
          <option value="">全部结果</option>
          <option value="success">成功 (success)</option>
          <option value="flood_wait">FloodWait (flood_wait)</option>
          <option value="peer_flood">PeerFlood (peer_flood)</option>
          <option value="proxy_dead">代理失效 (proxy_dead)</option>
          <option value="auth_invalid">授权失效 (auth_invalid)</option>
          <option value="skipped">已跳过 (skipped)</option>
          <option value="error">异常 (error)</option>
        </select>
      </div>

      <div className="rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead className="bg-slate-50 dark:bg-slate-800/60 text-xs uppercase text-slate-500 dark:text-slate-400">
            <tr>
              <th className="px-4 py-3">时间</th>
              <th className="px-4 py-3">账号 ID</th>
              <th className="px-4 py-3">动作</th>
              <th className="px-4 py-3">结果</th>
              <th className="px-4 py-3">目标</th>
              <th className="px-4 py-3">等待秒数</th>
              <th className="px-4 py-3">详情</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
            {logs.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-slate-500">
                  暂无符合条件的审计日志
                </td>
              </tr>
            ) : (
              logs.map((log) => (
                <tr key={log.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                  <td className="px-4 py-3 text-xs font-mono text-slate-500 whitespace-nowrap">
                    {new Date(log.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">#{log.account_id}</td>
                  <td className="px-4 py-3 text-xs font-medium">{log.action}</td>
                  <td className="px-4 py-3">
                    <StatusBadge value={log.result} />
                  </td>
                  <td className="px-4 py-3 text-xs font-mono">{log.target_ref || '-'}</td>
                  <td className="px-4 py-3 text-xs font-mono">
                    {log.wait_seconds > 0 ? `${log.wait_seconds}s` : '-'}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500 dark:text-slate-400 max-w-md truncate">
                    {log.error_detail || '-'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

