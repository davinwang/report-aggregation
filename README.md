# 股票研报聚合平台 (Stock Research Aggregation Platform)

A stock-investment research aggregation platform inspired by the 国泰君安期货·研报聚合平台,
rebuilt for **A股个股 + 指数 + 股指期货 (IF/IH/IC/IM) + 股指期权 (IO/MO/HO)**.

Data is sourced from **public feeds** via [AkShare](https://akshare.akfamily.xyz/) (东方财富 /
新浪财经 / 巨潮资讯 / 交易所), ingested into a local database on a schedule. The UI never
live-scrapes on request — it reads from the DB.

> **Not investment advice.** All data is aggregated from public sources for research only.
> Source attribution and data dates ("新鲜度") are shown throughout the UI.

---

## Feature scope

Included (stock-transformed): 市场看板 · 研报库 · 技术指标(K线) · 财务数据 · 个股详情 ·
功能导航 (Phase 1); 全市场速览 · 可操作信号 · 研报准确率 · 周统计 · 股指期货基差 · 股指期权 ·
资金流向 · 板块/指数联动 · 资讯舆情 · 登录/管理/运营/上传 (Phase 2); AI综合研判 · AI助手 (Phase 3, feature-flagged).

**Explicitly removed** vs. the reference platform: `报告生成 (/report)` and `质控审核 (/qc)`.

---

## Tech stack

- **Frontend:** React 18 · Vite · TypeScript · Ant Design v5 · ECharts 5 · TanStack Query v5 · Zustand · React Router v6
- **Backend:** Python 3.11+ · FastAPI · SQLAlchemy 2.0 · Alembic · APScheduler · akshare · pandas/numpy · uvicorn
- **DB:** SQLite (WAL mode, zero-config)
- **Cache:** in-process TTL + pickle file (no Redis)
- **Realtime:** SSE (`/api/stream`)

---

## Repository layout

```
report-aggreation/
─ backend/     # FastAPI app, ingestion adapters, indicator engine, services, API
├─ frontend/    # React SPA
├─ deploy/      # docker-compose.yml + Dockerfiles (SQLite-only stack)
├─ data/        # sqlite dev db + caches (gitignored)
└─ scripts/     # dev / seed / backfill helpers (PowerShell)
```

See `backend/README.md` and `frontend/README.md` for details.

---

## Prerequisites

- **Node.js** ≥ 18 (tested with v22)
- **Python** ≥ 3.11 (backend)

---

## Quick start

### 1) Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"          # or: pip install -r requirements.txt
copy .env.example .env           # then edit DATABASE_URL / secrets as needed

# create schema
alembic upgrade head             # or: python -m app.core.db --create-all

# seed the default universe (沪深300) + first ingestion pass
python -m app.ingestion.pipeline --feed security_master
python -m app.ingestion.pipeline --all --universe hs300

# run API
uvicorn app.main:app --reload --port 8000
```

Health probe: `http://localhost:8000/health/deep` · API docs: `http://localhost:8000/docs`

### 2) Frontend

```powershell
cd frontend
npm install
npm run dev                      # http://localhost:5173 (proxies /api → :8000)
```

### 3) Both together

```powershell
./scripts/dev.ps1                # starts backend (if python present) + frontend
```

---

## Data ingestion

Adapters wrap AkShare interfaces (isolated in `backend/app/ingestion/adapters/`), each with
retry/backoff, throttling, idempotent upserts, and freshness stamping. Bulk daily feeds run
after market close; per-symbol feeds are limited to a configurable **universe**.

```powershell
python -m app.ingestion.pipeline --feed ratings_daily --date 2026-09-10
python -m app.ingestion.pipeline --feed price_history --universe hs300
```

## MCP 接入（AI 客户端）

`FEATURE_MCP=true`（compose 默认开启）时，后端在**同进程**挂载一个只读 MCP
（Streamable HTTP）端点，把看板/个股/研报/指标/信号/资金等能力开放给 Claude Code、
Cursor 等外部 AI 客户端，无需另起服务：

- 直连后端：`http://localhost:19731/mcp/`
- 经 nginx：`http://localhost:19732/mcp/`

鉴权：设置 `MCP_TOKEN` 后要求 `Authorization: Bearer <token>`；留空则免鉴权（内网
自托管默认，启动日志会告警）。传输层启用 DNS-rebinding 防护，默认仅放行
localhost；局域网/域名部署用 `MCP_ALLOWED_HOSTS`（逗号分隔）追加允许的 Host。

Claude Code：

```powershell
claude mcp add --transport http srp http://localhost:19731/mcp/ `
  --header "Authorization: Bearer $MCP_TOKEN"
```

通用客户端 JSON：

```json
{
  "mcpServers": {
    "srp": {
      "type": "http",
      "url": "http://localhost:19731/mcp/",
      "headers": { "Authorization": "Bearer <MCP_TOKEN>" }
    }
  }
}
```

工具清单（13 个，全部只读，实现见 `backend/app/mcp/tools.py`）：

| 工具 | 说明 |
|---|---|
| market_dashboard | 市场看板（指数/板块热力/评级汇总/最新研报） |
| stock_snapshot | 个股快照（行情+财务指标+研报+评级+资金） |
| search_reports | 研报库检索（关键词/机构/行业/评级/日期） |
| technical_series | 技术指标序列（MA/MACD/KDJ/RSI/BOLL…） |
| market_matrix | 全市场速览矩阵 |
| list_signals | 可操作信号 |
| accuracy_leaderboard | 研报准确率排行 |
| basis_overview | 股指期货基差（期限结构+快照） |
| options_overview | 股指期权概览（PCR/成交/持仓） |
| flow_overview | 资金流向（北向/两融/龙虎榜） |
| linkage_overview | 板块/指数联动（相关性+beta） |
| financial_summary | 财务摘要（三大报表+指标） |
| list_news | 资讯舆情快讯（情绪/来源过滤） |

运维核对：`GET /api/ops/mcp` 返回 `{enabled, path, token_required, tools, client_hint}`。

> 回退方案：若同进程挂载与运行环境不兼容（如 FastMCP SDK API 漂移），可改用独立
> 进程承载 `app/mcp/server.py` 构建的 ASGI app（第二端口/容器），工具实现与鉴权
> 中间件完全复用；本期未实现。

## Testing

```powershell
cd backend; pytest            # adapters are tested against mocked AkShare frames (no network)
cd frontend; npm run test     # Vitest + RTL; npm run e2e for Playwright smoke
```
