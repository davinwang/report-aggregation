"""Security master + industry classification.

A ``Security`` is any tradable/quotable instrument: A股个股, 指数, 股指期货, 股指期权.
Industry uses 申万一级 (``industry_sw``) plus a coarse sidebar group (``industry_group``).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import Boolean, Date, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# Coarse sidebar groups (transform of futures 板块) mapping over 申万一级 industries.
INDUSTRY_GROUPS: dict[str, str] = {
    "银行": "金融地产", "非银金融": "金融地产", "房地产": "金融地产",
    "食品饮料": "消费服务", "商贸零售": "消费服务", "社会服务": "消费服务",
    "纺织服饰": "消费服务", "轻工制造": "消费服务", "美容护理": "消费服务",
    "农林牧渔": "消费服务", "家用电器": "消费服务", "汽车": "消费服务",
    "电子": "科技成长", "计算机": "科技成长", "通信": "科技成长", "传媒": "科技成长",
    "国防军工": "科技成长",
    "医药生物": "医药生物",
    "机械设备": "先进制造", "电力设备": "新能源", "公用事业": "公用交运",
    "交通运输": "公用交运", "环保": "公用交运", "建筑装饰": "先进制造",
    "建筑材料": "周期资源", "钢铁": "周期资源", "有色金属": "周期资源",
    "煤炭": "周期资源", "石油石化": "周期资源", "基础化工": "周期资源",
    "综合": "综合",
}


def group_of(industry_sw: Optional[str]) -> str:
    if not industry_sw:
        return "未分类"
    return INDUSTRY_GROUPS.get(industry_sw, "综合")


class Security(Base, TimestampMixin):
    __tablename__ = "security"
    __table_args__ = (UniqueConstraint("code", name="uq_security_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16), index=True)          # e.g. "600519", "000300", "IF2412"
    name: Mapped[str] = mapped_column(String(64), default="")
    type: Mapped[str] = mapped_column(String(16), default="stock", index=True)  # stock|index|future|option
    exchange: Mapped[str] = mapped_column(String(16), default="")      # SSE|SZSE|BSE|CFFEX|...
    industry_sw: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)   # 申万一级
    industry_group: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    list_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Security {self.code} {self.name} {self.type}>"


class IndustryBoard(Base, TimestampMixin):
    """东财/申万行业板块 (``stock_board_industry_name_em``)."""

    __tablename__ = "industry_board"
    __table_args__ = (UniqueConstraint("name", "source", name="uq_industry_board_name_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="em")      # em|sw
    group: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    change_pct: Mapped[Optional[float]] = mapped_column(nullable=True)  # latest board move
    turnover: Mapped[Optional[float]] = mapped_column(nullable=True)
    company_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class IndustryConstituent(Base):
    """Membership of a security in an industry board (``stock_board_industry_cons_em``)."""

    __tablename__ = "industry_constituent"
    __table_args__ = (
        UniqueConstraint("board_name", "code", name="uq_ind_const_board_code"),
        Index("ix_ind_const_code", "code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    board_name: Mapped[str] = mapped_column(String(64))
    code: Mapped[str] = mapped_column(String(16))
    name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
