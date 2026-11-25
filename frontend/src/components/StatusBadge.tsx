interface StatusBadgeProps {
  value: string
}

const BADGE_STYLES: Record<string, string> = {
  active: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30',
  success: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30',
  cooldown: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30',
  flood_wait: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30',
  slow: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30',
  restricted: 'bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/30',
  peer_flood: 'bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/30',
  dead: 'bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/30',
  proxy_dead: 'bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/30',
  auth_invalid: 'bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/30',
  invalid: 'bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/30',
  banned: 'bg-red-600/20 text-red-600 dark:text-red-400 border-red-600/40',
  frozen: 'bg-sky-500/15 text-sky-600 dark:text-sky-400 border-sky-500/30',
  skipped: 'bg-slate-500/15 text-slate-600 dark:text-slate-400 border-slate-500/30',
  pending: 'bg-slate-500/15 text-slate-600 dark:text-slate-400 border-slate-500/30',
  running: 'bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 border-indigo-500/30',
  sent: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30',
  failed: 'bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/30',
  cancelled: 'bg-slate-500/15 text-slate-500 dark:text-slate-400 border-slate-500/30',
  error: 'bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/30',
}

const LABELS: Record<string, string> = {
  active: '正常',
  cooldown: '冷却中',
  restricted: '已受限',
  frozen: '已冻结',
  invalid: '已失效',
  banned: '已封禁',
  pending: '待验证',
  dead: '不可达',
  slow: '高延迟',
  success: '成功',
  flood_wait: 'FloodWait',
  peer_flood: 'PeerFlood',
  proxy_dead: '代理失效',
  auth_invalid: '授权失效',
  skipped: '已跳过',
  running: '发布中',
  sent: '已发送',
  failed: '发送失败',
  cancelled: '已取消',
  error: '异常',
}

/**
 * 统一的状态标签组件（支持账号状态、代理状态与风控日志高亮）。
 */
export function StatusBadge({ value }: StatusBadgeProps) {
  const style =
    BADGE_STYLES[value] ??
    'bg-slate-500/15 text-slate-600 dark:text-slate-400 border-slate-500/30'
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full border ${style}`}
    >
      {LABELS[value] ?? value}
    </span>
  )
}

