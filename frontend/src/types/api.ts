export type AccountStatus =
  | 'pending'
  | 'active'
  | 'cooldown'
  | 'restricted'
  | 'frozen'
  | 'invalid'
  | 'banned'

export type AccountRole = 'listener' | 'worker' | 'publisher'

export interface DeviceProfile {
  id: number
  platform: string
  api_id: number
  device_model: string
  system_version: string
  app_version: string
  lang_code: string
  system_lang_code: string
  unique_seed: string
}

export interface Account {
  id: number
  account_uuid: string
  phone: string
  country_code: string | null
  tg_user_id: number | null
  username: string | null
  first_name: string | null
  import_source: string
  account_role: AccountRole
  proxy_id: number
  device_profile_id: number
  status: AccountStatus
  health_score: number
  cooldown_until: string | null
  spambot_status: string | null
  last_health_check_at: string | null
  timezone: string
  quiet_hours_enabled: boolean
  daily_action_count: number
  daily_action_limit: number
  last_active_at: string | null
  created_at: string
  updated_at: string
  device_profile: DeviceProfile | null
}

export interface ProxyItem {
  id: number
  name: string
  protocol: 'socks5' | 'http'
  host: string
  port: number
  username: string | null
  has_password: boolean
  country_code: string | null
  max_accounts: number
  status: 'active' | 'dead' | 'slow'
  latency_ms: number | null
  last_checked_at: string | null
  created_at: string
  bound_account_count: number
}

export interface ProxyCreateInput {
  name: string
  protocol: 'socks5' | 'http'
  host: string
  port: number
  username?: string | null
  password?: string | null
  country_code?: string | null
  max_accounts: number
}

export interface ProxyCheckResult {
  proxy_id: number
  alive: boolean
  status: string
  latency_ms: number | null
  error: string | null
  last_checked_at: string
}

export interface SystemStats {
  total_accounts: number
  status_counts: Record<string, number>
  cpu_percent: number
  memory_percent: number
  memory_used_mb: number
  memory_total_mb: number
  pool_pinned_count: number
  pool_lru_count: number
  pool_total_active: number
  ws_connections: number
}

export interface TaskLog {
  id: number
  job_id: number | null
  account_id: number
  action: string
  result: string
  target_ref: string | null
  wait_seconds: number
  error_detail: string | null
  created_at: string
}

export interface WsEventMessage {
  type: 'task_log' | 'alert' | 'account_status' | 'keyword_alert'
  timestamp: string
  data: Record<string, unknown>
}

export interface RegexReplacementItem {
  pattern: string
  replace: string
}

export interface ChannelSyncRule {
  id: number
  name: string
  listener_account_id: number
  publisher_account_id: number
  source_chat_id: string
  target_chat_id: string
  enable_ai_translate: boolean
  ai_system_prompt: string
  regex_replacements: RegexReplacementItem[]
  blocked_keywords: string[]
  append_footer: string | null
  min_delay_sec: number
  max_delay_sec: number
  is_enabled: boolean
  created_at: string
}

export interface ChannelSyncRuleCreateInput {
  name: string
  listener_account_id: number
  publisher_account_id: number
  source_chat_id: string
  target_chat_id: string
  enable_ai_translate: boolean
  ai_system_prompt: string
  regex_replacements: RegexReplacementItem[]
  blocked_keywords: string[]
  append_footer: string | null
  min_delay_sec: number
  max_delay_sec: number
  is_enabled: boolean
}

export interface ScheduledPost {
  id: number
  title: string
  publisher_account_id: number
  target_chat_ids: string[]
  content_text: string
  parse_mode: 'html' | 'md'
  media_file_path: string | null
  disable_web_page_preview: boolean
  scheduled_at: string
  status: 'pending' | 'running' | 'sent' | 'failed' | 'cancelled'
  error_message: string | null
  sent_at: string | null
  created_at: string
}

export interface ScheduledPostCreateInput {
  title: string
  publisher_account_id: number
  target_chat_ids: string[]
  content_text: string
  parse_mode: 'html' | 'md'
  media_file_path: string | null
  disable_web_page_preview: boolean
  scheduled_at: string
}

export interface MediaUploadResult {
  file_path: string
  filename: string
  size_bytes: number
}

export interface KeywordRule {
  id: number
  name: string
  listener_account_id: number
  monitored_chat_ids: string[]
  keywords: string[]
  match_mode: 'contains' | 'regex'
  exclude_keywords: string[]
  alert_webhook_url: string | null
  alert_target_chat_id: string | null
  is_enabled: boolean
  created_at: string
}

export interface KeywordRuleCreateInput {
  name: string
  listener_account_id: number
  monitored_chat_ids: string[]
  keywords: string[]
  match_mode: 'contains' | 'regex'
  exclude_keywords: string[]
  alert_webhook_url: string | null
  alert_target_chat_id: string | null
  is_enabled: boolean
}

export interface KeywordAlert {
  id: number
  rule_id: number
  matched_keyword: string
  source_chat_title: string | null
  source_chat_id: string
  sender_username: string | null
  message_text: string
  message_link: string | null
  is_read: boolean
  created_at: string
}

