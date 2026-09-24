"""recommend_pool — bulk 机构推荐池 via sina → ``RecommendPool`` rows.

Three pools (上调评级股票 / 下调评级股票 / 首次评级股票), one whole-market HTTP
call each.

Note: akshare's ``stock_institute_recommend`` is broken on modern pandas
(``pd.read_html(str)`` treats the HTML string as a filename), which is why this
feed always errored and the pool stayed empty. We fetch the same sina endpoints
ourselves (httpx + ``pd.read_html(BytesIO)``) — see the pool URL map, whose
hrefs are verified against the ``leftMenu`` of
``vIR_RatingNewest/index.phtml``.
"""
from __future__ import annotations

import io
from datetime import date
from typing import Any

import httpx
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.ingestion import throttle
from app.ingestion.base import BaseAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import clean_text, norm_code, norm_rating, to_date, to_float
from app.ingestion.secmap import industry_group_map, security_id_map
from app.models.base import RatingDirection
from app.models.research import RecommendPool
from app.models.security import group_of

logger = get_logger(__name__)

_BASE = "http://stock.finance.sina.com.cn/stock/go.php"
# sina pool page name -> (model kind, page path). Paths verified against the
# leftMenu links of vIR_RatingNewest/index.phtml (same endpoints akshare uses).
POOLS: dict[str, tuple[str, str]] = {
    "上调评级股票": ("upgrade", f"{_BASE}/vIR_RatingUp/index.phtml"),
    "下调评级股票": ("downgrade", f"{_BASE}/vIR_RatingDown/index.phtml"),
    "首次评级股票": ("first", f"{_BASE}/vIR_RatingFirst/index.phtml"),
}

_UP_STRENGTH = {RatingDirection.buy: "强", RatingDirection.overweight: "中"}
_DOWN_STRENGTH = {RatingDirection.sell: "强", RatingDirection.underweight: "中"}


def _strength(kind: str, direction: RatingDirection) -> str:
    table = _DOWN_STRENGTH if kind == "downgrade" else _UP_STRENGTH
    return table.get(direction, "中")


def fetch_pool(url: str) -> pd.DataFrame:
    """GET one sina pool page → DataFrame (first table, sort-arrow columns renamed)."""
    r = httpx.get(url, params={"num": "10000", "p": "1"}, timeout=30.0, follow_redirects=True)
    r.raise_for_status()
    # Bytes → pandas/lxml honors the page's GBK meta charset (r.text may not).
    df = pd.read_html(io.BytesIO(r.content), header=0)[0]
    df = df.rename(columns={c: str(c).rstrip("↓").strip() for c in df.columns if str(c).endswith("↓")})
    return df


def _pool_code(v: Any) -> str | None:
    """Sina returns 股票代码 as int (1328 → 001328); tolerate float/str variants."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, float):
        v = int(v)
    code = norm_code(v) or ""
    if code.endswith(".0") and code[:-2].isdigit():
        code = code[:-2]
    if code.isdigit() and len(code) <= 6:
        return code.zfill(6)
    return None


class RecommendPoolAdapter(BaseAdapter):
    name = "recommend_pool"
    description = "新浪-机构推荐池 (上调/下调/首次评级) → recommend_pool"

    def fetch(self, pools: list[str] | None = None, **kwargs) -> list[tuple[str, pd.DataFrame]]:
        out: list[tuple[str, pd.DataFrame]] = []
        for pool_name, (kind, url) in POOLS.items():
            if pools and pool_name not in pools and kind not in pools:
                continue
            throttle.default_throttle.wait()
            try:
                out.append((kind, fetch_pool(url)))
            except Exception as exc:  # noqa: BLE001 - one broken pool must not kill the rest
                logger.warning("[recommend_pool] %s failed: %s", pool_name, exc)
        if not out:
            raise RuntimeError("all sina recommend pools failed")
        return out

    def normalize(self, raw: Any, trade_date: date | None = None, **kwargs) -> list[dict[str, Any]]:
        today = trade_date or date.today()
        rows: list[dict[str, Any]] = []
        for kind, df in raw or []:
            for r in records(df):
                code = _pool_code(get(r, "股票代码", "代码", "证券代码"))
                if not code:
                    continue
                rating = clean_text(get(r, "最新评级", "综合评级", "投资评级", "评级"))
                direction = norm_rating(rating)
                org = clean_text(get(r, "评级机构", "机构", "研究机构"))
                # sina marks the sort column with a trailing arrow (评级日期↓).
                d = to_date(get(r, "评级日期", "评级日期↓", "日期")) or today
                rows.append(
                    {
                        "code": code,
                        "name": clean_text(get(r, "股票名称", "证券简称", "名称")),
                        "trade_date": d,
                        "kind": kind,
                        "rating": rating,
                        "direction": direction.value,  # 买入/增持/... — matches Signal.direction
                        "strength": _strength(kind, direction),
                        "org": org,
                        "analysts": clean_text(get(r, "分析师", "研究员")),
                        "target_price": to_float(get(r, "目标价", "平均目标价")),
                        "industry": clean_text(get(r, "行业")),
                        "source": "sina",
                        "sources_json": [{"pool": kind, "rating": rating, "org": org}],
                    }
                )
        return rows

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        codes = [r["code"] for r in rows]
        id_map = security_id_map(session, codes)
        grp_map = industry_group_map(session, codes)
        for r in rows:
            r["security_id"] = id_map.get(r["code"])
            r["industry_group"] = grp_map.get(r["code"]) or group_of(r.get("industry"))
        scope = select(RecommendPool).where(RecommendPool.code.in_(list(dict.fromkeys(codes))))
        return bulk_upsert(
            session, RecommendPool, rows,
            key_fields=["code", "trade_date", "kind"], scope=scope,
        )


adapter = RecommendPoolAdapter()
