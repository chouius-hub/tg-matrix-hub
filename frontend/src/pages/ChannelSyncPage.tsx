import { FormEvent, useEffect, useState } from 'react'
import { Plus, Power, RefreshCw, Trash2 } from 'lucide-react'
import { api } from '../api/client'
import type { Account, ChannelSyncRule, RegexReplacementItem } from '../types/api'

/**
 * 多频道 AI 翻译转发配置页。
 */
export function ChannelSyncPage() {
  const [rules, setRules] = useState<ChannelSyncRule[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [name, setName] = useState('')
  const [listenerId, setListenerId] = useState('')
  const [publisherId, setPublisherId] = useState('')
  const [sourceChat, setSourceChat] = useState('')
  const [targetChat, setTargetChat] = useState('')
  const [enableAi, setEnableAi] = useState(true)
  const [aiPrompt, setAiPrompt] = useState(
    '将以下内容翻译为流畅、口语化的中文，保留核心信息与排版，去除原频道广告和推广链接。',
  )
  const [blockedText, setBlockedText] = useState('')
  const [regexItems, setRegexItems] = useState<RegexReplacementItem[]>([])
  const [appendFooter, setAppendFooter] = useState('')
  const [minDelay, setMinDelay] = useState('15')
  const [maxDelay, setMaxDelay] = useState('60')
  const [submitting, setSubmitting] = useState(false)

  const loadData = async () => {
    setLoading(true)
    try {
      const [rulesData, accData] = await Promise.all([
        api.getSyncRules(),
        api.getAccounts(),
      ])
      setRules(rulesData)
      setAccounts(accData)
      if (!listenerId && accData[0]) setListenerId(String(accData[0].id))
      if (!publisherId && accData[0]) setPublisherId(String(accData[0].id))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载转发规则失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault()
    if (!listenerId || !publisherId) {
      setError('请先在账号管理中导入至少一个可用账号')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await api.createSyncRule({
        name: name.trim(),
        listener_account_id: Number(listenerId),
        publisher_account_id: Number(publisherId),
        source_chat_id: sourceChat.trim(),
        target_chat_id: targetChat.trim(),
        enable_ai_translate: enableAi,
        ai_system_prompt: aiPrompt.trim(),
        regex_replacements: regexItems.filter((i) => i.pattern.trim()),
        blocked_keywords: blockedText
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        append_footer: appendFooter.trim() || null,
        min_delay_sec: Number(minDelay),
        max_delay_sec: Number(maxDelay),
        is_enabled: true,
      })
      setShowModal(false)
      setName('')
      setSourceChat('')
      setTargetChat('')
      setBlockedText('')
      setRegexItems([])
      setAppendFooter('')
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建规则失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleToggle = async (id: number) => {
    try {
      await api.toggleSyncRule(id)
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : '切换状态失败')
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await api.deleteSyncRule(id)
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除规则失败')
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">多频道 AI 翻译转发</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            热加载监听源频道，自动执行屏蔽词过滤、正则清洗、AI 翻译与去来源重发
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
            新建转发规则
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
              <th className="px-4 py-3">规则名称</th>
              <th className="px-4 py-3">源频道 → 目标频道</th>
              <th className="px-4 py-3">监听 / 发布账号</th>
              <th className="px-4 py-3">AI 翻译</th>
              <th className="px-4 py-3">延迟 (秒)</th>
              <th className="px-4 py-3">状态</th>
              <th className="px-4 py-3 text-right">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
            {rules.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-slate-500">
                  暂无转发规则，点击右上角「新建转发规则」即可开始
                </td>
              </tr>
            ) : (
              rules.map((rule) => (
                <tr key={rule.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                  <td className="px-4 py-3 font-medium">{rule.name}</td>
                  <td className="px-4 py-3 font-mono text-xs">
                    {rule.source_chat_id} → {rule.target_chat_id}
                  </td>
                  <td className="px-4 py-3 text-xs font-mono">
                    #{rule.listener_account_id} / #{rule.publisher_account_id}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {rule.enable_ai_translate ? (
                      <span className="text-indigo-500 font-medium">已开启</span>
                    ) : (
                      <span className="text-slate-400">原文</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs font-mono">
                    {rule.min_delay_sec}~{rule.max_delay_sec}s
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-0.5 text-xs rounded-full border ${
                        rule.is_enabled
                          ? 'bg-emerald-500/15 text-emerald-500 border-emerald-500/30'
                          : 'bg-slate-500/15 text-slate-400 border-slate-500/30'
                      }`}
                    >
                      {rule.is_enabled ? '运行中' : '已停用'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right space-x-2">
                    <button
                      onClick={() => handleToggle(rule.id)}
                      className="inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded-md border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800"
                    >
                      <Power className="w-3.5 h-3.5" />
                      {rule.is_enabled ? '停用' : '启用'}
                    </button>
                    <button
                      onClick={() => handleDelete(rule.id)}
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

      {showModal && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4 overflow-y-auto">
          <form
            onSubmit={handleCreate}
            className="w-full max-w-2xl rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-6 space-y-4 shadow-xl"
          >
            <h3 className="text-lg font-semibold">新建频道转发规则</h3>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="block text-xs text-slate-500 mb-1">规则名称</label>
                <input
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="例如：海外币圈快讯汉化转发"
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">监听采集账号</label>
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
                <label className="block text-xs text-slate-500 mb-1">发布执行账号</label>
                <select
                  value={publisherId}
                  onChange={(e) => setPublisherId(e.target.value)}
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
                <label className="block text-xs text-slate-500 mb-1">源频道 (@username 或 ID)</label>
                <input
                  required
                  value={sourceChat}
                  onChange={(e) => setSourceChat(e.target.value)}
                  placeholder="@source_channel"
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">目标频道 (@username 或 ID)</label>
                <input
                  required
                  value={targetChat}
                  onChange={(e) => setTargetChat(e.target.value)}
                  placeholder="@my_channel"
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
            </div>

            <div className="space-y-2">
              <label className="inline-flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={enableAi}
                  onChange={(e) => setEnableAi(e.target.checked)}
                />
                启用 OpenAI 兼容大模型翻译清洗
              </label>
              {enableAi && (
                <textarea
                  rows={2}
                  value={aiPrompt}
                  onChange={(e) => setAiPrompt(e.target.value)}
                  className="w-full px-3 py-2 text-xs rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              )}
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-500">正则替换规则</span>
                <button
                  type="button"
                  onClick={() =>
                    setRegexItems((prev) => [...prev, { pattern: '', replace: '' }])
                  }
                  className="text-xs text-indigo-500 hover:underline"
                >
                  + 添加替换对
                </button>
              </div>
              {regexItems.map((item, idx) => (
                <div key={idx} className="grid grid-cols-5 gap-2">
                  <input
                    value={item.pattern}
                    onChange={(e) => {
                      const next = [...regexItems]
                      next[idx].pattern = e.target.value
                      setRegexItems(next)
                    }}
                    placeholder="正则匹配（如 @old_ch）"
                    className="col-span-2 px-2.5 py-1.5 text-xs rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                  />
                  <input
                    value={item.replace}
                    onChange={(e) => {
                      const next = [...regexItems]
                      next[idx].replace = e.target.value
                      setRegexItems(next)
                    }}
                    placeholder="替换为（如 @my_ch）"
                    className="col-span-2 px-2.5 py-1.5 text-xs rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                  />
                  <button
                    type="button"
                    onClick={() =>
                      setRegexItems((prev) => prev.filter((_, i) => i !== idx))
                    }
                    className="text-xs text-rose-500"
                  >
                    移除
                  </button>
                </div>
              ))}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-slate-500 mb-1">屏蔽词（英文逗号分隔）</label>
                <input
                  value={blockedText}
                  onChange={(e) => setBlockedText(e.target.value)}
                  placeholder="广告, 博彩, 加微信"
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">底部追加文案（可选）</label>
                <input
                  value={appendFooter}
                  onChange={(e) => setAppendFooter(e.target.value)}
                  placeholder="关注频道 @my_channel"
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">最小随机延迟 (秒)</label>
                <input
                  type="number"
                  min={0}
                  value={minDelay}
                  onChange={(e) => setMinDelay(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">最大随机延迟 (秒)</label>
                <input
                  type="number"
                  min={0}
                  value={maxDelay}
                  onChange={(e) => setMaxDelay(e.target.value)}
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

