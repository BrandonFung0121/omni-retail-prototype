"""Pydantic response models for the OMNI Retail API.

Kept separate from the internal services/analytics dataclasses so the
API contract can evolve independently of the internal representation.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

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


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: str
    type: str
    severity: str
    title: str
    description: str
    recommended_action: str
    supporting_data: dict[str, Any]
    detected_at: datetime
    status: str


class AlertSummaryResponse(BaseModel):
    total: int
    critical: int
    warning: int
    info: int
    by_type: dict[str, int]


class AskRequest(BaseModel):
    question: str


class AgentResponseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    question: str
    intent: str
    answer: str
    confidence: str
    supporting_metrics: dict[str, Any]
    recommended_actions: list[str]
    related_alert_ids: list[str]
    generated_by: str
    tool_trace: list[dict[str, Any]] = []


class ExampleQuestionsResponse(BaseModel):
    questions: list[str]


class ProductCatalogEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    name: str
    category: str
    selling_price: float
    current_stock: int
    reorder_threshold: int
    status: str


class CustomerSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: int
    name: str
    email: str


class ReceiptLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    product_name: str
    quantity: int
    unit_price: float
    line_total: float


class OrderSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: int
    order_datetime: datetime
    customer_name: str
    status: str
    channel: str
    item_count: int
    total: float
    payment_method: str | None
    payment_status: str | None


class OrderDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: int
    order_datetime: datetime
    customer_id: int | None
    customer_name: str
    status: str
    channel: str
    lines: list[ReceiptLineOut]
    subtotal: float
    discount_total: float
    total: float
    payment_method: str | None
    payment_status: str | None


class CartItemIn(BaseModel):
    product_id: int
    quantity: int


class CheckoutRequest(BaseModel):
    items: list[CartItemIn]
    payment_method: str
    customer_id: int | None = None
    channel: str = "in_store"
    discount_type: str | None = None
    discount_value: float = 0.0


class SaleReceiptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: int
    order_datetime: datetime
    customer_id: int | None
    customer_name: str
    channel: str
    status: str
    lines: list[ReceiptLineOut]
    subtotal: float
    discount_total: float
    total: float
    payment_method: str
    payment_status: str
    payment_reference: str
    failure_reason: str | None = None


class StorefrontCheckoutRequest(BaseModel):
    items: list[CartItemIn]
    payment_method: str
    channel: str = "online"
    discount_type: str | None = None
    discount_value: float = 0.0
    card_number: str | None = None
    idempotency_key: str | None = None


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class CustomerMeOut(BaseModel):
    customer_id: int
    name: str
    email: str


class AuthResponse(BaseModel):
    token: str
    customer: CustomerMeOut


class AgentActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: int
    action_type: str
    source_alert_id: str | None
    customer_id: int | None
    product_id: int | None
    business_reason: str
    supporting_evidence: dict[str, Any]
    proposed_parameters: dict[str, Any]
    edited_parameters: dict[str, Any] | None
    expected_outcome: str
    risk_level: str
    status: str
    created_at: datetime
    decided_at: datetime | None
    decided_by: str | None
    rejection_reason: str | None
    executed_at: datetime | None
    execution_result: dict[str, Any] | None


class ApproveActionRequest(BaseModel):
    decided_by: str = "Admin"
    edited_parameters: dict[str, Any] | None = None


class RejectActionRequest(BaseModel):
    decided_by: str = "Admin"
    reason: str | None = None


class StorefrontAskRequest(BaseModel):
    question: str
    cart: list[CartItemIn] = []


class CartActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    product_name: str
    quantity: int
    unit_price: float


class StorefrontAskResponse(BaseModel):
    answer: str
    generated_by: str
    cart_action: CartActionOut | None = None
    suggested_product_ids: list[int] = []
