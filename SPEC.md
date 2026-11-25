# SPEC.md — 系统详细技术规格说明书

## 一、PostgreSQL 数据库完整表结构（共 9 张表）

所有表必须使用 SQLAlchemy 2.0 声明式映射，并与以下 PostgreSQL 16 DDL 保持字段名、类型、约束完全一致。

### 1. 代理池表 (`proxies`)
```sql
CREATE TABLE proxies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    protocol VARCHAR(16) NOT NULL DEFAULT 'socks5',  -- socks5 / http
    host VARCHAR(255) NOT NULL,
    port INTEGER NOT NULL,
    username VARCHAR(128),
    password_encrypted TEXT,                         -- Fernet 加密
    country_code VARCHAR(8),                         -- ISO 国家码，如 US / GB / JP
    max_accounts INTEGER NOT NULL DEFAULT 2,         -- 单 IP 硬上限（建议 1-3）
    status VARCHAR(20) NOT NULL DEFAULT 'active',    -- active / dead / slow
    latency_ms INTEGER,
    last_checked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 2. 设备指纹表 (`device_profiles`)
```sql
CREATE TABLE device_profiles (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(32) NOT NULL,                   -- desktop / android / ios
    api_id INTEGER NOT NULL,
    api_hash VARCHAR(64) NOT NULL,
    device_model VARCHAR(128) NOT NULL,
    system_version VARCHAR(64) NOT NULL,
    app_version VARCHAR(32) NOT NULL,
    lang_code VARCHAR(16) NOT NULL DEFAULT 'en',
    system_lang_code VARCHAR(16) NOT NULL DEFAULT 'en-US',
    unique_seed VARCHAR(64) UNIQUE NOT NULL,         -- 固定随机种子，防止重连变更
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 3. 100 账号生命周期与健康状态主表 (`accounts`)
```sql
CREATE TABLE accounts (
    id SERIAL PRIMARY KEY,
    account_uuid UUID UNIQUE NOT NULL,               -- 对应 storage/sessions/{uuid}.session
    phone VARCHAR(32) UNIQUE NOT NULL,
    country_code VARCHAR(8),                         -- 手机号归属国，与 proxy.country_code 比对
    tg_user_id BIGINT UNIQUE,
    username VARCHAR(64),
    first_name VARCHAR(128),
    import_source VARCHAR(24) NOT NULL,              -- tdata / session / phone_login
    session_file_path TEXT NOT NULL,
    two_fa_encrypted TEXT,                           -- Fernet 加密
    account_role VARCHAR(24) NOT NULL DEFAULT 'worker', -- listener(常驻监控) / worker(任务号) / publisher(发帖号)

    -- 强绑定外键
    device_profile_id INTEGER UNIQUE NOT NULL REFERENCES device_profiles(id) ON DELETE RESTRICT,
    proxy_id INTEGER NOT NULL REFERENCES proxies(id) ON DELETE RESTRICT,

    -- 生命周期、健康状态与冷却控制
    status VARCHAR(24) NOT NULL DEFAULT 'active',    -- pending / active / cooldown / restricted / frozen / banned / invalid
    health_score INTEGER NOT NULL DEFAULT 100,       -- 0-100 健康分，每次风控扣分，连续正常加分
    cooldown_until TIMESTAMPTZ,                      -- 冷却截止时间（大于 NOW() 时严禁调度）
    spambot_status TEXT,                             -- @SpamBot 最新体检返回摘要
    last_health_check_at TIMESTAMPTZ,
    timezone VARCHAR(64) NOT NULL DEFAULT 'America/New_York', -- 拟人作息时区
    quiet_hours_enabled BOOLEAN NOT NULL DEFAULT TRUE,        -- 是否开启 00:00-07:30 夜间静默

    -- 每日配额限制
    daily_action_count INTEGER NOT NULL DEFAULT 0,   -- 每日 00:00 (UTC) 由调度器清零
    daily_action_limit INTEGER NOT NULL DEFAULT 30,

    last_active_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_accounts_schedulable ON accounts (status, cooldown_until, account_role);
CREATE INDEX idx_accounts_proxy_id ON accounts (proxy_id);
```

### 4. 任务配置表 (`task_jobs`)
```sql
CREATE TABLE task_jobs (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    job_type VARCHAR(32) NOT NULL,                   -- health_check / channel_sync / scheduled_post / keyword_monitor / keep_alive
    cron_expr VARCHAR(64),                           -- 标准 5 段 Cron；实时监听类任务可为空
    target_account_ids JSONB NOT NULL DEFAULT '[]',  -- 参与任务的 account_id 数组
    payload JSONB NOT NULL DEFAULT '{}',             -- 任务扩展参数
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_run_at TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 5. 风控与任务审计日志表 (`task_logs`)
```sql
CREATE TABLE task_logs (
    id BIGSERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES task_jobs(id) ON DELETE SET NULL,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    action VARCHAR(64) NOT NULL,                     -- health_check / sync_forward / send_post / keyword_hit / proxy_check
    result VARCHAR(24) NOT NULL,                     -- success / flood_wait / peer_flood / proxy_dead / auth_invalid / skipped / error
    target_ref VARCHAR(128),                         -- 目标频道 ID 或消息 ID
    wait_seconds INTEGER NOT NULL DEFAULT 0,         -- 触发 FloodWait 时的官方等待秒数
    error_detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_task_logs_account_time ON task_logs (account_id, created_at DESC);
CREATE INDEX idx_task_logs_result ON task_logs (result, created_at DESC);
```

### 6. 业务表 A：多频道采集与 AI 翻译转发规则表 (`channel_sync_rules` & `sync_message_history`)
```sql
CREATE TABLE channel_sync_rules (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    listener_account_id INTEGER NOT NULL REFERENCES accounts(id), -- 负责采集的账号
    publisher_account_id INTEGER NOT NULL REFERENCES accounts(id),-- 负责发布的账号（可与采集号相同）
    source_chat_id VARCHAR(128) NOT NULL,            -- 源频道 @username 或数字 ID
    target_chat_id VARCHAR(128) NOT NULL,            -- 目标频道 @username 或数字 ID
    enable_ai_translate BOOLEAN NOT NULL DEFAULT TRUE,
    ai_system_prompt TEXT NOT NULL DEFAULT '将以下内容翻译为流畅、口语化的中文，保留核心信息与排版，去除原频道广告和推广链接。',
    regex_replacements JSONB NOT NULL DEFAULT '[]',  -- [{"pattern": "@old_ch", "replace": "@my_ch"}]
    blocked_keywords JSONB NOT NULL DEFAULT '[]',    -- 命中则跳过转发的屏蔽词列表
    append_footer TEXT,                              -- 统一追加的底部文案/返佣链接
    min_delay_sec INTEGER NOT NULL DEFAULT 15,       -- 转发前最小随机延迟
    max_delay_sec INTEGER NOT NULL DEFAULT 60,       -- 转发前最大随机延迟
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 去重记录表：防止重启后重复转发同一条消息
CREATE TABLE sync_message_history (
    id BIGSERIAL PRIMARY KEY,
    rule_id INTEGER NOT NULL REFERENCES channel_sync_rules(id) ON DELETE CASCADE,
    source_chat_id VARCHAR(128) NOT NULL,
    source_msg_id BIGINT NOT NULL,
    target_msg_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (rule_id, source_chat_id, source_msg_id)
);
```

### 7. 业务表 B：定时发帖排期表 (`scheduled_posts`)
```sql
CREATE TABLE scheduled_posts (
    id SERIAL PRIMARY KEY,
    title VARCHAR(128) NOT NULL,
    publisher_account_id INTEGER NOT NULL REFERENCES accounts(id),
    target_chat_ids JSONB NOT NULL,                  -- 支持群发到多个自有频道 ["@ch1", "@ch2"]
    content_text TEXT NOT NULL,
    parse_mode VARCHAR(16) NOT NULL DEFAULT 'html',  -- html / md
    media_file_path TEXT,                            -- 可选：storage/uploads/ 下的本地图片/视频路径
    disable_web_page_preview BOOLEAN NOT NULL DEFAULT FALSE,
    scheduled_at TIMESTAMPTZ NOT NULL,               -- 计划发送时间
    status VARCHAR(24) NOT NULL DEFAULT 'pending',   -- pending / running / sent / failed / cancelled
    error_message TEXT,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_scheduled_posts_due ON scheduled_posts (status, scheduled_at);
```

### 8. 业务表 C：关键词监控与告警表 (`keyword_rules` & `keyword_alerts`)
```sql
CREATE TABLE keyword_rules (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    listener_account_id INTEGER NOT NULL REFERENCES accounts(id),
    monitored_chat_ids JSONB NOT NULL,               -- 监控的群组/频道列表
    keywords JSONB NOT NULL,                         -- 关键词列表 ["免费API", "空投"]
    match_mode VARCHAR(16) NOT NULL DEFAULT 'contains', -- contains / regex
    exclude_keywords JSONB NOT NULL DEFAULT '[]',    -- 排除词列表
    alert_webhook_url TEXT,                          -- 可选：飞书/钉钉/Telegram Bot Webhook 地址
    alert_target_chat_id VARCHAR(128),               -- 可选：通过账号转发告警到的内部群 ID
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE keyword_alerts (
    id BIGSERIAL PRIMARY KEY,
    rule_id INTEGER NOT NULL REFERENCES keyword_rules(id) ON DELETE CASCADE,
    matched_keyword VARCHAR(128) NOT NULL,
    source_chat_title VARCHAR(255),
    source_chat_id VARCHAR(128) NOT NULL,
    sender_username VARCHAR(128),
    message_text TEXT NOT NULL,
    message_link TEXT,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 二、100 账号生命周期状态机

调度引擎必须严格维护 `accounts.status` 的状态流转：

1. **`pending`**：刚创建尚未完成首次连通性验证。
2. **`active`**：代理畅通、Session 有效、未在冷却期，可参与调度。
3. **`cooldown`**：触发 `FloodWaitError` 进入自动冷却；当 `NOW() 大于 cooldown_until` 时，由每分钟运行的后台恢复任务自动改回 `active`。
4. **`restricted`**：触发 `PeerFloodError` 或 `@SpamBot` 返回受限提示。停止一切写操作（发帖/转发），仅允许人工介入或只读体检。
5. **`frozen`**：管理员手动冻结暂停的账号。
6. **`invalid`**：Session 失效（`AuthKeyUnregisteredError`），需重新导入。
7. **`banned`**：账号被官方封禁（`UserDeactivatedBanError`），永久停用并自动释放其代理配额统计。

**健康分（`health_score`）计算规则**：
- 初始 100 分；
- 触发 `FloodWaitError` 扣 15 分；触发 `PeerFloodError` 扣 40 分；代理不可达扣 5 分；
- 连续 24 小时无风控错误且成功执行任务，每日加 5 分（上限 100 分）。

---

## 三、3 种账号导入方式精确实现规格

无论哪种方式导入，**第一步必须要求前端传入一个已存在且未超容（当前绑定数小于 `max_accounts`）的 `proxy_id`**，并先通过 `ProxyChecker` 探活。

### 方式 1：`tdata` 压缩包导入 (`POST /api/accounts/import/tdata`)
- **输入**：`multipart/form-data`，包含 `file`（`.zip` 压缩包，内含 `tdata/` 目录）、`proxy_id`、可选 `two_fa`、`country_code`、`account_role`。
- **处理流程**：
  1. 解压 ZIP 到 `storage/temp/{temp_uuid}/`，定位 `tdata` 文件夹路径。
  2. 生成新的 `account_uuid` 和目标路径 `storage/sessions/{account_uuid}.session`。
  3. 使用 `opentele2` 的 `TDesktop(tdata_path)` 加载，生成固定的官方桌面端 API 配置（`API.TelegramDesktop.Generate(unique_id=str(account_uuid))`），调用 `ToTelethon(session_path, flag=UseCurrentSession, proxy=proxy_tuple, api=api_obj)`。
  4. 通过代理连接 Telegram，调用 `await client.get_me()` 获取 `phone`、`tg_user_id`、`username`、`first_name`。
  5. 立即断开连接，将 `device_profiles` 和 `accounts` 写入 PostgreSQL，**在 `finally` 块中彻底删除 `storage/temp/{temp_uuid}/`**。

### 方式 2：已有 `.session` 文件导入 (`POST /api/accounts/import/session`)
- **输入**：`multipart/form-data`，包含 `session_file`（`.session` 文件）、可选 `json_file`（部分号商附带的设备信息 JSON）、`proxy_id`、可选 `two_fa`、`country_code`、`account_role`。
- **处理流程**：
  1. 将 `.session` 保存至 `storage/sessions/{account_uuid}.session`。
  2. 若上传了 `json_file`，解析其中的 `app_id`、`app_hash`、`device`、`sdk`、`app_version`、`lang_code`；若未上传，则使用 `opentele2` 生成一套固定的 `TelegramDesktop` 或 `TelegramAndroid` 参数并绑定 `unique_seed`。
  3. 使用该指纹 + 绑定代理初始化 `TelegramClient`，调用 `connect()` 并验证 `await client.is_user_authorized()`。
  4. 若返回 `False`，删除刚保存的 `.session` 文件并返回 HTTP 400（提示 Session 已失效）；若成功，调用 `get_me()` 并入库。

### 方式 3：手机号 + 验证码 + 2FA 网页端登录
拆分为两个 REST 接口，服务端在内存中用字典 `_pending_logins: dict[str, PendingLogin]` 暂存登录态（超过 5 分钟自动清理并断开连接）：

1. **发送验证码** (`POST /api/accounts/import/phone/send-code`)
   - 输入：`{ "phone": "+1...", "proxy_id": 1, "platform": "android", "country_code": "US", "account_role": "worker" }`
   - 流程：探活代理 → 用 `opentele2` 生成固定设备指纹 → 创建临时 `.session` → 连接并调用 `await client.send_code_request(phone)` → 返回 `{ "login_token": "...", "phone_code_hash": "..." }`。
2. **提交验证码完成登录** (`POST /api/accounts/import/phone/verify`)
   - 输入：`{ "login_token": "...", "code": "12345", "two_fa": "可选密码" }`
   - 流程：取出暂存的 `client` → 调用 `await client.sign_in(phone, code, phone_code_hash=...)` → 若抛出 `SessionPasswordNeededError`，必须检查 `two_fa` 并调用 `await client.sign_in(password=two_fa)`（若未提供则返回 `{ "need_2fa": true }` 让前端弹出 2FA 输入框）→ 登录成功后调用 `get_me()`、入库 `device_profiles` 和 `accounts`、断开临时连接并清理内存字典。

---

## 四、核心引擎接口设计（必须严格照此实现）

### 1. `ClientPoolManager` (`backend/app/engine/pool.py`)
- 维护两类客户端：
  - **常驻监听池 (`_pinned_clients`)**：仅给分配了活跃 `channel_sync_rules` 或 `keyword_rules` 的监听号使用，启动时自动连接并挂载 `events.NewMessage` 监听器。
  - **LRU 任务池 (`_lru_clients`, `max_size=20`)**：给发帖、体检等短时任务使用；超过 20 个时断开最久未使用的连接；后台每 2 分钟扫描一次，断开闲置超过 10 分钟的连接。
- 每个账号必须通过 `get_account_lock(account_id)` 获取独占 `asyncio.Lock`。

### 2. `RiskGuard` (`backend/app/engine/guard.py`)
所有主动调用 Telegram 写操作的方法，必须通过统一入口 `run_safe_account_task(account_id, action_name, coro_factory, job_id=None, target_ref=None)` 包装执行，内部严格执行以下 8 步：
1. 从 PostgreSQL 查询最新 `account` 与 `proxy`，校验 `status == 'active'`、`cooldown_until` 已过期、`daily_action_count < daily_action_limit`。
2. 校验作息时间：若 `quiet_hours_enabled` 为 `True`，按 `account.timezone` 计算当前本地小时数，若在 0 到 7 点之间，记录 `skipped` 日志并直接返回。
3. 获取 `account_lock` 与全局 `GLOBAL_SEMAPHORE(6)`。
4. 调用 `ProxyChecker.verify_proxy_alive(proxy)` 强制探活；不通则将 `proxy.status` 置为 `dead`，写 `proxy_dead` 日志并中止。
5. 执行前置随机抖动 `await asyncio.sleep(random.uniform(2.0, 8.0))`。
6. 从 `ClientPoolManager` 获取已绑定固定指纹与代理的 `client`，执行 `await coro_factory(client)`。
7. 异常分类熔断：
   - `FloodWaitError` → 置 `cooldown`，更新 `cooldown_until`，扣 15 健康分，写 `flood_wait` 日志。
   - `PeerFloodError` → 置 `restricted`，扣 40 健康分，写 `peer_flood` 日志，通过 WebSocket 推送红色告警。
   - `AuthKeyUnregisteredError` / `UserDeactivatedBanError` → 置 `invalid` / `banned`，写 `auth_invalid` 日志。
   - `SlowModeWaitError` → 仅写日志，不惩罚账号。
8. 成功时：`daily_action_count += 1`，更新 `last_active_at`，写 `success` 审计日志，通过 WebSocket 推送实时动态。

---

## 五、首批三大核心业务逻辑规格

### 业务 1：多频道自动采集与 AI 翻译转发 (`workers/channel_sync.py`)
- 监听端（`listener_account_id`）挂载 `events.NewMessage(chats=source_chat_ids)`。
- 收到新消息后执行流水线：
  1. 查询 `sync_message_history` 去重（已转发直接忽略）。
  2. 检查 `blocked_keywords`（命中则写 `skipped` 日志丢弃）。
  3. 对文本按顺序执行 `regex_replacements` 正则清洗。
  4. 若 `enable_ai_translate=True` 且存在文本，异步调用 OpenAI 兼容接口（配置在 `.env` 的 `AI_API_BASE`、`AI_API_KEY`、`AI_MODEL`），超时时间设为 30 秒，失败时记录错误并可降级保留原文或跳过。
  5. 若配置了 `append_footer`，拼接在正文末尾。
  6. 随机休眠 `random.uniform(min_delay_sec, max_delay_sec)` 秒。
  7. 将发送任务交给 `RiskGuard` 由 `publisher_account_id` 发布至 `target_chat_id`（若原消息带图片/视频，先下载至 `storage/temp/` 再重新上传发送，**不带“转发自某频道”的原始来源标记**，发完后删除临时文件）。
  8. 写入 `sync_message_history` 与 `task_logs`。

### 业务 2：定时发帖排期 (`workers/scheduled_post.py`)
- `APScheduler` 每 30 秒扫描一次 `scheduled_posts` 表中 `status='pending'` 且 `scheduled_at 小于等于 NOW()` 的记录。
- 先使用原子更新将记录改为 `running`（防止重复触发）。
- 遍历 `target_chat_ids`，每发完一个目标频道，通过 `RiskGuard` 执行并在频道之间插入 10 至 30 秒随机延迟；支持纯文本及 `media_file_path` 图文发送。
- 全部发送成功更新为 `sent` 与 `sent_at`；部分或全部失败记录 `failed` 及 `error_message`。

### 业务 3：关键词实时监控与告警 (`workers/keyword_monitor.py`)
- 监听端（`listener_account_id`）挂载 `events.NewMessage(chats=monitored_chat_ids)`。
- 收到消息后先检查 `exclude_keywords`（命中跳过），再根据 `match_mode`（`contains` 忽略大小写包含匹配，或 `regex` 正则匹配）检查 `keywords`。
- 命中后：
  1. 立即写入 `keyword_alerts` 表。
  2. 通过 `ws_manager` 向 React 前端广播实时弹窗/红点通知。
  3. 若配置了 `alert_webhook_url`，异步 `POST` JSON 载荷推送到外部 Webhook（兼容飞书/钉钉/Telegram Bot）。
  4. 若配置了 `alert_target_chat_id`，通过 `RiskGuard` 将命中摘要与原消息直达链接发往内部告警群。

---

## 六、前后端 API 路由总览

- **系统与实时流**：`GET /api/system/stats`（账号各状态统计 + `psutil` CPU/内存 + 活跃连接池数）、`WS /ws/events`（实时日志与关键词告警推送）
- **代理管理**：`GET/POST/DELETE /api/proxies`、`POST /api/proxies/{id}/check`（手动测速探活）
- **账号管理与 3 种导入**：`GET/PATCH/DELETE /api/accounts`、`POST /api/accounts/import/tdata`、`POST /api/accounts/import/session`、`POST /api/accounts/import/phone/send-code`、`POST /api/accounts/import/phone/verify`、`POST /api/accounts/{id}/health-check`、`POST /api/accounts/batch-health-check`
- **任务与审计日志**：`GET/POST/PATCH/DELETE /api/tasks`、`GET /api/logs`（支持按 `account_id`、`result`、时间筛选）
- **三大业务模块**：
  - `GET/POST/PATCH/DELETE /api/sync-rules` + `POST /api/sync-rules/{id}/toggle`
  - `GET/POST/PATCH/DELETE /api/scheduled-posts` + `POST /api/uploads/media`
  - `GET/POST/PATCH/DELETE /api/keyword-rules` + `GET /api/keyword-alerts` + `PATCH /api/keyword-alerts/{id}/read`