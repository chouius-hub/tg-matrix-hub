# TG Matrix Hub — Telegram 矩阵运营与风控调度系统

面向 100 账号规模的 Telegram 矩阵运营、防封调度与实时监控平台。

## 1. 环境准备

- **Docker Desktop**（运行 PostgreSQL 16）
- **Python 3.11+**
- **Node.js 20+**（用于前端构建与开发）

## 2. 快速启动步骤

### 第一步：配置环境变量
复制根目录下的 `.env.example` 为 `.env` 并填入必要配置：
- `DATABASE_URL`：PostgreSQL 16 异步连接串（默认匹配 `docker-compose.yml`）
- `FERNET_KEY`：执行以下命令生成对称加密密钥：
  ```powershell
  backend\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- `AI_API_BASE`、`AI_API_KEY`、`AI_MODEL`：OpenAI 兼容大模型接口配置（用于多频道 AI 翻译转发）

### 第二步：启动 PostgreSQL 16 并执行建表
```powershell
docker compose up -d
cd backend
.\.venv\Scripts\alembic.exe upgrade head
```

### 第三步：启动后端服务
```powershell
cd backend
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
```
- 接口文档（Swagger）：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/health`

### 第四步：启动前端控制台
```powershell
cd frontend
npm.cmd install
npm.cmd run dev -- --port 5173
```
浏览器访问 `http://127.0.0.1:5173`。

## 3. 运行测试
```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests -v
cd frontend; npm.cmd run build
```

