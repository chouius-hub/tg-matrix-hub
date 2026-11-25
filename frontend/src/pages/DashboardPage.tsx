import { useEffect, useState } from 'react'
import { Activity, Cpu, HardDrive, Network, RefreshCw, ShieldAlert } from 'lucide-react'
import { api } from '../api/client'
import { StatusBadge } from '../components/StatusBadge'
import type { SystemStats, TaskLog, WsEventMessage } from '../types/api'

interface DashboardPageProps {
  liveEvents: WsEventMessage[]
  wsConnected: boolean
}

/**
 * 总览大盘：展示 100 账号状态分布、本机硬件资源、连接池水位与实时风控动态。
 */
export function DashboardPage({ liveEvents, wsConnected }: DashboardPageProps) {
  const [stats, setStats] = useState<SystemStats | null>(null)
  const [recentLogs, setRecentLogs] = useState<TaskLog[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = async () => {
    try {
      const [statsRes, logsRes] = await Promise.all([
        api.getSystemStats(),
        api.getLogs({ limit: 15 }),
      ])
      setStats(statsRes)
      setRecentLogs(logsRes)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载大盘数据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    const timer = window.setInterval(fetchData, 5000)
    return () => window.clearInterval(timer)
  }, [])

  const counts = stats?.status_counts ?? {}
  const invalidTotal = (counts.invalid ?? 0) + (counts.banned ?? 0)

  const cards = [
    { label: '账号总数', value: stats?.total_accounts ?? 0, accent: 'text-slate-900 dark:text-white' },
    { label: '正常可调度', value: counts.active ?? 0, accent: 'text-emerald-600 dark:text-emerald-400' },
    { label: '冷却中', value: counts.cooldown ?? 0, accent: 'text-amber-600 dark:text-amber-400' },
    { label: '已受限', value: counts.restricted ?? 0, accent: 'text-rose-600 dark:text-rose-400' },
    { label: '已冻结', value: counts.frozen ?? 0, accent: 'text-sky-600 dark:text-sky-400' },
    { label: '失效 / 封禁', value: invalidTotal, accent: 'text-red-600 dark:text-red-400' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">系统总览大盘</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            实时监控账号池健康状态、资源水位与风控熔断动态
          </p>
        </div>
        <button
          onClick={fetchData}
          className="inline-flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800"
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

      {/* 账号状态分布卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {cards.map((card) => (
          <div
            key={card.label}
            className="p-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm"
          >
            <div className="text-xs text-slate-500 dark:text-slate-400">{card.label}</div>
            <div className={`mt-2 text-2xl font-bold ${card.accent}`}>{card.value}</div>
          </div>
        ))}
      </div>

      {/* 系统资源与连接池状态 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="p-5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 space-y-3">
          <div className="flex items-center justify-between text-sm font-medium">
            <span className="inline-flex items-center gap-2">
              <Cpu className="w-4 h-4 text-indigo-500" />
              CPU 使用率
            </span>
            <span>{stats?.cpu_percent ?? 0}%</span>
          </div>
          <div className="h-2.5 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
            <div
              className="h-full bg-indigo-500 transition-all duration-300"
              style={{ width: `${Math.min(100, stats?.cpu_percent ?? 0)}%` }}
            />
          </div>
        </div>

        <div className="p-5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 space-y-3">
          <div className="flex items-center justify-between text-sm font-medium">
            <span className="inline-flex items-center gap-2">
              <HardDrive className="w-4 h-4 text-emerald-500" />
              内存占用
            </span>
            <span>
              {stats?.memory_percent ?? 0}% ({Math.round(stats?.memory_used_mb ?? 0)} /{' '}
              {Math.round(stats?.memory_total_mb ?? 0)} MB)
            </span>
          </div>
          <div className="h-2.5 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
            <div
              className="h-full bg-emerald-500 transition-all duration-300"
              style={{ width: `${Math.min(100, stats?.memory_percent ?? 0)}%` }}
            />
          </div>
        </div>

        <div className="p-5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <div className="space-y-1">
            <div className="inline-flex items-center gap-2 text-sm font-medium">
              <Network className="w-4 h-4 text-sky-500" />
              活跃 Telegram 连接池
            </div>
            <div className="text-xs text-slate-500 dark:text-slate-400">
              常驻监听: {stats?.pool_pinned_count ?? 0} · LRU 任务池: {stats?.pool_lru_count ?? 0}/20
            </div>
          </div>
          <div className="text-2xl font-bold text-sky-500">{stats?.pool_total_active ?? 0}</div>
        </div>
      </div>

      {/* 实时动态流与最近日志 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-medium inline-flex items-center gap-2">
              <Activity className="w-4 h-4 text-indigo-500" />
              WebSocket 实时风控流
            </h3>
            <span
              className={`text-xs px-2 py-0.5 rounded-full ${
                wsConnected
                  ? 'bg-emerald-500/15 text-emerald-500'
                  : 'bg-slate-500/15 text-slate-400'
              }`}
            >
              {wsConnected ? '已连接' : '重连中'}
            </span>
          </div>
          {liveEvents.length === 0 ? (
            <div className="text-sm text-slate-500 dark:text-slate-400 py-8 text-center">
              暂无实时推送事件，执行任务或触发风控后将在此处实时滚动显示
            </div>
          ) : (
            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {liveEvents.map((ev, idx) => (
                <div
                  key={`${ev.timestamp}-${idx}`}
                  className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-200/70 dark:border-slate-700/60 text-xs flex items-start justify-between gap-3"
                >
                  <div className="space-y-0.5">
                    <div className="font-medium">
                      [{ev.type}] 账号 #{String(ev.data.account_id ?? '-')} ·{' '}
                      {String(ev.data.action ?? ev.data.event ?? '')}
                    </div>
                    {Boolean(ev.data.error_detail || ev.data.message) && (
                      <div className="text-slate-500 dark:text-slate-400">
                        {String(ev.data.error_detail ?? ev.data.message)}
                      </div>
                    )}
                  </div>
                  <div className="shrink-0 flex flex-col items-end gap-1">
                    {typeof ev.data.result === 'string' && <StatusBadge value={ev.data.result} />}
                    <span className="text-[11px] text-slate-400">
                      {new Date(ev.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-medium inline-flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-amber-500" />
              最近审计记录
            </h3>
          </div>
          {recentLogs.length === 0 ? (
            <div className="text-sm text-slate-500 dark:text-slate-400 py-8 text-center">
              暂无历史审计日志
            </div>
          ) : (
            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {recentLogs.map((log) => (
                <div
                  key={log.id}
                  className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-200/70 dark:border-slate-700/60 text-xs flex items-center justify-between gap-2"
                >
                  <div className="min-w-0">
                    <div className="font-medium truncate">
                      账号 #{log.account_id} · {log.action}
                      {log.target_ref ? ` → ${log.target_ref}` : ''}
                    </div>
                    {log.error_detail && (
                      <div className="text-slate-500 dark:text-slate-400 truncate">
                        {log.error_detail}
                      </div>
                    )}
                  </div>
                  <div className="shrink-0 flex items-center gap-2">
                    <StatusBadge value={log.result} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

