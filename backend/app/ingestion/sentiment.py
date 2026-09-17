"""规则化 情绪打分 for flash news (no LLM — matches the platform's rule-based philosophy).

Weighted keyword lexicon; ``classify`` returns ``(label, score)`` where label is
利好/中性/利空. The interface is intentionally swappable for an LLM classifier
later (same signature). Terms are kept unambiguous on purpose — ambiguous words
(e.g. 波动, 关注) are excluded to bound false signals.
"""
from __future__ import annotations

from app.ingestion.normalizers import clean_text

#: keyword -> weight. 3 = strong direct event, 2 = clear signal, 1 = supportive.
POSITIVE: dict[str, int] = {
    "涨停": 3, "大涨": 2, "涨停板": 3, "飙升": 2, "创新高": 2, "超预期": 2,
    "扭亏": 2, "中标": 2, "获批": 2, "回购": 2, "增持": 2, "上调": 2,
    "预增": 2, "利好": 2, "签约": 1, "合作": 1, "突破": 1, "涨价": 1,
    "降准": 2, "降息": 2, "回暖": 1, "加码": 1,
}
NEGATIVE: dict[str, int] = {
    "跌停": 3, "大跌": 2, "跌停板": 3, "暴跌": 3, "创新低": 2, "亏损": 2,
    "爆雷": 3, "违约": 2, "退市": 3, "立案": 3, "处罚": 2, "下调": 2,
    "减持": 2, "利空": 2, "预亏": 2, "商誉减值": 2, "冻结": 1, "停牌": 1,
    "解禁": 1, "加息": 2, "承压": 1, "风险警示": 2,
}

NEUTRAL = "中性"
BULLISH = "利好"
BEARISH = "利空"


def classify(text: str) -> tuple[str, float]:
    """Return ``(label, score)`` for ``text``.

    score > 0 → 利好, score < 0 → 利空, == 0 → 中性. The score is the weighted
    sum of lexicon hits (positive keys add, negative keys subtract).
    """
    s = clean_text(text, "") or ""
    if not s:
        return NEUTRAL, 0.0
    score = 0
    for word, weight in POSITIVE.items():
        if word in s:
            score += weight
    for word, weight in NEGATIVE.items():
        if word in s:
            score -= weight
    if score > 0:
        return BULLISH, float(score)
    if score < 0:
        return BEARISH, float(score)
    return NEUTRAL, 0.0
