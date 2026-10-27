# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

股票研报聚合平台 — a stock research aggregation platform for A股个股 + 指数 + 股指期货 (IF/IH/IC/IM) + 股指期权 (IO/MO/HO). FastAPI + SQLite backend ingests public data via AkShare on a schedule; a React SPA reads from the DB.

**Core invariant: the API never live-scrapes on request.** All AkShare access is isolated in `backend/app/ingestion/` (adapters + lazy `akshare_client.py`); API endpoints only read what has been ingested. Do not add AkShare/network calls to `services/` or `api/`.

Explicitly out of scope: `报告生成 (/report)` and `质控审核 (/qc)` pages.

## Commands

A bundled conda Python lives at repo-root `.conda/python.exe` (3.12); `scripts/conda.ps1` resolves it (`Enable-CondaPython`). On Windows use PowerShell for the scripts; the `python` below is that interpreter.

### Backend (run from `backend/`)

```powershell
$py = ..\.conda\python.exe        # or system python 3.11+
& $py -m pytest                       # all tests (offline — fake akshare, in-memory SQLite)
& $py -m pytest tests/test_indicators.py -q   # single file
& $py -m ruff check .                 # lint (line-length 110; E,F,I,UP,B; B008 ignored)

& $py -m uvicorn app.main:app --reload --port 8000    # API on :8000, docs at /docs

# schema + data
& $py -m app.core.db --create-all     # dev schema (alembic/versions is empty; create_all is what runs)
& $py -m app.ingestion.pipeline --feed security_master    # first-time seed
& $py -m app.ingestion.pipeline --all --universe hs300    # full first ingestion pass
& $py -m app.ingestion.pipeline --list                    # list feeds
& $py -m app.ingestion.pipeline --group daily_close       # run one frequency group
& $py -m app.ingestion.pipeline --feed price_history --universe hs300
```

### Frontend (run from `frontend/`)

```powershell
npm run dev                # Vite on :5173, proxies /api + /health → :8000
npm run build              # tsc --noEmit && vite build — this IS the type check (no ESLint configured)
npm run test               # vitest run
npx vitest run src/features/technical/__tests__/matrixView.test.ts   # single test file
```

### Both / deploy

```powershell
./scripts/dev.ps1              # backend (uvicorn) + frontend (vite) in separate windows
./scripts/deploy.ps1           # docker compose build + up (ports 19731 backend / 19732 frontend)
./scripts/backfill.ps1 -Feed price_history -Universe hs300
cd deploy; docker compose up -d --build    # compose project name "srp"
```

Default dev users: `admin/admin123`, `analyst/analyst123` (`AUTH_ENABLED=false` by default — every request acts as a hardcoded admin).

## Architecture

### Data flow (backend)

```
AkShare → adapters (retry/throttle/idempotent upsert) → SQLite → services (compute) → API ({data, meta})
                                                              ↓
                                              in-process TTL cache + pickle (prewarmed)
```

- **Adapters** (`app/ingestion/adapters/`): one module per feed, registered by name in `adapters/__init__.py` (`REGISTRY` + `BULK_ORDER` / `PER_SYMBOL_ORDER` / `FEED_GROUPS`). Add new feeds there. Per-symbol feeds iterate a resolved **universe** (`ingestion/universe.py`: hs300 / zz500 / all / explicit codes). Each run writes `IngestionLog` + `DataFreshness` rows so staleness is visible in the UI.
- **Scheduler** (`ingestion/scheduler.py`): one APScheduler cron job per `FEED_GROUPS` entry (intraday / daily_close / daily_evening / weekly_master / weekly_financials / news_refresh), Asia/Shanghai, crons overridable via `SCHEDULER_CRON_*`. Jobs run in worker threads behind a **global ingest lock**; the news cron is deliberately offset to :02/:22/:42 off intraday's */10 grid because same-second collisions starve the loser. Startup bootstrap (`INGEST_BOOTSTRAP`) seeds an empty DB and catches up stale daily groups.
- **Derived read models**: `Signal`, `AccuracySnapshot`, `WeeklyStat` are *not* ingested — `services/derived.py::refresh_derived` recomputes them from `research_report`/`DailyQuote`. It runs after the `daily_evening` group, `--all` runs, and bootstrap. If you ingest reports manually via a single feed, run the derived refresh or the 信号/准确率/周统计 pages go stale.
- **Services** (`app/services/`): pure compute. `indicators.py` implements 42 TA indicators in raw numpy/pandas (no TA-Lib; formulas follow 通达信 definitions, e.g. `_sma_cn` = EWM alpha=M/N). Indicators are computed **on demand only for what the page requested**. `signal_matrix.py` treats 弃权/无数据 as excluded-from-denominator, distinct from 中性.
- **Cache** (`core/cache.py`): in-process TTL + pickle file, no Redis. Heavy endpoints (全市场速览, 技术信号矩阵, 板块联动) cache computed payloads; `services/prewarm.py` warms the default parameter sets at boot and after each ingestion.
- **API** (`app/api/v1/endpoints/`): every read endpoint returns the `{"data": ..., "meta": {...}}` envelope from `api/common.py` (`envelope` / `paged`); `meta` carries pagination + data freshness ("新鲜度"). Routers are aggregated in `api/v1/router.py`.
- **SSE** (`app/sse/bus.py`): thread-safe event bus; worker-thread ingestion publishes to the asyncio loop bound in `main.py` lifespan.
- **MCP outlet** (`app/mcp/`): read-only tools at `/mcp` (Streamable HTTP) for external AI clients, gated by `FEATURE_MCP`. Tools are pure functions in `mcp/tools.py`; mounting happens in `main.py` **before** the SPA catch-all and must never block boot. Ops check: `GET /api/ops/mcp`.
- **Config** (`core/config.py`): every tunable is a pydantic-settings field read from env / `backend/.env` — don't hard-code values elsewhere.

### Frontend

- React 18 + Vite + TS, antd v5, ECharts 5, TanStack Query v5, Zustand, React Router v6. `@` alias → `src/`.
- Organized by **feature folders** (`src/features/<domain>/`), each owning its page + panels; shared charts/UI in `src/components/`, API access via `src/api/client.ts` (`getData<T>` / `getEnvelope<T>` unwrap the backend envelope).
- Pages are lazy-loaded from `src/router/index.tsx`; login is removed — no auth guards.
- Data provenance is a UI requirement: show source attribution + freshness (`FreshnessBadge` / `ProvenanceTag`), not just values.

## Conventions

- Comments, docstrings, log messages, and UI copy are Chinese (mixed with English); keep new code consistent.
- Commit style: conventional commits with Chinese subjects, e.g. `feat(insights): 研报洞察页 — 情绪分歧度/信号复盘/龙虎榜联动`, `fix(scheduler): ...`.
- Backend Python ≥3.11, ruff line-length 110, `from __future__ import annotations` at top of modules.
- `data/` is gitignored (dev SQLite + caches); repo root accumulates transient `*.log`/`*.png` artifacts that are ignored too.
