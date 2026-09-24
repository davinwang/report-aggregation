"""Import all models so they register on ``Base.metadata``.

Alembic's ``env.py`` and ``init_db()`` import this package; every table must be
imported here or it won't be created/migrated.
"""
from app.models.base import (
    Base,
    RatingDirection,
    SecurityType,
    StatementType,
    TimestampMixin,
    utcnow,
)
from app.models.financial import (
    Disclosure,
    EarningsReport,
    FinancialIndicator,
    FinancialStatement,
)
from app.models.flow import FundFlowDaily, LhbRecord, MarginData, NorthboundDaily
from app.models.market import DailyQuote, IndexFutureDaily, OptionQuote
from app.models.news import NewsItem
from app.models.research import (
    AccuracySnapshot,
    PeerActivity,
    RatingEvent,
    RecommendPool,
    ResearchReport,
    Signal,
    WeeklyStat,
)
from app.models.security import (
    INDUSTRY_GROUPS,
    IndustryBoard,
    IndustryConstituent,
    Security,
    group_of,
)
from app.models.system import AiSynthesis, DataFreshness, IngestionLog, User

__all__ = [
    "Base",
    "utcnow",
    "TimestampMixin",
    "SecurityType",
    "StatementType",
    "RatingDirection",
    # security
    "Security",
    "IndustryBoard",
    "IndustryConstituent",
    "INDUSTRY_GROUPS",
    "group_of",
    # market
    "DailyQuote",
    "IndexFutureDaily",
    "OptionQuote",
    # research
    "ResearchReport",
    "RatingEvent",
    "Signal",
    "RecommendPool",
    "AccuracySnapshot",
    "WeeklyStat",
    "PeerActivity",
    # financial
    "FinancialStatement",
    "FinancialIndicator",
    "EarningsReport",
    "Disclosure",
    # flow
    "FundFlowDaily",
    "NorthboundDaily",
    "MarginData",
    "LhbRecord",
    # news
    "NewsItem",
    # system
    "User",
    "IngestionLog",
    "DataFreshness",
    "AiSynthesis",
]
