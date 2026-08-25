"""Build omni_retail.db from scratch and populate it with demo data.

Usage:
    python scripts/seed_db.py
"""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from omni_retail import services
from omni_retail.data.seed import seed_database
from omni_retail.database import init_db, make_engine, make_session_factory

DB_PATH = "omni_retail.db"


def main() -> None:
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    engine = make_engine(DB_PATH)
    init_db(engine)
    SessionLocal = make_session_factory(engine)

    with SessionLocal() as session:
        seed_database(session)

        today = date.today()
        last_30_start = today - timedelta(days=30)

        print(f"Seeded database at {DB_PATH}\n")
        print("--- Last 30 days ---")
        print(f"Revenue:            ${services.revenue(session, last_30_start, today):,.2f}")
        print(f"Orders:             {services.order_count(session, last_30_start, today)}")
        print(f"Avg order value:    ${services.average_order_value(session, last_30_start, today):,.2f}")
        print(f"Estimated profit:   ${services.estimated_profit(session, last_30_start, today):,.2f}")

        traffic = services.website_traffic_summary(session, last_30_start, today)
        print(f"Website visitors:   {traffic.visitors:,}")
        print(f"Conversion rate:    {traffic.conversion_rate}%")

        print("\n--- Top 5 products by revenue ---")
        for product in services.top_products(session, last_30_start, today, limit=5):
            print(f"  {product.name:<35} ${product.revenue:>10,.2f}  ({product.units_sold} units)")

        print("\n--- Top 5 customers by spend (all time) ---")
        for customer in services.high_value_customers(session, limit=5):
            print(f"  {customer.name:<25} ${customer.total_spent:>10,.2f}  ({customer.order_count} orders)")

        print("\n--- Low / out-of-stock products ---")
        for inv in services.low_stock_products(session):
            print(f"  {inv.product.name:<35} stock={inv.current_stock:<4} threshold={inv.reorder_threshold:<4} status={inv.status.value}")

        print("\n--- Expenses by category (all time) ---")
        for category, amount in services.expenses_by_category(session).items():
            print(f"  {category.value:<12} ${amount:>10,.2f}")


if __name__ == "__main__":
    main()
