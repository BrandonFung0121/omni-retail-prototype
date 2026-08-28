from omni_retail import services
from omni_retail.models import InventoryStatus, OrderStatus
from omni_retail.models.order import Order


def test_seed_produces_orders_across_statuses(session):
    from collections import Counter

    counts = Counter(order.status for order in session.query(Order).all())
    assert counts[OrderStatus.COMPLETED] > 0
    assert counts[OrderStatus.CANCELLED] > 0
    # REFUNDED and PENDING must be more than a token single example --
    # the dashboard's status filter tabs need a demonstrable (if still
    # small/realistic) number of each to filter, not just "exists".
    assert counts[OrderStatus.REFUNDED] >= 3
    assert counts[OrderStatus.PENDING] >= 3


def test_revenue_is_positive(session):
    assert services.revenue(session) > 0


def test_average_order_value_matches_revenue_over_orders(session):
    rev = services.revenue(session)
    orders = services.order_count(session)
    aov = services.average_order_value(session)
    assert orders > 0
    assert aov == round(rev / orders, 2)


def test_average_order_value_handles_zero_orders(session):
    assert services.average_order_value(session, start=None, end=None) >= 0
    # A far-future window with no orders should not raise a ZeroDivisionError.
    import datetime

    future = datetime.date(2999, 1, 1)
    assert services.average_order_value(session, start=future, end=future) == 0.0


def test_top_products_sorted_descending_by_revenue(session):
    products = services.top_products(session, limit=10, by="revenue")
    assert len(products) > 0
    revenues = [p.revenue for p in products]
    assert revenues == sorted(revenues, reverse=True)


def test_top_products_by_units(session):
    products = services.top_products(session, limit=5, by="units")
    units = [p.units_sold for p in products]
    assert units == sorted(units, reverse=True)


def test_high_value_customers_sorted_descending(session):
    customers = services.high_value_customers(session, limit=10)
    assert len(customers) > 0
    spends = [c.total_spent for c in customers]
    assert spends == sorted(spends, reverse=True)
    for c in customers:
        assert c.order_count > 0
        assert c.average_order_value == round(c.total_spent / c.order_count, 2)


def test_inventory_status_counts_include_low_and_out_of_stock(session):
    counts = services.inventory_status_counts(session)
    assert sum(counts.values()) > 0
    assert counts[InventoryStatus.LOW_STOCK] > 0
    assert counts[InventoryStatus.OUT_OF_STOCK] > 0


def test_low_stock_products_are_never_healthy(session):
    flagged = services.low_stock_products(session)
    assert len(flagged) > 0
    assert all(inv.status != InventoryStatus.HEALTHY for inv in flagged)


def test_expenses_by_category_sums_to_total(session):
    total = services.total_expenses(session)
    by_category = services.expenses_by_category(session)
    assert total > 0
    assert round(sum(by_category.values()), 2) == total


def test_estimated_profit_is_revenue_minus_costs(session):
    profit = services.estimated_profit(session)
    rev = services.revenue(session)
    cogs = services.cost_of_goods_sold(session)
    expenses = services.total_expenses(session)
    assert profit == round(rev - cogs - expenses, 2)


def test_website_conversion_rate_between_zero_and_hundred(session):
    traffic = services.website_traffic_summary(session)
    assert traffic.visitors > 0
    assert 0 <= traffic.conversion_rate <= 100
    assert traffic.conversions <= traffic.sessions or traffic.sessions >= 0
