import { FormEvent, useEffect, useState } from 'react'
import { Bell, CheckCircle2, ExternalLink, Plus, Power, RefreshCw, Trash2 } from 'lucide-react'
import { api } from '../api/client'
import type { Account, KeywordAlert, KeywordRule } from '../types/api'

interface KeywordMonitorPageProps {
  onAlertsChanged?: () => void
}

/**
 * 关键词实时监控与告警页：管理监控规则，查看命中告警信息流并一键标为已读。
 */
export function KeywordMonitorPage({ onAlertsChanged }: KeywordMonitorPageProps) {
  const [rules, setRules] = useState<KeywordRule[]>([])
  const [alerts, setAlerts] = useState<KeywordAlert[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [name, setName] = useState('')
  const [listenerId, setListenerId] = useState('')
  const [chatsText, setChatsText] = useState('')
  const [keywordsText, setKeywordsText] = useState('')
  const [excludeText, setExcludeText] = useState('')
  const [matchMode, setMatchMode] = useState<'contains' | 'regex'>('contains')
  const [webhookUrl, setWebhookUrl] = useState('')
  const [alertChatId, setAlertChatId] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const loadData = async () => {
    setLoading(true)
    try {
      const [rulesData, alertsData, accData] = await Promise.all([
        api.getKeywordRules(),
        api.getKeywordAlerts(),
        api.getAccounts(),
      ])
      setRules(rulesData)
      setAlerts(alertsData)
      setAccounts(accData)
      if (!listenerId && accData[0]) setListenerId(String(accData[0].id))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载关键词监控数据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const handleCreateRule = async (e: FormEvent) => {
    e.preventDefault()
    if (!listenerId) {
      setError('请先在账号管理中导入至少一个可用账号')
      return
    }
    const monitoredChats = chatsText
      .split(/[\n,]/)
      .map((s) => s.trim())
      .filter(Boolean)
    const keywords = keywordsText
      .split(/[\n,]/)
      .map((s) => s.trim())
      .filter(Boolean)
    if (monitoredChats.length === 0 || keywords.length === 0) {
      setError('请填写至少一个监控群组和关键词')
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      await api.createKeywordRule({
        name: name.trim(),
        listener_account_id: Number(listenerId),
        monitored_chat_ids: monitoredChats,
        keywords,
        match_mode: matchMode,
        exclude_keywords: excludeText
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        alert_webhook_url: webhookUrl.trim() || null,
        alert_target_chat_id: alertChatId.trim() || null,
        is_enabled: true,
      })
      setShowModal(false)
      setName('')
      setChatsText('')
      setKeywordsText('')
      setExcludeText('')
      setWebhookUrl('')
      setAlertChatId('')
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建监控规则失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleToggleRule = async (rule: KeywordRule) => {
    try {
      await api.updateKeywordRule(rule.id, { is_enabled: !rule.is_enabled })
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : '切换规则状态失败')
    }
  }

  const handleDeleteRule = async (id: number) => {
    try {
      await api.deleteKeywordRule(id)
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除规则失败')
    }
  }

  const handleMarkRead = async (alertId: number) => {
    try {
      await api.markKeywordAlertRead(alertId)
      await loadData()
      onAlertsChanged?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : '标记已读失败')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">关键词实时监控与告警</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            实时监听指定群组/频道消息，命中关键词后立即触发前端红点、Webhook 与内部群告警
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadData}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
          <button
            onClick={() => setShowModal(true)}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-500"
          >
            <Plus className="w-4 h-4" />
            新建监控规则
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-600 dark:text-rose-400 text-sm">
          {error}
        </div>
      )}

      {/* 规则列表 */}
      <div className="rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 overflow-x-auto">
        <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 font-medium text-sm">
          监控规则列表
        </div>
        <table className="w-full text-sm text-left">
          <thead className="bg-slate-50 dark:bg-slate-800/60 text-xs uppercase text-slate-500 dark:text-slate-400">
            <tr>
              <th className="px-4 py-3">规则名称</th>
              <th className="px-4 py-3">监听账号</th>
              <th className="px-4 py-3">监控群组</th>
              <th className="px-4 py-3">关键词 ({rules.length})</th>
              <th className="px-4 py-3">模式</th>
              <th className="px-4 py-3">状态</th>
              <th className="px-4 py-3 text-right">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
            {rules.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-slate-500">
                  暂无关键词监控规则
                </td>
              </tr>
            ) : (
              rules.map((rule) => (
                <tr key={rule.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                  <td className="px-4 py-3 font-medium">{rule.name}</td>
                  <td className="px-4 py-3 font-mono text-xs">#{rule.listener_account_id}</td>
                  <td className="px-4 py-3 text-xs font-mono">
                    {rule.monitored_chat_ids.join(', ')}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {rule.keywords.join(', ')}
                    {rule.exclude_keywords.length > 0 && (
                      <span className="ml-2 text-slate-400">
                        (排除: {rule.exclude_keywords.join(', ')})
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs font-mono">{rule.match_mode}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-0.5 text-xs rounded-full border ${
                        rule.is_enabled
                          ? 'bg-emerald-500/15 text-emerald-500 border-emerald-500/30'
                          : 'bg-slate-500/15 text-slate-400 border-slate-500/30'
                      }`}
                    >
                      {rule.is_enabled ? '监控中' : '已停用'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right space-x-2">
                    <button
                      onClick={() => handleToggleRule(rule)}
                      className="inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded-md border border-slate-200 dark:border-slate-700"
                    >
                      <Power className="w-3.5 h-3.5" />
                      {rule.is_enabled ? '停用' : '启用'}
                    </button>
                    <button
                      onClick={() => handleDeleteRule(rule.id)}
                      className="p-1.5 rounded-md text-rose-500 hover:bg-rose-500/10"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* 告警信息流 */}
      <div className="rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-medium inline-flex items-center gap-2">
            <Bell className="w-4 h-4 text-rose-500" />
            实时告警信息流
          </h3>
          <span className="text-xs text-slate-500">
            未读: {alerts.filter((a) => !a.is_read).length} / 总计: {alerts.length}
          </span>
        </div>

        {alerts.length === 0 ? (
          <div className="py-10 text-center text-sm text-slate-500">暂无命中告警记录</div>
        ) : (
          <div className="space-y-2.5">
            {alerts.map((alert) => (
              <div
                key={alert.id}
                className={`p-4 rounded-xl border transition-colors ${
                  alert.is_read
                    ? 'bg-slate-50/50 dark:bg-slate-800/30 border-slate-200 dark:border-slate-800'
                    : 'bg-rose-500/5 border-rose-500/30'
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
                  <div className="flex items-center gap-2 text-xs">
                    {!alert.is_read && (
                      <span className="w-2 h-2 rounded-full bg-rose-500" />
                    )}
                    <span className="px-2 py-0.5 rounded bg-rose-500/15 text-rose-500 font-medium">
                      命中: {alert.matched_keyword}
                    </span>
                    <span className="font-medium">
                      {alert.source_chat_title || alert.source_chat_id}
                    </span>
                    {alert.sender_username && (
                      <span className="text-slate-500">@{alert.sender_username}</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 text-xs text-slate-400">
                    <span>{new Date(alert.created_at).toLocaleString()}</span>
                    {alert.message_link && (
                      <a
                        href={alert.message_link}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-indigo-500 hover:underline"
                      >
                        原消息 <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                    {!alert.is_read && (
                      <button
                        onClick={() => handleMarkRead(alert.id)}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                      >
                        <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                        标为已读
                      </button>
                    )}
                  </div>
                </div>
                <p className="text-sm text-slate-700 dark:text-slate-200 whitespace-pre-wrap">
                  {alert.message_text}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 新建监控规则弹窗 */}
      {showModal && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4 overflow-y-auto">
          <form
            onSubmit={handleCreateRule}
            className="w-full max-w-xl rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-6 space-y-4 shadow-xl"
          >
            <h3 className="text-lg font-semibold">新建关键词监控规则</h3>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="block text-xs text-slate-500 mb-1">规则名称</label>
                <input
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="例如：竞品动态与空投线报监控"
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">监听账号</label>
                <select
                  value={listenerId}
                  onChange={(e) => setListenerId(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                >
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      #{a.id} {a.phone} ({a.account_role})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">匹配模式</label>
                <select
                  value={matchMode}
                  onChange={(e) => setMatchMode(e.target.value as 'contains' | 'regex')}
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                >
                  <option value="contains">包含匹配 (contains)</option>
                  <option value="regex">正则匹配 (regex)</option>
                </select>
              </div>
              <div className="col-span-2">
                <label className="block text-xs text-slate-500 mb-1">
                  监控群组/频道（多个用逗号或换行分隔）
                </label>
                <input
                  required
                  value={chatsText}
                  onChange={(e) => setChatsText(e.target.value)}
                  placeholder="@group_a, @channel_b"
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
              <div className="col-span-2">
                <label className="block text-xs text-slate-500 mb-1">
                  监控关键词（多个用逗号分隔）
                </label>
                <input
                  required
                  value={keywordsText}
                  onChange={(e) => setKeywordsText(e.target.value)}
                  placeholder="免费API, 空投, airdrop"
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
              <div className="col-span-2">
                <label className="block text-xs text-slate-500 mb-1">
                  排除词（命中则忽略，逗号分隔，可选）
                </label>
                <input
                  value={excludeText}
                  onChange={(e) => setExcludeText(e.target.value)}
                  placeholder="假消息, 钓鱼"
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">外部 Webhook URL（可选）</label>
                <input
                  value={webhookUrl}
                  onChange={(e) => setWebhookUrl(e.target.value)}
                  placeholder="https://open.feishu.cn/..."
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">内部转发告警群 ID（可选）</label>
                <input
                  value={alertChatId}
                  onChange={(e) => setAlertChatId(e.target.value)}
                  placeholder="@my_alert_group"
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="px-4 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700"
              >
                取消
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="px-4 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50"
              >
                {submitting ? '保存并加载中...' : '保存并启用'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}

