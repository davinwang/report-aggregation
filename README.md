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
资金流向 · 板块/指数联动 · 登录/管理/运营/上传 (Phase 2); AI综合研判 · AI助手 (Phase 3, feature-flagged).

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

## Testing

```powershell
cd backend; pytest            # adapters are tested against mocked AkShare frames (no network)
cd frontend; npm run test     # Vitest + RTL; npm run e2e for Playwright smoke
```
