"""Pydantic response models for the OMNI Retail API.

Kept separate from the internal services/analytics dataclasses so the
API contract can evolve independently of the internal representation.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


class RevenueResponse(BaseModel):
    revenue: float


class OrderCountResponse(BaseModel):
    orders: int


class AverageOrderValueResponse(BaseModel):
    average_order_value: float


class ProductPerformanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    name: str
    category: str
    units_sold: int
    revenue: float


class CustomerValueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: int
    name: str
    email: str
    total_spent: float
    order_count: int
    average_order_value: float


class InventoryItemOut(BaseModel):
    product_id: int
    product_name: str
    category: str
    current_stock: int
    reorder_threshold: int
    status: str


class InventoryStatusResponse(BaseModel):
    healthy: int
    low_stock: int
    out_of_stock: int
    low_stock_items: list[InventoryItemOut]


class ExpensesResponse(BaseModel):
    total: float
    by_category: dict[str, float]


class EstimatedProfitResponse(BaseModel):
    estimated_profit: float
    revenue: float
    cost_of_goods_sold: float
    expenses: float


class TrafficResponse(BaseModel):
    visitors: int
    sessions: int
    conversions: int
    conversion_rate: float


class ConversionRateResponse(BaseModel):
    conversion_rate: float
    visitors: int
    conversions: int


class DailyRevenuePointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    day: date
    revenue: float
    orders: int


class DailyTrafficPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    day: date
    visitors: int
    sessions: int
    conversions: int
    conversion_rate: float


class KPISummaryResponse(BaseModel):
    revenue: float
    orders: int
    average_order_value: float
    estimated_profit: float
    website_visitors: int
    conversion_rate: float
