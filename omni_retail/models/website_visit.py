import enum
from datetime import date

from sqlalchemy import Date, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from omni_retail.database import Base


class TrafficSource(str, enum.Enum):
    ORGANIC_SEARCH = "organic_search"
    PAID_SEARCH = "paid_search"
    SOCIAL = "social"
    EMAIL = "email"
    DIRECT = "direct"
    REFERRAL = "referral"


class Device(str, enum.Enum):
    DESKTOP = "desktop"
    MOBILE = "mobile"
    TABLET = "tablet"


class WebsiteVisit(Base):
    """One row per (date, traffic_source, device) combination."""

    __tablename__ = "website_visits"

    id: Mapped[int] = mapped_column(primary_key=True)
    visit_date: Mapped[date] = mapped_column(Date)
    traffic_source: Mapped[TrafficSource] = mapped_column(Enum(TrafficSource))
    device: Mapped[Device] = mapped_column(Enum(Device))
    visitors: Mapped[int]
    sessions: Mapped[int]
    conversions: Mapped[int]
