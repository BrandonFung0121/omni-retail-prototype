"""Core business-intelligence calculations.

This module is the single source of truth for OMNI Retail's KPI
definitions. Dashboards, alerts/automation, and future AI features
should all call these functions rather than re-deriving metrics, so
the numbers stay consistent everywhere they're shown.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from omni_retail.models import (
    Customer,
    Expense,
    ExpenseCategory,
    Inventory,
    InventoryStatus,
    Order,
    OrderItem,
    OrderStatus,
    Product,
)
from omni_retail.models.website_visit import WebsiteVisit

# Only completed orders count as realized revenue. Cancelled orders
# never paid; refunded orders paid and then had that payment reversed.
REVENUE_STATUSES = (OrderStatus.COMPLETED,)


def _apply_date_filter(stmt: Select, column, start: Optional[date], end: Optional[date]) -> Select:
    is_datetime_column = column.type.python_type is datetime
    if start is not None:
        start_value = datetime.combine(start, datetime.min.time()) if is_datetime_column else start
        stmt = stmt.where(column >= start_value)
    if end is not None:
        if is_datetime_column:
            stmt = stmt.where(column < datetime.combine(end, datetime.min.time()) + timedelta(days=1))
        else:
            stmt = stmt.where(column <= end)
    return stmt


@dataclass
class ProductPerformance:
    product_id: int
    name: str
    category: str
    units_sold: int
    revenue: float


@dataclass
class CustomerValue:
    customer_id: int
    name: str
    email: str
    total_spent: float
    order_count: int
    average_order_value: float


@dataclass
class TrafficSummary:
    visitors: int
    sessions: int
    conversions: int
    conversion_rate: float


@dataclass
class DailyRevenuePoint:
    day: date
    revenue: float
    orders: int


@dataclass
class DailyTrafficPoint:
    day: date
    visitors: int
    sessions: int
    conversions: int
    conversion_rate: float


def _as_date(value) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date() if isinstance(value, str) else value


def revenue(session: Session, start: Optional[date] = None, end: Optional[date] = None) -> float:
    """Total realized revenue: sum of line totals on completed orders."""
    stmt = (
        select(func.coalesce(func.sum(OrderItem.quantity * OrderItem.unit_price), 0.0))
        .join(Order, OrderItem.order_id == Order.id)
        .where(Order.status.in_(REVENUE_STATUSES))
    )
    stmt = _apply_date_filter(stmt, Order.order_datetime, start, end)
    return round(float(session.execute(stmt).scalar_one()), 2)


def revenue_trend(
    session: Session, start: Optional[date] = None, end: Optional[date] = None
) -> list[DailyRevenuePoint]:
    """Daily revenue and order count, for trend charts."""
    day_col = func.date(Order.order_datetime)
    stmt = (
        select(
            day_col.label("day"),
            func.sum(OrderItem.quantity * OrderItem.unit_price).label("revenue"),
            func.count(func.distinct(Order.id)).label("orders"),
        )
        .join(OrderItem, OrderItem.order_id == Order.id)
        .where(Order.status.in_(REVENUE_STATUSES))
        .group_by(day_col)
        .order_by(day_col)
    )
    stmt = _apply_date_filter(stmt, Order.order_datetime, start, end)
    rows = session.execute(stmt).all()
    return [
        DailyRevenuePoint(day=_as_date(row.day), revenue=round(float(row.revenue), 2), orders=int(row.orders))
        for row in rows
    ]


def order_count(session: Session, start: Optional[date] = None, end: Optional[date] = None) -> int:
    """Number of valid (completed) orders in the period."""
    stmt = select(func.count(Order.id)).where(Order.status.in_(REVENUE_STATUSES))
    stmt = _apply_date_filter(stmt, Order.order_datetime, start, end)
    return int(session.execute(stmt).scalar_one())


def average_order_value(session: Session, start: Optional[date] = None, end: Optional[date] = None) -> float:
    orders = order_count(session, start, end)
    if orders == 0:
        return 0.0
    return round(revenue(session, start, end) / orders, 2)


def top_products(
    session: Session,
    start: Optional[date] = None,
    end: Optional[date] = None,
    limit: int = 10,
    by: str = "revenue",
) -> list[ProductPerformance]:
    """Best-selling products, ranked by 'revenue' or 'units'."""
    if by not in ("revenue", "units"):
        raise ValueError("by must be 'revenue' or 'units'")

    units_sold = func.sum(OrderItem.quantity)
    line_revenue = func.sum(OrderItem.quantity * OrderItem.unit_price)

    stmt = (
        select(
            Product.id,
            Product.name,
            Product.category,
            units_sold.label("units_sold"),
            line_revenue.label("revenue"),
        )
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, OrderItem.order_id == Order.id)
        .where(Order.status.in_(REVENUE_STATUSES))
        .group_by(Product.id)
        .order_by((line_revenue if by == "revenue" else units_sold).desc())
        .limit(limit)
    )
    stmt = _apply_date_filter(stmt, Order.order_datetime, start, end)

    rows = session.execute(stmt).all()
    return [
        ProductPerformance(
            product_id=row.id,
            name=row.name,
            category=row.category,
            units_sold=int(row.units_sold),
            revenue=round(float(row.revenue), 2),
        )
        for row in rows
    ]


def high_value_customers(
    session: Session, start: Optional[date] = None, end: Optional[date] = None, limit: int = 10
) -> list[CustomerValue]:
    """Customers ranked by total spending on completed orders."""
    total_spent = func.sum(OrderItem.quantity * OrderItem.unit_price)
    order_count_col = func.count(func.distinct(Order.id))

    stmt = (
        select(
            Customer.id,
            Customer.name,
            Customer.email,
            total_spent.label("total_spent"),
            order_count_col.label("order_count"),
        )
        .join(Order, Order.customer_id == Customer.id)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .where(Order.status.in_(REVENUE_STATUSES))
        .group_by(Customer.id)
        .order_by(total_spent.desc())
        .limit(limit)
    )
    stmt = _apply_date_filter(stmt, Order.order_datetime, start, end)

    rows = session.execute(stmt).all()
    results = []
    for row in rows:
        spent = round(float(row.total_spent), 2)
        count = int(row.order_count)
        results.append(
            CustomerValue(
                customer_id=row.id,
                name=row.name,
                email=row.email,
                total_spent=spent,
                order_count=count,
                average_order_value=round(spent / count, 2) if count else 0.0,
            )
        )
    return results


def order_status_counts(
    session: Session, start: Optional[date] = None, end: Optional[date] = None
) -> dict[OrderStatus, int]:
    """Order counts by status, across ALL statuses (not just completed).

    Unlike order_count(), this includes cancelled/pending/refunded
    orders -- it answers "what happened to orders placed in this
    period", which cancellation/failure-pattern monitoring needs.
    """
    stmt = select(Order.status, func.count(Order.id)).group_by(Order.status)
    stmt = _apply_date_filter(stmt, Order.order_datetime, start, end)
    rows = session.execute(stmt).all()
    counts = {status: 0 for status in OrderStatus}
    for status, count in rows:
        counts[status] = int(count)
    return counts


def last_order_date(session: Session, customer_id: int) -> Optional[date]:
    """Most recent completed-order date for a customer, or None if they have none."""
    stmt = (
        select(func.max(Order.order_datetime))
        .where(Order.customer_id == customer_id, Order.status.in_(REVENUE_STATUSES))
    )
    result = session.execute(stmt).scalar_one()
    return result.date() if result else None


def inventory_status_counts(session: Session) -> dict[InventoryStatus, int]:
    counts = {status: 0 for status in InventoryStatus}
    for inventory in session.execute(select(Inventory)).scalars().all():
        counts[inventory.status] += 1
    return counts


def low_stock_products(session: Session) -> list[Inventory]:
    """Inventory rows that are low or out of stock, most urgent first."""
    inventories = session.execute(select(Inventory)).scalars().all()
    flagged = [inv for inv in inventories if inv.status != InventoryStatus.HEALTHY]
    flagged.sort(key=lambda inv: inv.current_stock)
    return flagged


def total_expenses(session: Session, start: Optional[date] = None, end: Optional[date] = None) -> float:
    stmt = select(func.coalesce(func.sum(Expense.amount), 0.0))
    stmt = _apply_date_filter(stmt, Expense.expense_date, start, end)
    return round(float(session.execute(stmt).scalar_one()), 2)


def expenses_by_category(
    session: Session, start: Optional[date] = None, end: Optional[date] = None
) -> dict[ExpenseCategory, float]:
    stmt = select(Expense.category, func.sum(Expense.amount)).group_by(Expense.category)
    stmt = _apply_date_filter(stmt, Expense.expense_date, start, end)
    rows = session.execute(stmt).all()
    return {category: round(float(amount), 2) for category, amount in rows}


def cost_of_goods_sold(session: Session, start: Optional[date] = None, end: Optional[date] = None) -> float:
    stmt = (
        select(func.coalesce(func.sum(OrderItem.quantity * Product.cost), 0.0))
        .join(Product, OrderItem.product_id == Product.id)
        .join(Order, OrderItem.order_id == Order.id)
        .where(Order.status.in_(REVENUE_STATUSES))
    )
    stmt = _apply_date_filter(stmt, Order.order_datetime, start, end)
    return round(float(session.execute(stmt).scalar_one()), 2)


def estimated_profit(session: Session, start: Optional[date] = None, end: Optional[date] = None) -> float:
    """Revenue minus cost of goods sold minus operating expenses.

    A simplified profit model for the prototype; the architecture
    (separate revenue/COGS/expense functions) allows a more nuanced
    calculation (e.g. allocated overhead, taxes) to be layered on later.
    """
    return round(
        revenue(session, start, end) - cost_of_goods_sold(session, start, end) - total_expenses(session, start, end),
        2,
    )


def website_traffic_summary(
    session: Session, start: Optional[date] = None, end: Optional[date] = None
) -> TrafficSummary:
    stmt = select(
        func.coalesce(func.sum(WebsiteVisit.visitors), 0),
        func.coalesce(func.sum(WebsiteVisit.sessions), 0),
        func.coalesce(func.sum(WebsiteVisit.conversions), 0),
    )
    stmt = _apply_date_filter(stmt, WebsiteVisit.visit_date, start, end)
    visitors, sessions, conversions = session.execute(stmt).one()
    visitors, sessions, conversions = int(visitors), int(sessions), int(conversions)
    conversion_rate = round(conversions / visitors * 100, 2) if visitors else 0.0
    return TrafficSummary(
        visitors=visitors, sessions=sessions, conversions=conversions, conversion_rate=conversion_rate
    )


def website_traffic_trend(
    session: Session, start: Optional[date] = None, end: Optional[date] = None
) -> list[DailyTrafficPoint]:
    """Daily visitors/sessions/conversions, for trend charts."""
    stmt = (
        select(
            WebsiteVisit.visit_date.label("day"),
            func.sum(WebsiteVisit.visitors).label("visitors"),
            func.sum(WebsiteVisit.sessions).label("sessions"),
            func.sum(WebsiteVisit.conversions).label("conversions"),
        )
        .group_by(WebsiteVisit.visit_date)
        .order_by(WebsiteVisit.visit_date)
    )
    stmt = _apply_date_filter(stmt, WebsiteVisit.visit_date, start, end)
    rows = session.execute(stmt).all()

    points = []
    for row in rows:
        visitors, sessions, conversions = int(row.visitors), int(row.sessions), int(row.conversions)
        rate = round(conversions / visitors * 100, 2) if visitors else 0.0
        points.append(
            DailyTrafficPoint(
                day=_as_date(row.day),
                visitors=visitors,
                sessions=sessions,
                conversions=conversions,
                conversion_rate=rate,
            )
        )
    return points


@dataclass
class ProductCatalogEntry:
    product_id: int
    name: str
    category: str
    selling_price: float
    current_stock: int
    reorder_threshold: int
    status: str


def list_products(session: Session) -> list[ProductCatalogEntry]:
    """Full catalog with live stock -- for product-selection UIs (POS, storefront)."""
    stmt = select(Product, Inventory).join(Inventory, Inventory.product_id == Product.id).order_by(Product.name)
    rows = session.execute(stmt).all()
    return [
        ProductCatalogEntry(
            product_id=product.id,
            name=product.name,
            category=product.category,
            selling_price=float(product.selling_price),
            current_stock=inventory.current_stock,
            reorder_threshold=inventory.reorder_threshold,
            status=inventory.status.value,
        )
        for product, inventory in rows
    ]


@dataclass
class CustomerSummary:
    customer_id: int
    name: str
    email: str


def search_customers(session: Session, query: str = "", limit: int = 10) -> list[CustomerSummary]:
    """Name/email typeahead -- for customer-selection UIs (POS, storefront)."""
    stmt = select(Customer).order_by(Customer.name).limit(limit)
    if query:
        pattern = f"%{query.lower()}%"
        stmt = stmt.where((func.lower(Customer.name).like(pattern)) | (func.lower(Customer.email).like(pattern)))
    customers = session.execute(stmt).scalars().all()
    return [CustomerSummary(customer_id=c.id, name=c.name, email=c.email) for c in customers]


@dataclass
class OrderSummary:
    order_id: int
    order_datetime: datetime
    customer_name: str
    status: str
    channel: str
    item_count: int
    total: float
    payment_method: Optional[str]
    payment_status: Optional[str]


def list_orders(
    session: Session,
    start: Optional[date] = None,
    end: Optional[date] = None,
    status: Optional[OrderStatus] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[OrderSummary]:
    """Recent orders/transactions, newest first -- for the Transactions view."""
    stmt = (
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.customer), selectinload(Order.payment))
        .order_by(Order.order_datetime.desc())
        .limit(limit)
        .offset(offset)
    )
    if status is not None:
        stmt = stmt.where(Order.status == status)
    stmt = _apply_date_filter(stmt, Order.order_datetime, start, end)
    orders = session.execute(stmt).scalars().all()

    return [
        OrderSummary(
            order_id=order.id,
            order_datetime=order.order_datetime,
            customer_name=order.customer.name if order.customer else "Guest",
            status=order.status.value,
            channel=order.channel.value,
            item_count=sum(item.quantity for item in order.items),
            total=round(order.order_value, 2),
            payment_method=order.payment.method.value if order.payment else None,
            payment_status=order.payment.status.value if order.payment else None,
        )
        for order in orders
    ]


@dataclass
class ReceiptLine:
    product_id: int
    product_name: str
    quantity: int
    unit_price: float
    line_total: float


@dataclass
class OrderDetail:
    order_id: int
    order_datetime: datetime
    customer_id: Optional[int]
    customer_name: str
    status: str
    channel: str
    lines: list[ReceiptLine]
    subtotal: float
    discount_total: float
    total: float
    payment_method: Optional[str]
    payment_status: Optional[str]


def get_order(session: Session, order_id: int) -> Optional[OrderDetail]:
    """Full line-item detail for one order -- for a receipt view."""
    order = session.get(
        Order,
        order_id,
        options=[selectinload(Order.items).selectinload(OrderItem.product), selectinload(Order.customer), selectinload(Order.payment)],
    )
    if order is None:
        return None

    lines = [
        ReceiptLine(
            product_id=item.product_id,
            product_name=item.product.name,
            quantity=item.quantity,
            unit_price=float(item.unit_price),
            line_total=round(item.line_total, 2),
        )
        for item in order.items
    ]
    discount_total = float(order.discount_total)
    total = round(order.order_value, 2)
    return OrderDetail(
        order_id=order.id,
        order_datetime=order.order_datetime,
        customer_id=order.customer_id,
        customer_name=order.customer.name if order.customer else "Guest",
        status=order.status.value,
        channel=order.channel.value,
        lines=lines,
        subtotal=round(total + discount_total, 2),
        discount_total=discount_total,
        total=total,
        payment_method=order.payment.method.value if order.payment else None,
        payment_status=order.payment.status.value if order.payment else None,
    )
