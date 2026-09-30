"""FastMCP server — registers every read-only tool and exposes a mountable ASGI app.

``mcp_asgi()`` builds the streamable-HTTP app (wrapped in the static-token
middleware) for ``main.py`` to mount at ``settings.mcp_path``; ``mcp_lifespan()``
enters the session manager from the FastAPI lifespan (a mounted sub-app's own
lifespan never runs, so the parent must drive it — FastMCP's ``session_manager``
also requires ``streamable_http_app()`` to have been called first). The ``mcp``
package is imported lazily so the main app keeps working without it when
FEATURE_MCP=false.

Tool wrappers are ``async`` and offload the blocking service calls to the worker
threadpool (``anyio.to_thread``) — FastMCP executes *sync* tools directly on the
event loop, which would stall the whole API on a slow aggregation.

Transport security: FastMCP enables DNS-rebinding protection with a localhost
allow-list by default. Port-less localhost variants are always added (nginx
forwards ``Host: localhost`` without the port, which the SDK default patterns
``localhost:*`` would reject), and ``MCP_ALLOWED_HOSTS`` (comma-separated)
extends the allow-list for LAN/domain deployments.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from functools import partial
from typing import Any

import anyio

from app.core.config import settings
from app.core.db import SessionLocal
from app.mcp import tools
from app.mcp.auth import TokenAuthMiddleware

_server: Any | None = None


def _call_sync(fn: Callable[..., dict], args: tuple, kwargs: dict) -> dict:
    with SessionLocal() as db:
        return fn(db, *args, **kwargs)


async def _call(fn: Callable[..., dict], *args: Any, **kwargs: Any) -> dict:
    """Run a sync tool function off the event loop (worker threadpool)."""
    return await anyio.to_thread.run_sync(partial(_call_sync, fn, args, kwargs))


def _configure_transport_security(mcp: Any) -> None:
    sec = mcp.settings.transport_security
    if sec is None:
        return
    # Port-less localhost variants: nginx forwards "Host: localhost" (no port),
    # which the SDK defaults ("localhost:*") would reject.
    sec.allowed_hosts = list(sec.allowed_hosts) + ["localhost", "127.0.0.1", "[::1]"]
    extra = [h.strip() for h in settings.mcp_allowed_hosts.split(",") if h.strip()]
    if extra:
        sec.allowed_hosts += extra
        sec.allowed_origins += [
            f"{scheme}://{host}"
            for host in extra
            if not host.endswith(":*")
            for scheme in ("http", "https")
        ]
    mcp.settings.transport_security = sec


def build_server() -> Any:
    """Build (once) the FastMCP instance with every read-only tool registered."""
    global _server
    if _server is not None:
        return _server

    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        "srp-terminal",
        instructions=(
            "股票研报聚合平台 (A股研报/评级/行情/技术指标/衍生品/资金) 只读数据工具。"
            "Read-only A-share research & market data tools."
        ),
        stateless_http=True,
    )
    # Internal route at "/" so the public URL is exactly <host><mcp_path>/ —
    # avoids the /mcp/mcp double prefix when mounted under "/mcp".
    mcp.settings.streamable_http_path = "/"
    _configure_transport_security(mcp)

    @mcp.tool()
    async def market_dashboard() -> dict:
        """市场看板: 指数行情/板块热力图/评级变动/最新研报 (最近一周窗口)."""
        return await _call(tools.market_dashboard)

    @mcp.tool()
    async def stock_snapshot(code: str) -> dict:
        """个股快照: 行情+财务指标+最新研报+评级+资金流. code 如 600519 / sh000300."""
        return await _call(tools.stock_snapshot, code)

    @mcp.tool()
    async def search_reports(
        keyword: str | None = None,
        code: str | None = None,
        org: str | None = None,
        industry: str | None = None,
        rating: str | None = None,
        start: str | None = None,
        end: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> dict:
        """研报库检索: 标题/名称关键词、机构、行业、评级、代码、YYYY-MM-DD 日期范围."""
        return await _call(
            tools.search_reports, keyword=keyword, code=code, org=org,
            industry=industry, rating=rating, start=start, end=end, page=page, size=size,
        )

    @mcp.tool()
    async def technical_series(
        code: str,
        period: str = "1y",
        indicators: str | None = None,
        freq: str = "daily",
        params: str | None = None,
    ) -> dict:
        """技术指标序列 (ECharts-ready). period: 6m|1y|2y|3y|5y; freq: daily|weekly|monthly;
        indicators: 逗号分隔 (ma,macd,kdj,rsi,boll...); params: 指标参数覆盖, 如 "ma=5,10,20"."""
        return await _call(tools.technical_series, code, period=period, indicators=indicators,
                           freq=freq, params=params)

    @mcp.tool()
    async def indicator_catalog(group: str | None = None) -> dict:
        """技术指标目录: 每项指标的中文名/分类/主图副图/公式说明/默认参数;
        group 过滤: 趋势|震荡|动量|量价|波动|衍生品."""
        return tools.indicator_catalog(group)

    @mcp.tool()
    async def signal_matrix(
        scope: str = "index",
        columns: str | None = None,
        freq: str = "daily",
        limit: int = 60,
    ) -> dict:
        """技术信号矩阵: 品种 × 指标的 偏多/偏空/中性/弃权 表决 + 净方向排序.
        scope: index(宽基)|index+all(含行业)|etf|bond|stock|all; columns: 逗号分隔列 key."""
        return await _call(tools.signal_matrix, scope=scope, columns=columns, freq=freq,
                           limit=limit)

    @mcp.tool()
    async def market_matrix(scope: str = "index+active", limit: int = 60) -> dict:
        """全市场速览: 指数(+活跃个股) 技术快照矩阵 (trend/MA20/MACD/RSI 状态)."""
        return await _call(tools.market_matrix, scope=scope, limit=limit)

    @mcp.tool()
    async def list_signals(
        kind: str | None = None,
        days: int = 30,
        industry: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> dict:
        """可操作信号: kind=upgrade|downgrade|first|consensus; days 时间窗; industry 行业组过滤."""
        return await _call(tools.list_signals, kind=kind, days=days, industry=industry, page=page, size=size)

    @mcp.tool()
    async def accuracy_leaderboard(
        horizon: int = 20, by: str = "org", min_events: int = 5, limit: int = 50
    ) -> dict:
        """研报准确率排行: 相对沪深300 的 hit-rate & net-skill; horizon=20|60; by=org|analyst."""
        return await _call(
            tools.accuracy_leaderboard, horizon=horizon, by=by, min_events=min_events, limit=limit
        )

    @mcp.tool()
    async def basis_overview(variety: str | None = None) -> dict:
        """股指期货基差: 期限结构 + 最新基差快照; variety=IF|IH|IC|IM."""
        return await _call(tools.basis_overview, variety=variety)

    @mcp.tool()
    async def options_overview() -> dict:
        """股指期权概览: 各标的 PCR/成交/持仓汇总 (IO/MO/HO 系列)."""
        return await _call(tools.options_overview)

    @mcp.tool()
    async def flow_overview(kind: str = "northbound", days: int = 30) -> dict:
        """资金流向: kind=northbound(沪深港通) | margin(两融) | lhb(龙虎榜)."""
        return await _call(tools.flow_overview, kind=kind, days=days)

    @mcp.tool()
    async def linkage_overview(window: int = 120) -> dict:
        """板块/指数联动: 指数收益相关性矩阵 + 个股 beta (vs 沪深300, 滚动窗口)."""
        return await _call(tools.linkage_overview, window=window)

    @mcp.tool()
    async def financial_summary(code: str, statement: str = "income", limit: int = 12) -> dict:
        """财务摘要: 三大报表期序列 (statement=balance|income|cashflow) + 关键财务指标."""
        return await _call(tools.financial_summary, code, statement=statement, limit=limit)

    @mcp.tool()
    async def list_news(
        q: str | None = None,
        sentiment: str | None = None,
        source: str | None = None,
        days: int = 1,
        page: int = 1,
        size: int = 50,
    ) -> dict:
        """资讯舆情快讯: 关键词 / 情绪(利好|中性|利空) / 来源(em|cls) 过滤, 近 days 天 (默认当日)."""
        return await _call(
            tools.list_news, q=q, sentiment=sentiment, source=source, days=days, page=page, size=size
        )

    _server = mcp
    return mcp


def mcp_asgi() -> Any:
    """Mountable ASGI app: streamable HTTP wrapped in the static-token middleware."""
    return TokenAuthMiddleware(build_server().streamable_http_app())


@asynccontextmanager
async def mcp_lifespan() -> AsyncIterator[None]:
    """Run the streamable-HTTP session manager (driven by the FastAPI lifespan)."""
    server = build_server()
    async with server.session_manager.run():
        yield
