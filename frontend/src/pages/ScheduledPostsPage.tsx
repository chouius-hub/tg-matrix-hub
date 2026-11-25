import { FormEvent, useEffect, useState } from 'react'
import { Plus, RefreshCw, Trash2, Upload } from 'lucide-react'
import { api } from '../api/client'
import { StatusBadge } from '../components/StatusBadge'
import type { Account, ScheduledPost } from '../types/api'

/**
 * 定时发帖排期页：支持图文媒体上传、多目标频道排期发送与状态追踪。
 */
export function ScheduledPostsPage() {
  const [posts, setPosts] = useState<ScheduledPost[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [title, setTitle] = useState('')
  const [publisherId, setPublisherId] = useState('')
  const [targetsText, setTargetsText] = useState('')
  const [parseMode, setParseMode] = useState<'html' | 'md'>('html')
  const [contentText, setContentText] = useState('')
  const [mediaPath, setMediaPath] = useState<string | null>(null)
  const [mediaName, setMediaName] = useState<string | null>(null)
  const [scheduledAt, setScheduledAt] = useState('')
  const [uploading, setUploading] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const loadData = async () => {
    setLoading(true)
    try {
      const [postData, accData] = await Promise.all([
        api.getScheduledPosts(),
        api.getAccounts(),
      ])
      setPosts(postData)
      setAccounts(accData)
      if (!publisherId && accData[0]) setPublisherId(String(accData[0].id))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载定时发帖列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const handleUploadMedia = async (file: File | null) => {
    if (!file) return
    setUploading(true)
    setError(null)
    try {
      const res = await api.uploadMedia(file)
      setMediaPath(res.file_path)
      setMediaName(res.filename)
    } catch (err) {
      setError(err instanceof Error ? err.message : '媒体上传失败')
    } finally {
      setUploading(false)
    }
  }

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault()
    if (!publisherId || !scheduledAt) {
      setError('请选择发布账号和计划发送时间')
      return
    }
    const targets = targetsText
      .split(/[\n,]/)
      .map((s) => s.trim())
      .filter(Boolean)
    if (targets.length === 0) {
      setError('请填写至少一个目标频道')
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      await api.createScheduledPost({
        title: title.trim(),
        publisher_account_id: Number(publisherId),
        target_chat_ids: targets,
        content_text: contentText,
        parse_mode: parseMode,
        media_file_path: mediaPath,
        disable_web_page_preview: false,
        scheduled_at: new Date(scheduledAt).toISOString(),
      })
      setShowModal(false)
      setTitle('')
      setTargetsText('')
      setContentText('')
      setMediaPath(null)
      setMediaName(null)
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建定时发帖失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await api.deleteScheduledPost(id)
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除发帖记录失败')
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">定时发帖排期</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            调度器每 30 秒扫描到期任务，经 RiskGuard 错峰发送至多个自有频道
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
            新建定时发帖
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
              <th className="px-4 py-3">任务标题</th>
              <th className="px-4 py-3">发布账号</th>
              <th className="px-4 py-3">目标频道</th>
              <th className="px-4 py-3">计划发送时间</th>
              <th className="px-4 py-3">状态</th>
              <th className="px-4 py-3">备注 / 错误</th>
              <th className="px-4 py-3 text-right">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
            {posts.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-slate-500">
                  暂无定时发帖排期
                </td>
              </tr>
            ) : (
              posts.map((post) => (
                <tr key={post.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                  <td className="px-4 py-3 font-medium">
                    {post.title}
                    {post.media_file_path && (
                      <span className="ml-2 text-[11px] px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-500">
                        含媒体
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">#{post.publisher_account_id}</td>
                  <td className="px-4 py-3 text-xs font-mono">
                    {post.target_chat_ids.join(', ')}
                  </td>
                  <td className="px-4 py-3 text-xs font-mono">
                    {new Date(post.scheduled_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge value={post.status} />
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500 max-w-xs truncate">
                    {post.error_message || (post.sent_at ? `发送于 ${new Date(post.sent_at).toLocaleTimeString()}` : '-')}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => handleDelete(post.id)}
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
            className="w-full max-w-xl rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-6 space-y-4 shadow-xl"
          >
            <h3 className="text-lg font-semibold">新建定时发帖排期</h3>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="block text-xs text-slate-500 mb-1">任务标题</label>
                <input
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="例如：每日晚间行情播报"
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">发布账号</label>
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
                <label className="block text-xs text-slate-500 mb-1">计划发送时间</label>
                <input
                  required
                  type="datetime-local"
                  value={scheduledAt}
                  onChange={(e) => setScheduledAt(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
              <div className="col-span-2">
                <label className="block text-xs text-slate-500 mb-1">
                  目标频道（多个频道用英文逗号或换行分隔）
                </label>
                <input
                  required
                  value={targetsText}
                  onChange={(e) => setTargetsText(e.target.value)}
                  placeholder="@channel_1, @channel_2"
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
              <div className="col-span-2">
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs text-slate-500">正文内容</label>
                  <select
                    value={parseMode}
                    onChange={(e) => setParseMode(e.target.value as 'html' | 'md')}
                    className="text-xs px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800"
                  >
                    <option value="html">HTML 格式</option>
                    <option value="md">Markdown 格式</option>
                  </select>
                </div>
                <textarea
                  required
                  rows={4}
                  value={contentText}
                  onChange={(e) => setContentText(e.target.value)}
                  placeholder="支持 <b>加粗</b> 或 **加粗**..."
                  className="w-full px-3 py-2 text-sm rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
              <div className="col-span-2">
                <label className="inline-flex items-center gap-2 px-3 py-2 text-xs rounded-lg border border-dashed border-slate-300 dark:border-slate-700 cursor-pointer hover:border-indigo-500">
                  <Upload className="w-4 h-4 text-slate-400" />
                  <span>
                    {uploading
                      ? '上传中...'
                      : mediaName
                        ? `已上传: ${mediaName}`
                        : '附加图片或视频（可选）'}
                  </span>
                  <input
                    type="file"
                    accept="image/*,video/*"
                    className="hidden"
                    onChange={(e) => handleUploadMedia(e.target.files?.[0] ?? null)}
                  />
                </label>
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
                disabled={submitting || uploading}
                className="px-4 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50"
              >
                {submitting ? '提交中...' : '加入排期'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}

