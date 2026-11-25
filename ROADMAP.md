# ROADMAP.md — 分阶段开发与验收清单

**执行规则**：每次只允许执行一个 Phase。完成当前 Phase 的所有代码编写与验收命令，确认全部通过后，再停止并等待用户指令进入下一 Phase。

---

## Phase 0：工程骨架与 PostgreSQL 基础设施
**目标**：搭建可启动的 PostgreSQL 16、FastAPI 骨架和全部 9 张数据库表。

### 任务清单
1. 创建 `docker-compose.yml`（PostgreSQL 16 容器，端口 5432，挂载持久化卷）与 `.env.example`（包含 `DATABASE_URL`、`FERNET_KEY`、`AI_API_BASE`、`AI_API_KEY`、`AI_MODEL`）。
2. 创建 `backend/requirements.txt` 并安装依赖。
3. 编写 `backend/app/core/config.py`、`database.py`、`security.py`（Fernet 加密解密，含单元测试）。
4. 严格按照 `SPEC.md` 第一节，编写 `backend/app/models/` 下全部 9 张 SQLAlchemy 2.0 ORM 模型。
5. 配置 `alembic`，生成初始迁移脚本并执行建表。
6. 编写最小 `backend/app/main.py`（含 `GET /api/health` 接口，验证数据库连接正常）。

### 验收标准（必须运行并贴出结果）
- `docker compose up -d` 启动 PostgreSQL 成功。
- `alembic upgrade head` 执行成功，数据库中存在全部 9 张表。
- 启动 `uvicorn app.main:app` 后，`GET /api/health` 返回 `{"status": "ok", "db": "connected"}`。

---

## Phase 1：代理强制探活 + 3 种账号导入 + @SpamBot 体检
**目标**：跑通账号资产的完整入库、指纹固化与健康检查闭环。

### 任务清单
1. 先在终端探测 `opentele2` 实际导出的 API 类名和转换方法，避免写错调用签名。
2. 实现 `backend/app/engine/proxy_checker.py`（SOCKS5/HTTP 异步探活与延迟测速，强制超时 8 秒）及代理 CRUD API（`/api/proxies`）。
3. 实现 `backend/app/engine/converter.py`，完整落地 `SPEC.md` 第三节的 **3 种导入方式**：
   - `tdata` ZIP 导入（解压 → `opentele2` 转换 → 提取固化指纹 → 清理临时目录）
   - `.session`（+ 可选 `.json`）导入
   - 手机号 + 验证码 + 2FA 两步登录（带 5 分钟 TTL 内存缓存清理）
4. 实现账号管理 CRUD API（支持查看列表、手动冻结/解冻、修改每日限额和作息时区、删除账号及本地 `.session`）。
5. 实现 `backend/app/workers/health_check.py`：通过绑定代理和固化指纹连上账号，向 `@SpamBot` 发送 `/start` 并解析返回文本，更新 `spambot_status`、`status`、`last_health_check_at`。

### 验收标准
- 使用无效代理导入账号时，API 明确拦截报错，不会尝试直连。
- 使用 `pytest` 通过代理探活单元测试、Fernet 加解密测试和 3 种导入路由参数校验测试。
- Swagger 文档（`/docs`）中代理、账号与 3 种导入接口全部可正常调用。

---

## Phase 2：核心防封引擎（连接池 + 风控熔断 + 调度器 + WebSocket）
**目标**：构建保护 100 个账号不被连坐封禁的核心调度层。

### 任务清单
1. 实现 `backend/app/engine/pool.py`（`ClientPoolManager`）：单账号 `asyncio.Lock`、LRU 20 连接上限、10 分钟闲置自动断开、常驻监听号注册接口。
2. 实现 `backend/app/engine/guard.py`（`run_safe_account_task`）：严格落实 `SPEC.md` 第四节的全部 8 步校验与异常分类熔断（`FloodWaitError` / `PeerFloodError` / `AuthKeyUnregisteredError` / `UserDeactivatedBanError`），并自动写入 `task_logs`。
3. 实现 `backend/app/engine/scheduler.py`（基于 `APScheduler`）：
   - 每 1 分钟检查并自动恢复已过 `cooldown_until` 的账号（`cooldown` → `active`）。
   - 每日 UTC 00:00 清零全部账号的 `daily_action_count`。
   - 加载 `task_jobs` 表中的定时任务（如定时批量体检）。
4. 实现 `backend/app/core/ws_manager.py`、`GET /api/system/stats`（含 `psutil` 资源监控）、`GET /api/logs` 和 `WS /ws/events`。

### 验收标准
- 编写并运行 `pytest` 模拟测试（Mock Telethon 异常）：
  - 模拟抛出 `FloodWaitError(60)` → 验证数据库状态自动变为 `cooldown`、`cooldown_until` 正确、`health_score` 减 15、`task_logs` 有记录。
  - 模拟抛出 `PeerFloodError` → 验证数据库状态变为 `restricted`、`health_score` 减 40，且未触发重试。
  - 模拟代理探活失败 → 验证直接返回 `proxy_dead`，不调用 `client.connect()`。
- FastAPI 启动与 Ctrl+C 关闭时，连接池与调度器优雅关闭无报错。

---

## Phase 3：React + Tailwind 可视化管理后台（基础与风控面板）
**目标**：打造对标现代桌面级控制台的前端界面，方便可视化管理 100 个账号。

### 任务清单
1. 初始化 `frontend/`（Vite + React 18 + TypeScript + Tailwind CSS），配置后端 API 代理。
2. 实现深色/浅色简洁侧边栏布局，包含 6 个导航页面：
   - **总览大盘（Dashboard）**：账号状态分布卡片（正常/冷却/受限/冻结/失效）、本机 CPU 与内存实时进度条、活跃连接池数、最近风控实时日志流（接入 WebSocket）。
   - **账号管理（Accounts）**：搜索/状态筛选表格（显示手机号、国家、绑定代理、设备指纹、健康分、冷却倒计时、今日配额 `count/limit`）、批量体检按钮、**“三合一导入弹窗”**（3 个 Tab 分别对应 `tdata` 拖拽上传、`.session` 上传、手机号验证码/2FA 分步登录）。
   - **代理池（Proxies）**：新增/批量导入代理、一键测速探活、展示当前绑定账号数/上限。
   - **业务模块占位页**：频道采集转发、定时发帖、关键词监控（在 Phase 4 & 5 填充完整交互）。
   - **风控审计日志（Logs）**：多条件筛选表格，红/黄/绿标签高亮 `peer_flood`、`flood_wait`、`success`。

### 验收标准
- `npm run build` 编译零 TypeScript 错误。
- 浏览器打开前端页面，可正常完成代理添加、测速、查看大盘统计和打开三合一账号导入弹窗。

---

## Phase 4：业务落地 A & B（多频道 AI 翻译转发 + 定时发帖排期）
**目标**：跑通前两个直接产生运营价值的自动化业务模块。

### 任务清单
1. **后端实现 `workers/channel_sync.py` 与 `/api/sync-rules`**：
   - 接入 `ClientPoolManager` 的常驻监听池，支持规则热加载（新建/启停规则无需重启后端）。
   - 完整实现去重（`sync_message_history`）、屏蔽词过滤、正则替换、OpenAI 兼容接口异步翻译、媒体下载重发（去转发来源标记）、随机延迟与 `RiskGuard` 托管发布。
2. **后端实现 `workers/scheduled_post.py` 与 `/api/scheduled-posts`、`/api/uploads/media`**：
   - 接入 `APScheduler` 每 30 秒扫描到期帖子，原子抢锁改为 `running`，经 `RiskGuard` 错峰发送至多个目标频道。
3. **前端补全两个业务页面**：
   - 频道转发规则配置页（支持填写源/目标频道、自定义 AI 翻译提示词、添加正则替换对与屏蔽词、一键开关）。
   - 定时发帖排期页（支持图文上传、选择发布账号、多选目标频道、日期时间选择器、发送状态列表）。

### 验收标准
- 创建一条转发规则后，后端日志正确挂载监听；单元测试验证正则清洗、屏蔽词跳过、去重拦截与 AI 翻译 mock 流程通过。
- 创建一条 1 分钟后执行的定时帖子，到期后调度器自动抓取并调用 `RiskGuard` 执行，状态与审计日志正确落库。

---

## Phase 5：业务落地 C（关键词监控告警）与全链路联调
**目标**：补齐关键词实时监控与告警闭环，完成 100 账号规模的压力自检。

### 任务清单
1. **后端实现 `workers/keyword_monitor.py` 与 `/api/keyword-rules`、`/api/keyword-alerts`**：
   - 接入常驻监听池，支持 `contains` 与 `regex` 匹配及排除词过滤。
   - 命中后写库 `keyword_alerts`、通过 WebSocket 推送前端红点告警、异步 POST 外部 `alert_webhook_url`、可选经 `RiskGuard` 转发到内部告警群。
2. **前端补全关键词监控页**：规则增删改查、实时告警信息流（带原消息跳转链接、一键标为已读、顶部导航栏未读告警角标）。
3. **全链路验收与防坑检查**：
   - 编写脚本向 PostgreSQL 插入 100 条模拟账号与 50 条代理测试数据，验证前端分页流畅、大盘查询响应小于 200ms、调度器批量巡检内存稳定。
   - 检查 `.gitignore`，确保 `.env`、`storage/sessions/`、`storage/uploads/`、`storage/temp/` 绝不会被误提交到 Git。

### 验收标准
- 关键词匹配单元测试（包含模式、正则模式、排除词优先级）全部通过。
- 100 条模拟账号下前后端全页面加载无报错，构建通过，交付一份简洁的 `README.md` 启动说明。