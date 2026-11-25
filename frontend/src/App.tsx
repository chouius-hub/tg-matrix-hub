import { useEffect, useState } from 'react'
import {
  Bell,
  CalendarClock,
  Globe,
  LayoutDashboard,
  Moon,
  Radio,
  ScrollText,
  ShieldCheck,
  Sun,
  Users,
} from 'lucide-react'
import { api } from './api/client'
import { useWebSocketEvents } from './hooks/useWebSocketEvents'
import { AccountsPage } from './pages/AccountsPage'
import { ChannelSyncPage } from './pages/ChannelSyncPage'
import { DashboardPage } from './pages/DashboardPage'
import { KeywordMonitorPage } from './pages/KeywordMonitorPage'
import { LogsPage } from './pages/LogsPage'
import { ProxiesPage } from './pages/ProxiesPage'
import { ScheduledPostsPage } from './pages/ScheduledPostsPage'

type NavKey =
  | 'dashboard'
  | 'accounts'
  | 'proxies'
  | 'sync'
  | 'posts'
  | 'keywords'
  | 'logs'

const NAV_ITEMS: Array<{ key: NavKey; label: string; icon: typeof LayoutDashboard }> = [
  { key: 'dashboard', label: '总览大盘', icon: LayoutDashboard },
  { key: 'accounts', label: '账号管理', icon: Users },
  { key: 'proxies', label: '代理池', icon: Globe },
  { key: 'sync', label: '频道转发', icon: Radio },
  { key: 'posts', label: '定时发帖', icon: CalendarClock },
  { key: 'keywords', label: '关键词监控', icon: Bell },
  { key: 'logs', label: '风控审计日志', icon: ScrollText },
]

export function App() {
  const [activeNav, setActiveNav] = useState<NavKey>('dashboard')
  const [darkMode, setDarkMode] = useState(true)
  const [dbUnreadCount, setDbUnreadCount] = useState(0)
  const { connected, events, unreadAlerts, clearUnreadAlerts } = useWebSocketEvents()

  const refreshUnreadCount = () => {
    api
      .getKeywordAlerts(false)
      .then((list) => setDbUnreadCount(list.length))
      .catch(() => {})
  }

  useEffect(() => {
    refreshUnreadCount()
  }, [])

  const totalUnreadBadge = dbUnreadCount + unreadAlerts

  useEffect(() => {
    const root = document.documentElement
    if (darkMode) {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
    }
  }, [darkMode])

  return (
    <div className="min-h-screen flex bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100">
      {/* 左侧导航栏 */}
      <aside className="w-60 shrink-0 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col">
        <div className="h-14 px-5 flex items-center gap-2.5 border-b border-slate-200 dark:border-slate-800">
          <ShieldCheck className="w-6 h-6 text-indigo-500" />
          <span className="font-bold tracking-tight">TG Matrix Hub</span>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon
            const isActive = activeNav === item.key
            return (
              <button
                key={item.key}
                onClick={() => {
                  setActiveNav(item.key)
                  if (item.key === 'keywords' || item.key === 'logs') {
                    clearUnreadAlerts()
                  }
                }}
                className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
                }`}
              >
                <span className="inline-flex items-center gap-2.5">
                  <Icon className="w-4 h-4" />
                  {item.label}
                </span>
                {item.key === 'keywords' && totalUnreadBadge > 0 && (
                  <span className="px-1.5 py-0.5 text-[10px] rounded-full bg-rose-500 text-white">
                    {totalUnreadBadge}
                  </span>
                )}
              </button>
            )
          })}
        </nav>

        <div className="p-4 border-t border-slate-200 dark:border-slate-800 flex items-center justify-between text-xs text-slate-500">
          <span className="inline-flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full ${
                connected ? 'bg-emerald-500' : 'bg-slate-400'
              }`}
            />
            {connected ? '实时流在线' : '实时流重连中'}
          </span>
          <button
            onClick={() => setDarkMode((prev) => !prev)}
            title="切换深/浅色模式"
            className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-300"
          >
            {darkMode ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>
        </div>
      </aside>

      {/* 主内容区域 */}
      <main className="flex-1 min-w-0 p-6 lg:p-8 overflow-y-auto">
        <div className="max-w-7xl mx-auto">
          {activeNav === 'dashboard' && (
            <DashboardPage liveEvents={events} wsConnected={connected} />
          )}
          {activeNav === 'accounts' && <AccountsPage />}
          {activeNav === 'proxies' && <ProxiesPage />}
          {activeNav === 'sync' && <ChannelSyncPage />}
          {activeNav === 'posts' && <ScheduledPostsPage />}
          {activeNav === 'keywords' && (
            <KeywordMonitorPage onAlertsChanged={refreshUnreadCount} />
          )}
          {activeNav === 'logs' && <LogsPage />}
        </div>
      </main>
    </div>
  )
}

export default App

