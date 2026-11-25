import type {
  Account,
  ChannelSyncRule,
  ChannelSyncRuleCreateInput,
  KeywordAlert,
  KeywordRule,
  KeywordRuleCreateInput,
  MediaUploadResult,
  ProxyCheckResult,
  ProxyCreateInput,
  ProxyItem,
  ScheduledPost,
  ScheduledPostCreateInput,
  SystemStats,
  TaskLog,
} from '../types/api'

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options)
  if (!response.ok) {
    let message = `请求失败 (${response.status})`
    try {
      const payload = await response.json()
      if (typeof payload?.detail === 'string') {
        message = payload.detail
      } else if (Array.isArray(payload?.detail)) {
        message = payload.detail.map((item: { msg?: string }) => item.msg || '').join('; ')
      }
    } catch {
      // 忽略非 JSON 错误体
    }
    throw new Error(message)
  }

  if (response.status === 204) {
    return undefined as T
  }
  return response.json() as Promise<T>
}

export const api = {
  getSystemStats: () => request<SystemStats>('/api/system/stats'),

  getLogs: (params?: { account_id?: number; result?: string; limit?: number }) => {
    const query = new URLSearchParams()
    if (params?.account_id) query.set('account_id', String(params.account_id))
    if (params?.result) query.set('result', params.result)
    if (params?.limit) query.set('limit', String(params.limit))
    const qs = query.toString()
    return request<TaskLog[]>(`/api/logs${qs ? `?${qs}` : ''}`)
  },

  getProxies: () => request<ProxyItem[]>('/api/proxies'),
  createProxy: (data: ProxyCreateInput) =>
    request<ProxyItem>('/api/proxies', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),
  deleteProxy: (id: number) =>
    request<void>(`/api/proxies/${id}`, { method: 'DELETE' }),
  checkProxy: (id: number) =>
    request<ProxyCheckResult>(`/api/proxies/${id}/check`, { method: 'POST' }),

  getAccounts: (params?: { status?: string; search?: string }) => {
    const query = new URLSearchParams()
    if (params?.status) query.set('status', params.status)
    if (params?.search) query.set('search', params.search)
    const qs = query.toString()
    return request<Account[]>(`/api/accounts${qs ? `?${qs}` : ''}`)
  },
  updateAccount: (
    id: number,
    data: Partial<{
      status: 'active' | 'frozen'
      account_role: 'listener' | 'worker' | 'publisher'
      daily_action_limit: number
      timezone: string
      quiet_hours_enabled: boolean
      proxy_id: number
    }>,
  ) =>
    request<Account>(`/api/accounts/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),
  deleteAccount: (id: number) =>
    request<void>(`/api/accounts/${id}`, { method: 'DELETE' }),
  healthCheckAccount: (id: number) =>
    request<{ account_id: number; status: string; spambot_status: string }>(
      `/api/accounts/${id}/health-check`,
      { method: 'POST' },
    ),
  batchHealthCheck: (accountIds: number[]) =>
    request<Array<{ account_id: number; status: string; spambot_status: string }>>(
      '/api/accounts/batch-health-check',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_ids: accountIds }),
      },
    ),

  importTdata: (formData: FormData) =>
    request<Account>('/api/accounts/import/tdata', {
      method: 'POST',
      body: formData,
    }),
  importSession: (formData: FormData) =>
    request<Account>('/api/accounts/import/session', {
      method: 'POST',
      body: formData,
    }),
  phoneSendCode: (data: {
    phone: string
    proxy_id: number
    platform: 'android' | 'ios' | 'desktop'
    country_code?: string
    account_role: 'listener' | 'worker' | 'publisher'
  }) =>
    request<{ login_token: string; phone_code_hash: string }>(
      '/api/accounts/import/phone/send-code',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      },
    ),
  phoneVerify: (data: { login_token: string; code: string; two_fa?: string }) =>
    request<{ need_2fa: boolean; login_token: string; account: Account | null }>(
      '/api/accounts/import/phone/verify',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      },
    ),

  getSyncRules: () => request<ChannelSyncRule[]>('/api/sync-rules'),
  createSyncRule: (data: ChannelSyncRuleCreateInput) =>
    request<ChannelSyncRule>('/api/sync-rules', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),
  toggleSyncRule: (id: number) =>
    request<ChannelSyncRule>(`/api/sync-rules/${id}/toggle`, { method: 'POST' }),
  deleteSyncRule: (id: number) =>
    request<void>(`/api/sync-rules/${id}`, { method: 'DELETE' }),

  getScheduledPosts: () => request<ScheduledPost[]>('/api/scheduled-posts'),
  createScheduledPost: (data: ScheduledPostCreateInput) =>
    request<ScheduledPost>('/api/scheduled-posts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),
  deleteScheduledPost: (id: number) =>
    request<void>(`/api/scheduled-posts/${id}`, { method: 'DELETE' }),
  uploadMedia: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return request<MediaUploadResult>('/api/uploads/media', {
      method: 'POST',
      body: formData,
    })
  },

  getKeywordRules: () => request<KeywordRule[]>('/api/keyword-rules'),
  createKeywordRule: (data: KeywordRuleCreateInput) =>
    request<KeywordRule>('/api/keyword-rules', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),
  updateKeywordRule: (id: number, data: Partial<KeywordRuleCreateInput>) =>
    request<KeywordRule>(`/api/keyword-rules/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),
  deleteKeywordRule: (id: number) =>
    request<void>(`/api/keyword-rules/${id}`, { method: 'DELETE' }),

  getKeywordAlerts: (isRead?: boolean) => {
    const qs = isRead === undefined ? '' : `?is_read=${String(isRead)}`
    return request<KeywordAlert[]>(`/api/keyword-alerts${qs}`)
  },
  markKeywordAlertRead: (id: number) =>
    request<KeywordAlert>(`/api/keyword-alerts/${id}/read`, { method: 'PATCH' }),
}

