"""Tunable thresholds for the automation rules.

Values were calibrated against the seeded demo dataset (see
scripts/seed_db.py) so the Action Center shows a realistic, non-empty,
non-overwhelming mix of severities out of the box. A real deployment
would tune these per business, or eventually let an AI agent
(Phase 4) suggest adjustments from observed history.
"""

# Revenue: percent decline vs. the immediately preceding period of
# equal length.
REVENUE_DROP_WARNING_PCT = 15.0
REVENUE_DROP_CRITICAL_PCT = 30.0
REVENUE_PERIOD_DAYS = 30

# Expenses: percent increase, current calendar month vs. previous
# calendar month. Calendar-month buckets are used (rather than a
# rolling N-day window) because expenses are recorded once per month
# per category -- a rolling window can straddle 1 or 2 billing dates
# depending on where it falls, which creates false "spikes" that are
# really just a windowing artifact, not a real cost increase.
EXPENSE_SPIKE_WARNING_PCT = 50.0
EXPENSE_SPIKE_CRITICAL_PCT = 100.0

# Website traffic: visitor growth vs. the preceding period that isn't
# matched by a proportional lift in conversion rate.
TRAFFIC_PERIOD_DAYS = 30
TRAFFIC_SPIKE_VISITOR_GROWTH_WARNING_PCT = 25.0
TRAFFIC_SPIKE_VISITOR_GROWTH_CRITICAL_PCT = 60.0
# Conversion rate is considered "not keeping pace" if it hasn't grown
# by at least this fraction alongside the visitor growth.
TRAFFIC_CONVERSION_KEEP_PACE_TOLERANCE = 1.10

# Orders: share of orders in the period that ended cancelled or
# refunded (never became, or stopped being, revenue).
ORDER_PERIOD_DAYS = 30
ORDER_FAILURE_RATE_WARNING_PCT = 8.0
ORDER_FAILURE_RATE_CRITICAL_PCT = 15.0

# Customers: days since a high-value customer's last completed order.
CUSTOMER_POOL_SIZE = 15
CHURN_RISK_DAYS_WARNING = 30
CHURN_RISK_DAYS_CRITICAL = 60
