from datetime import date

from omni_retail.automation import Severity, run_all_rules
from omni_retail.automation import rules as automation_rules
from omni_retail.automation.models import AlertType


class _FakeTraffic:
    def __init__(self, visitors, conversion_rate):
        self.visitors = visitors
        self.conversion_rate = conversion_rate


def test_run_all_rules_against_seeded_data_is_well_formed(session):
    alerts = run_all_rules(session)
    assert len(alerts) > 0

    seen_ids = set()
    for alert in alerts:
        assert isinstance(alert.type, AlertType)
        assert isinstance(alert.severity, Severity)
        assert alert.title
        assert alert.description
        assert alert.recommended_action
        assert alert.supporting_data
        assert alert.id not in seen_ids, "alert ids must be unique"
        seen_ids.add(alert.id)


def test_alerts_sorted_most_severe_first(session):
    alerts = run_all_rules(session)
    ranks = [a.severity_rank for a in alerts]
    assert ranks == sorted(ranks, reverse=True)


def test_low_stock_and_out_of_stock_match_inventory_service(session):
    from omni_retail import services
    from omni_retail.models import InventoryStatus

    low_stock_alerts = automation_rules.detect_low_stock(session)
    out_of_stock_alerts = automation_rules.detect_out_of_stock(session)

    flagged = services.low_stock_products(session)
    expected_low = sum(1 for inv in flagged if inv.status == InventoryStatus.LOW_STOCK)
    expected_out = sum(1 for inv in flagged if inv.status == InventoryStatus.OUT_OF_STOCK)

    assert len(low_stock_alerts) == expected_low
    assert len(out_of_stock_alerts) == expected_out
    assert all(a.severity == Severity.WARNING for a in low_stock_alerts)
    assert all(a.severity == Severity.CRITICAL for a in out_of_stock_alerts)


def test_revenue_drop_triggers_when_revenue_falls(session, monkeypatch):
    calls = {"n": 0}

    def fake_revenue(_session, start, end):
        calls["n"] += 1
        # First call is the current period, second is the prior period.
        return 700.0 if calls["n"] == 1 else 1000.0

    monkeypatch.setattr(automation_rules.services, "revenue", fake_revenue)

    alerts = automation_rules.detect_revenue_drop(session, today=date(2026, 6, 15))
    assert len(alerts) == 1
    assert alerts[0].severity == Severity.CRITICAL
    assert alerts[0].supporting_data["pct_change"] == -30.0


def test_revenue_drop_does_not_trigger_on_growth(session, monkeypatch):
    calls = {"n": 0}

    def fake_revenue(_session, start, end):
        calls["n"] += 1
        return 1200.0 if calls["n"] == 1 else 1000.0

    monkeypatch.setattr(automation_rules.services, "revenue", fake_revenue)

    assert automation_rules.detect_revenue_drop(session, today=date(2026, 6, 15)) == []


def test_traffic_conversion_gap_triggers_on_spike_without_lift(session, monkeypatch):
    calls = {"n": 0}

    def fake_traffic(_session, start, end):
        calls["n"] += 1
        return _FakeTraffic(2000, 2.0) if calls["n"] == 1 else _FakeTraffic(1000, 2.5)

    monkeypatch.setattr(automation_rules.services, "website_traffic_summary", fake_traffic)

    alerts = automation_rules.detect_traffic_conversion_gap(session, today=date(2026, 6, 15))
    assert len(alerts) == 1
    assert alerts[0].type == AlertType.TRAFFIC_CONVERSION_GAP
    assert alerts[0].supporting_data["visitor_growth_pct"] == 100.0


def test_traffic_conversion_gap_silent_when_conversion_keeps_pace(session, monkeypatch):
    calls = {"n": 0}

    def fake_traffic(_session, start, end):
        calls["n"] += 1
        return _FakeTraffic(2000, 2.5) if calls["n"] == 1 else _FakeTraffic(1000, 2.0)

    monkeypatch.setattr(automation_rules.services, "website_traffic_summary", fake_traffic)

    assert automation_rules.detect_traffic_conversion_gap(session, today=date(2026, 6, 15)) == []


def test_expense_spike_uses_calendar_month_buckets(session, monkeypatch):
    def fake_expenses(_session, start, end):
        from omni_retail.models import ExpenseCategory

        if start.day == 1 and start.month == 6:
            return {ExpenseCategory.LOGISTICS: 2000.0}
        return {ExpenseCategory.LOGISTICS: 1000.0}

    monkeypatch.setattr(automation_rules.services, "expenses_by_category", fake_expenses)

    alerts = automation_rules.detect_expense_spike(session, today=date(2026, 6, 15))
    assert len(alerts) == 1
    assert alerts[0].supporting_data["category"] == "logistics"
    assert alerts[0].supporting_data["pct_change"] == 100.0
    assert alerts[0].severity == Severity.CRITICAL


def test_order_failure_pattern_triggers_above_threshold(session, monkeypatch):
    from omni_retail.models import OrderStatus

    def fake_counts(_session, start, end):
        return {
            OrderStatus.COMPLETED: 80,
            OrderStatus.PENDING: 0,
            OrderStatus.CANCELLED: 15,
            OrderStatus.REFUNDED: 5,
        }

    monkeypatch.setattr(automation_rules.services, "order_status_counts", fake_counts)

    alerts = automation_rules.detect_order_failure_pattern(session, today=date(2026, 6, 15))
    assert len(alerts) == 1
    assert alerts[0].supporting_data["failure_rate_pct"] == 20.0
    assert alerts[0].severity == Severity.CRITICAL


def test_customer_win_back_flags_stale_high_value_customers(session, monkeypatch):
    from omni_retail.services.analytics import CustomerValue

    fake_customer = CustomerValue(
        customer_id=999, name="Test Customer", email="test@example.com",
        total_spent=5000.0, order_count=10, average_order_value=500.0,
    )
    monkeypatch.setattr(automation_rules.services, "high_value_customers", lambda _session, limit: [fake_customer])
    monkeypatch.setattr(automation_rules.services, "last_order_date", lambda _session, customer_id: date(2026, 1, 1))

    alerts = automation_rules.detect_customer_win_back_opportunities(session, today=date(2026, 6, 15))
    assert len(alerts) == 1
    assert alerts[0].supporting_data["days_since_last_order"] == (date(2026, 6, 15) - date(2026, 1, 1)).days
    assert alerts[0].severity == Severity.CRITICAL
