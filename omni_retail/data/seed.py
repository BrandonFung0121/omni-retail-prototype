"""Synthetic dataset generator for the OMNI Retail prototype.

Produces a reproducible (seeded) demo dataset with deliberate,
realistic patterns rather than uniform randomness:

- A handful of popular products account for most sales; several are
  slow movers (see catalog.py).
- Customers fall into spending tiers (bargain / regular / VIP) that
  drive order frequency and basket size, creating genuine high-value
  customers and repeat purchasers.
- Order volume is seasonal (a Nov/Dec holiday bump, a Feb dip).
- A small share of orders are cancelled, refunded, or still pending;
  payments include some failures.
- A few products are deliberately left low/out of stock.
- One expense category gets a one-month spike (for anomaly detection
  demos); marketing spend loosely tracks revenue.
- One recent week has a website traffic spike with flat conversions
  (for the "traffic up, sales flat" automation scenario).
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from faker import Faker
from sqlalchemy.orm import Session

from omni_retail.auth import hash_password
from omni_retail.data.catalog import PRODUCT_CATALOG
from omni_retail.models import (
    Customer,
    Expense,
    ExpenseCategory,
    Inventory,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Product,
    SalesChannel,
)
from omni_retail.models.website_visit import Device, TrafficSource, WebsiteVisit

SEED = 42
NUM_CUSTOMERS = 200
HISTORY_DAYS = 450
WEBSITE_HISTORY_DAYS = 150
TRAFFIC_SPIKE_START_DAYS_AGO = 10
TRAFFIC_SPIKE_END_DAYS_AGO = 4

CUSTOMER_TIERS = {
    # tier: (population weight, monthly order-rate range, basket-size range)
    "bargain": (0.55, (0.05, 0.25), (1, 2)),
    "regular": (0.32, (0.25, 0.7), (1, 3)),
    "vip": (0.13, (0.8, 1.8), (2, 5)),
}

SEASONAL_MONTH_MULTIPLIER = {
    1: 0.85, 2: 0.75, 3: 0.9, 4: 0.95, 5: 1.0, 6: 1.0,
    7: 0.95, 8: 0.95, 9: 1.0, 10: 1.1, 11: 1.35, 12: 1.5,
}


def _weighted_choice(rng: random.Random, options: list, weights: list):
    return rng.choices(options, weights=weights, k=1)[0]


def seed_database(session: Session, seed: int = SEED) -> None:
    rng = random.Random(seed)
    faker = Faker()
    Faker.seed(seed)

    today = date.today()
    history_start = today - timedelta(days=HISTORY_DAYS)

    products = _seed_products(session, rng)
    _seed_inventory(session, products, rng)
    customers = _seed_customers(session, faker, rng, history_start, today)
    orders = _seed_orders(session, customers, products, rng, history_start, today)
    _seed_payments(session, orders, rng)
    _seed_expenses(session, rng, history_start, today)
    _seed_website_visits(session, rng, today)

    session.commit()


def _seed_products(session: Session, rng: random.Random) -> list[Product]:
    products = []
    for name, category, price, cost, _weight in PRODUCT_CATALOG:
        product = Product(name=name, category=category, selling_price=price, cost=cost)
        session.add(product)
        products.append(product)
    session.flush()
    return products


def _seed_inventory(session: Session, products: list[Product], rng: random.Random) -> None:
    popularity_by_name = {name: weight for name, *_rest, weight in PRODUCT_CATALOG}
    for product in products:
        weight = popularity_by_name[product.name]
        reorder_threshold = rng.randint(15, 30)

        roll = rng.random()
        if roll < 0.12:
            current_stock = rng.randint(0, 0)  # out of stock
        elif roll < 0.30:
            current_stock = rng.randint(1, reorder_threshold)  # low stock
        else:
            # Popular products get restocked more, so healthy stock scales
            # loosely with demand plus randomness.
            current_stock = rng.randint(reorder_threshold + 10, reorder_threshold + int(weight * 4) + 40)

        session.add(
            Inventory(
                product_id=product.id,
                current_stock=current_stock,
                reorder_threshold=reorder_threshold,
                last_updated=datetime.combine(date.today(), datetime.min.time()),
            )
        )


# Storefront demo login accounts, seeded with known credentials so the
# purchase flow can be demonstrated without registering first. Given
# real order history (via the normal tier-based generation below) so
# "My Orders" has something to show. Registration still works for any
# other account -- these are a convenience, not the only way in.
DEMO_ACCOUNTS = [
    ("Jordan Rivera", "demo@omniretail.test", "password123", "vip"),
    ("Alex Chen", "customer@omniretail.test", "password123", "regular"),
]


def _seed_customers(
    session: Session, faker: Faker, rng: random.Random, history_start: date, today: date
) -> list[tuple[Customer, str]]:
    tier_names = list(CUSTOMER_TIERS.keys())
    tier_weights = [CUSTOMER_TIERS[t][0] for t in tier_names]

    customers = []
    seen_emails: set[str] = set()

    for name, email, password, tier in DEMO_ACCOUNTS:
        salt, password_hash = hash_password(password)
        join_offset = rng.randint(0, (today - history_start).days)
        customer = Customer(
            name=name,
            email=email,
            join_date=history_start + timedelta(days=join_offset),
            password_hash=password_hash,
            password_salt=salt,
        )
        session.add(customer)
        customers.append((customer, tier))
        seen_emails.add(email)

    for _ in range(NUM_CUSTOMERS):
        tier = _weighted_choice(rng, tier_names, tier_weights)
        join_offset = rng.randint(0, (today - history_start).days)
        join_date = history_start + timedelta(days=join_offset)

        name = faker.name()
        email = faker.unique.email()
        while email in seen_emails:
            email = faker.unique.email()
        seen_emails.add(email)

        customer = Customer(name=name, email=email, join_date=join_date)
        session.add(customer)
        customers.append((customer, tier))

    session.flush()
    return customers


def _seed_orders(
    session: Session,
    customers: list[tuple[Customer, str]],
    products: list[Product],
    rng: random.Random,
    history_start: date,
    today: date,
) -> list[Order]:
    product_weights = [w for *_rest, w in PRODUCT_CATALOG]
    orders: list[Order] = []

    for customer, tier in customers:
        _pop_weight, rate_range, basket_range = CUSTOMER_TIERS[tier]
        active_days = max((today - customer.join_date).days, 1)
        active_months = active_days / 30.0
        monthly_rate = rng.uniform(*rate_range)
        expected_orders = monthly_rate * active_months

        num_orders = rng.choices(
            [0, max(1, round(expected_orders))],
            weights=[0.15, 0.85],
            k=1,
        )[0]

        for _ in range(num_orders):
            order_date = _seasonal_order_date(rng, customer.join_date, today)
            order_dt = datetime.combine(order_date, datetime.min.time()) + timedelta(
                hours=rng.randint(8, 21), minutes=rng.randint(0, 59)
            )

            days_ago = (today - order_date).days
            status = _order_status(rng, days_ago)
            channel = _weighted_choice(rng, list(SalesChannel), [0.6, 0.4])

            order = Order(
                customer_id=customer.id,
                order_datetime=order_dt,
                status=status,
                channel=channel,
            )
            session.add(order)
            session.flush()

            num_items = rng.randint(*basket_range)
            chosen_products = rng.choices(products, weights=product_weights, k=num_items)
            for product in dict.fromkeys(chosen_products):
                quantity = rng.randint(1, 3)
                session.add(
                    OrderItem(
                        order_id=order.id,
                        product_id=product.id,
                        quantity=quantity,
                        unit_price=product.selling_price,
                    )
                )

            orders.append(order)

    session.flush()
    return orders


def _seasonal_order_date(rng: random.Random, join_date: date, today: date) -> date:
    span_days = max((today - join_date).days, 1)
    for _ in range(20):
        candidate = join_date + timedelta(days=rng.randint(0, span_days))
        multiplier = SEASONAL_MONTH_MULTIPLIER[candidate.month]
        if rng.random() < multiplier / 1.5:
            return candidate
    return today


def _order_status(rng: random.Random, days_ago: int) -> OrderStatus:
    # Orders placed in roughly the last two weeks may still be awaiting
    # payment/fulfillment -- a wider window than "yesterday" is needed
    # so PENDING shows up as a small but reliably non-trivial slice of
    # the seeded data (a couple of days produced ~1 order total, too
    # thin to demonstrate the dashboard's status filter).
    if days_ago < 14:
        return _weighted_choice(
            rng,
            [OrderStatus.COMPLETED, OrderStatus.PENDING, OrderStatus.CANCELLED],
            [0.55, 0.35, 0.10],
        )
    return _weighted_choice(
        rng,
        [OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.REFUNDED],
        [0.90, 0.07, 0.03],
    )


def _seed_payments(session: Session, orders: list[Order], rng: random.Random) -> None:
    methods = list(PaymentMethod)
    for order in orders:
        if order.status == OrderStatus.PENDING:
            continue  # not yet charged

        order_value = round(order.order_value, 2)
        if order_value <= 0:
            continue

        if order.status == OrderStatus.COMPLETED:
            # A small share of "completed" orders still had a failed
            # attempt logged before the successful charge went through.
            status = PaymentStatus.SUCCESS
        elif order.status == OrderStatus.REFUNDED:
            status = PaymentStatus.REFUNDED
        else:  # CANCELLED
            status = _weighted_choice(rng, [PaymentStatus.FAILED, PaymentStatus.SUCCESS], [0.7, 0.3])

        session.add(
            Payment(
                order_id=order.id,
                method=_weighted_choice(rng, methods, [0.35, 0.2, 0.15, 0.2, 0.1]),
                amount=order_value,
                status=status,
                payment_date=order.order_datetime + timedelta(minutes=rng.randint(1, 30)),
            )
        )


EXPENSE_MONTHLY_RANGE = {
    ExpenseCategory.RENT: (3200, 3200),
    ExpenseCategory.PAYROLL: (9000, 11500),
    ExpenseCategory.MARKETING: (1500, 4500),
    ExpenseCategory.LOGISTICS: (1200, 2800),
    ExpenseCategory.SOFTWARE: (400, 700),
    ExpenseCategory.UTILITIES: (350, 650),
    ExpenseCategory.OTHER: (200, 900),
}

EXPENSE_DESCRIPTIONS = {
    ExpenseCategory.RENT: "Monthly storefront/warehouse rent",
    ExpenseCategory.PAYROLL: "Staff wages and payroll taxes",
    ExpenseCategory.MARKETING: "Paid ads and promotions",
    ExpenseCategory.LOGISTICS: "Shipping and fulfillment costs",
    ExpenseCategory.SOFTWARE: "SaaS subscriptions and tooling",
    ExpenseCategory.UTILITIES: "Electricity, internet, and utilities",
    ExpenseCategory.OTHER: "Miscellaneous operating costs",
}

# Deliberate anomaly: logistics costs spike sharply two months ago,
# for the "unusual expense increase" monitoring scenario.
ANOMALY_CATEGORY = ExpenseCategory.LOGISTICS
ANOMALY_MONTHS_AGO = 2
ANOMALY_MULTIPLIER = 2.6


def _seed_expenses(session: Session, rng: random.Random, history_start: date, today: date) -> None:
    month_cursor = date(history_start.year, history_start.month, 1)
    month_index = 0
    while month_cursor <= today:
        months_ago = (today.year - month_cursor.year) * 12 + (today.month - month_cursor.month)
        for category, (low, high) in EXPENSE_MONTHLY_RANGE.items():
            amount = rng.uniform(low, high)
            if category == ANOMALY_CATEGORY and months_ago == ANOMALY_MONTHS_AGO:
                amount *= ANOMALY_MULTIPLIER
            session.add(
                Expense(
                    category=category,
                    amount=round(amount, 2),
                    expense_date=month_cursor + timedelta(days=rng.randint(0, 27)),
                    description=EXPENSE_DESCRIPTIONS[category],
                )
            )
        month_cursor = _add_month(month_cursor)
        month_index += 1


def _add_month(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


TRAFFIC_SOURCE_WEIGHTS = {
    TrafficSource.ORGANIC_SEARCH: 0.30,
    TrafficSource.PAID_SEARCH: 0.20,
    TrafficSource.SOCIAL: 0.20,
    TrafficSource.EMAIL: 0.10,
    TrafficSource.DIRECT: 0.15,
    TrafficSource.REFERRAL: 0.05,
}
DEVICE_WEIGHTS = {Device.MOBILE: 0.55, Device.DESKTOP: 0.35, Device.TABLET: 0.10}
BASE_DAILY_VISITORS = 260


def _seed_website_visits(session: Session, rng: random.Random, today: date) -> None:
    start = today - timedelta(days=WEBSITE_HISTORY_DAYS)
    day = start
    while day <= today:
        days_ago = (today - day).days
        in_spike = TRAFFIC_SPIKE_END_DAYS_AGO <= days_ago <= TRAFFIC_SPIKE_START_DAYS_AGO
        seasonal = SEASONAL_MONTH_MULTIPLIER[day.month]
        weekday_factor = 1.15 if day.weekday() < 5 else 0.85

        daily_visitors = BASE_DAILY_VISITORS * seasonal * weekday_factor
        daily_visitors *= rng.uniform(0.85, 1.15)
        if in_spike:
            # Paid social campaign drives a traffic spike, but conversion
            # rate does not follow — surfaced as a conversion problem.
            daily_visitors *= 2.4

        for source, source_weight in TRAFFIC_SOURCE_WEIGHTS.items():
            for device, device_weight in DEVICE_WEIGHTS.items():
                visitors = max(1, round(daily_visitors * source_weight * device_weight))
                sessions = round(visitors * rng.uniform(1.05, 1.3))

                base_conversion_rate = rng.uniform(0.02, 0.05)
                if in_spike and source == TrafficSource.SOCIAL:
                    base_conversion_rate *= 0.35  # spike traffic converts poorly
                conversions = round(visitors * base_conversion_rate)

                session.add(
                    WebsiteVisit(
                        visit_date=day,
                        traffic_source=source,
                        device=device,
                        visitors=visitors,
                        sessions=sessions,
                        conversions=conversions,
                    )
                )
        day += timedelta(days=1)
