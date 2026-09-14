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

# Fine-grained industry sub-names (from ``stock_fund_flow_industry`` etc.) → coarse group.
# Checked first; falls back to ``INDUSTRY_GROUPS`` then "综合".
INDUSTRY_SUB_GROUPS: dict[str, str] = {
    # 金融地产
    "银行": "金融地产", "证券": "金融地产", "保险": "金融地产",
    "多元金融": "金融地产", "房地产": "金融地产",
    # 消费服务
    "白酒": "消费服务", "饮料制造": "消费服务", "食品加工制造": "消费服务",
    "白色家电": "消费服务", "黑色家电": "消费服务", "小家电": "消费服务",
    "厨卫电器": "消费服务", "服装家纺": "消费服务", "美容护理": "消费服务",
    "旅游及酒店": "消费服务", "零售": "消费服务", "贸易": "消费服务",
    "互联网电商": "消费服务", "家居用品": "消费服务", "养殖业": "消费服务",
    "农产品加工": "消费服务", "汽车整车": "消费服务", "汽车零部件": "消费服务",
    "汽车服务及其他": "消费服务", "教育": "消费服务", "其他社会服务": "消费服务",
    "种植业与林业": "消费服务",
    # 科技成长
    "软件开发": "科技成长", "计算机设备": "科技成长", "通信服务": "科技成长",
    "通信设备": "科技成长", "半导体": "科技成长", "元件": "科技成长",
    "电子化学品": "科技成长", "消费电子": "科技成长", "光学光电子": "科技成长",
    "其他电子": "科技成长", "IT服务": "科技成长", "军工电子": "科技成长",
    "军工装备": "科技成长", "文化传媒": "科技成长", "影视院线": "科技成长",
    "游戏": "科技成长",
    # 医药生物
    "化学制药": "医药生物", "中药": "医药生物", "生物制品": "医药生物",
    "医疗器械": "医药生物", "医疗服务": "医药生物", "医药商业": "医药生物",
    # 先进制造
    "通用设备": "先进制造", "专用设备": "先进制造", "自动化设备": "先进制造",
    "工程机械": "先进制造", "建筑装饰": "先进制造", "建筑材料": "先进制造",
    "轨交设备": "先进制造", "电机": "先进制造", "包装印刷": "先进制造",
    # 新能源
    "光伏设备": "新能源", "风电设备": "新能源", "电池": "新能源",
    "能源金属": "新能源", "电网设备": "新能源", "其他电源设备": "新能源",
    # 公用交运
    "电力": "公用交运", "燃气": "公用交运", "环境治理": "公用交运",
    "环保设备": "公用交运", "港口航运": "公用交运", "机场航运": "公用交运",
    "公路铁路运输": "公用交运", "物流": "公用交运",
    # 周期资源
    "煤炭开采加工": "周期资源", "油气开采及服务": "周期资源",
    "石油加工贸易": "周期资源", "工业金属": "周期资源", "贵金属": "周期资源",
    "小金属": "周期资源", "金属新材料": "周期资源", "钢铁": "周期资源",
    "化学原料": "周期资源", "化学制品": "周期资源", "化学纤维": "周期资源",
    "农化制品": "周期资源", "橡胶制品": "周期资源", "塑料制品": "周期资源",
    "非金属材料": "周期资源", "造纸": "周期资源",
    # 综合
    "综合": "综合",
}


def group_of(industry_sw: Optional[str]) -> str:
    if not industry_sw:
        return "未分类"
    return INDUSTRY_SUB_GROUPS.get(industry_sw) or INDUSTRY_GROUPS.get(industry_sw, "综合")


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
