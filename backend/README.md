# Backend — 股票研报聚合平台

FastAPI + SQLAlchemy 2.0 + APScheduler. All external data comes from **AkShare**
(东方财富 / 新浪 / 巨潮 / 交易所) via isolated adapters that ingest into the DB on a
schedule. **The API never live-scrapes on request.**

## Layout

```
app/
├─ main.py               # FastAPI app + lifespan (db init, scheduler, SSE loop)
├─ core/                 # config, db, logging, cache, security(JWT), bootstrap
├─ models/               # SQLAlchemy ORM (security, market, research, financial, flow, system)
├─ schemas/              # Pydantic DTOs (auth, ...)
├─ ingestion/            # adapters (only place akshare is imported), throttle, universe,
│                        #   normalizers, db_utils(bulk_upsert), scheduler, pipeline(CLI)
├─ services/             # indicators(numpy/pandas TA), aggregation, quotes, period,
│                        #   signals/accuracy/basis (Phase 2)
├─ sse/                  # thread-safe event bus
├─ ai/                   # RESERVED Phase 3 (feature-flagged stubs)
└─ api/v1/endpoints/     # health, meta, market, research, quant, financials, stock,
                         #   stream(SSE), ops, auth, chat(reserved)
```

## Setup

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"          # or: pip install -r requirements.txt
copy .env.example .env
python -m app.core.db --create-all       # dev schema (or: alembic upgrade head)
python -m app.ingestion.pipeline --feed security_master
python -m app.ingestion.pipeline --all --universe hs300
uvicorn app.main:app --reload --port 8000
```

- API docs: http://localhost:8000/docs
- Deep health: http://localhost:8000/health/deep
- Default seeded users (dev): `admin / admin123`, `analyst / analyst123`
  (override with `DEFAULT_ADMIN_PASSWORD`).

## Ingestion CLI

```powershell
python -m app.ingestion.pipeline --list                     # list feeds
python -m app.ingestion.pipeline --resolve-universe hs300   # show universe codes
python -m app.ingestion.pipeline --bulk                     # bulk feeds
python -m app.ingestion.pipeline --feed ratings_daily --date 2026-09-10
python -m app.ingestion.pipeline --per-symbol --universe hs300
python -m app.ingestion.pipeline --all --universe hs300
```

## Feeds

| Feed | AkShare interface | Type |
|---|---|---|
| security_master | stock_info_a_code_name | bulk |
| industry_boards | stock_board_industry_name_em | bulk |
| industry_constituents | stock_board_industry_cons_em | bulk(loop) |
| spot_snapshot | stock_zh_a_spot_em | bulk |
| index_daily | stock_zh_index_daily | bulk(loop) |
| ratings_daily | stock_rank_forecast_cninfo | bulk(by date) |
| recommend_pool | stock_institute_recommend | bulk |
| earnings | stock_yjbb_em | bulk(by quarter) |
| price_history | stock_zh_a_hist | per-symbol |
| research_reports | stock_research_report_em | per-symbol |
| fin_indicators | stock_financial_analysis_indicator | per-symbol |
| financials_em | stock_{balance,profit,cash_flow}_sheet_by_report_em | per-symbol |
| disclosures | stock_notice_report | bulk(by date) |

Phase 2 adds: index_futures (get_futures_daily/CFFEX), index_options (option_finance_board),
flow feeds (northbound/margin/lhb/individual).

## Tests

```powershell
pytest                       # adapters run against a FAKE akshare (no network)
pytest tests/test_indicators.py -q
```

## Notes / risk controls

- **akshare is imported lazily** (`ingestion/akshare_client.py`); the API boots even if it's
  missing, and `/health/deep` reports the dependency status.
- Every adapter is wrapped with retry/backoff, throttling, idempotent upserts, and writes
  `IngestionLog` + `DataFreshness` so stale feeds are visible in the UI.
- Indicators are pure numpy/pandas (no TA-Lib) to avoid Windows native-build issues.
