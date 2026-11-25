
# AGENTS.md — 项目开发铁律与执行规范

你正在开发一个面向 100 个账号规模的 **Telegram 矩阵运营与风控调度系统（tg-matrix-hub）**。
在编写任何一行代码前，必须完整阅读本文件、`SPEC.md` 和 `ROADMAP.md`。

## 1. 强制技术栈（严禁擅自更换）

- **后端**：Python 3.11+、FastAPI、Uvicorn、Pydantic v2
- **数据库**：PostgreSQL 16（使用 SQLAlchemy 2.0 异步模式 + `asyncpg` + `alembic`）
- **Telegram 协议层**：`Telethon` + `opentele2` + `PySocks` + `aiohttp-socks`
- **定时调度与加密**：`APScheduler`（3.x AsyncIOScheduler）、`cryptography`（Fernet 对称加密）、`psutil`
- **AI 翻译客户端**：`openai` 官方 Python SDK（配置 `base_url` 以兼容任意 OpenAI 格式大模型接口）
- **前端**：React 18 + Vite + TypeScript + Tailwind CSS + Lucide React

## 2. 核心防封与安全红线（绝对禁止违反）

以下 7 条为系统最高优先级规则，任何业务代码不得绕过：

1. **禁止直连回退（Zero Direct Fallback）**：
   - 任何账号在调用 `client.connect()` 前，**必须**先通过 `ProxyChecker` 检测该账号绑定的代理连通性。
   - 如果代理超时、认证失败或返回错误，**必须立即中止任务并将代理标为 `dead`**，绝对禁止去掉代理参数走本机直连 IP。
2. **单账号独占互斥锁（Single-Account Mutex）**：
   - 每个 `account_id` 必须拥有独立的 `asyncio.Lock`。同一时刻，一个账号只能执行一个协议操作，严禁并发操作同一个 `.session` 文件。
3. **设备指纹永久固化（Immutable Device Profile）**：
   - 账号导入时通过 `opentele2` 生成或提取设备参数并写入 `device_profiles` 表。
   - 之后每次初始化 `TelegramClient`，必须严格从数据库读取 `api_id`、`api_hash`、`device_model`、`system_version`、`app_version`、`lang_code`、`system_lang_code`。**严禁每次启动随机生成设备参数。**
4. **严格风控熔断（Circuit Breaker）**：
   - 遇到 `FloodWaitError`：立刻停止当前任务，将账号置为 `cooldown`，设置 `cooldown_until = now + e.seconds + random(30, 120)`（若 `e.seconds` 大于 1800 秒，直接冷却 24 小时）。**严禁在代码里直接 `sleep` 后继续强行重试。**
   - 遇到 `PeerFloodError`：立刻将账号置为 `restricted`，写入审计日志并推送告警。**严禁自动切换其他账号重试同一目标。**
   - 遇到 `AuthKeyUnregisteredError` 或 `UserDeactivatedBanError`：立刻标记为 `invalid` 或 `banned`，永久移出调度队列。
5. **全局并发闸门与拟人节流**：
   - 全局写操作并发必须受 `asyncio.Semaphore(6)` 限制。
   - 禁止在异步代码中使用同步阻塞的 `time.sleep()`，必须使用 `await asyncio.sleep()` 并加入随机抖动（Jitter）。
   - 写操作必须校验 `daily_action_count` 未超过 `daily_action_limit`，以及当前时间不在该账号 `timezone` 的夜间静默时段（00:00 至 07:30）。
6. **敏感信息加密**：
   - 代理密码（`password_encrypted`）与二步验证密码（`two_fa_encrypted`）入库前必须使用 `.env` 中的 `FERNET_KEY` 加密。
   - 严禁在日志、API 响应或报错堆栈中打印明文密码、API Key 或 Session 内容。
7. **合规边界**：
   - 本系统仅用于合法合规的多频道内容运营、定时发帖与关键词监控。严禁开发批量强拉成员、陌生人私信轰炸、恶意批量举报等功能。

## 3. 强制项目目录结构（严禁随意增删顶层结构）

```text
tg-matrix-hub/
├── docker-compose.yml              # 本地一键启动 PostgreSQL 16
├── .env.example                    # 环境变量模板
├── AGENTS.md
├── SPEC.md
├── ROADMAP.md
├── backend/
│   ├── requirements.txt
│   ├── alembic/                    # 数据库迁移脚本
│   ├── app/
│   │   ├── main.py                 # FastAPI 启动入口与 lifespan
│   │   ├── core/
│   │   │   ├── config.py           # Pydantic Settings 配置读取
│   │   │   ├── database.py         # AsyncEngine & AsyncSession
│   │   │   ├── security.py         # Fernet 加密解密工具
│   │   │   └── ws_manager.py       # WebSocket 实时日志与状态广播
│   │   ├── models/                 # SQLAlchemy 2.0 ORM 模型（严格对应 SPEC.md）
│   │   ├── schemas/                # Pydantic v2 请求与响应模型
│   │   ├── engine/
│   │   │   ├── proxy_checker.py    # SOCKS5/HTTP 代理强制探活
│   │   │   ├── converter.py        # 3 种导入方式（tdata/session/手机号）与指纹固化
│   │   │   ├── pool.py             # ClientPoolManager（LRU 池 + 独占锁 + 常驻监听管理）
│   │   │   ├── guard.py            # 风控熔断执行器（run_safe_account_task）
│   │   │   └── scheduler.py        # APScheduler 定时调度与每日配额清零
│   │   ├── workers/
│   │   │   ├── health_check.py     # @SpamBot 自动体检
│   │   │   ├── channel_sync.py     # 业务 1：多频道采集与 AI 翻译转发
│   │   │   ├── scheduled_post.py   # 业务 2：定时发帖排期
│   │   │   └── keyword_monitor.py  # 业务 3：关键词实时监控与告警
│   │   └── api/                    # 分模块路由（accounts, proxies, tasks, sync, posts, keywords, system）
│   └── storage/
│       ├── sessions/               # 存放 {account_uuid}.session（已加入 .gitignore）
│       ├── uploads/                # 存放发帖媒体文件与临时解压目录
│       └── temp/                   # 临时上传目录，处理完毕必须立即清理
└── frontend/                       # React + Vite + Tailwind CSS
```

## 4. 编码与排错工作纪律

- **禁止凭空猜测第三方库 API**：在使用 `opentele2` 和 `telethon` 的具体方法前，先在终端运行 `python -c "import opentele2; print(dir(opentele2))"` 检查当前安装版本的真实导出接口，确认后再写代码。
- **分步施工**：严格按 `ROADMAP.md` 的 Phase 顺序开发。每次只做当前指定的 1 个 Phase，严禁跨 Phase 提前写未要求的代码。
- **验证闭环**：每个 Phase 完成后，必须亲自在终端运行该 Phase 规定的验收测试命令（建表、启动服务、curl 或 pytest 测试），确保零报错后再向用户汇报完成。
