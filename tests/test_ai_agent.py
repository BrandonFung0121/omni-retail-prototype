from datetime import date

import pytest

from omni_retail.ai import agent
from omni_retail.ai.intents import Intent, classify_intent
from omni_retail.ai.synthesis import get_synthesizer


@pytest.mark.parametrize(
    "question,expected",
    [
        ("Why did revenue increase or decrease this month?", Intent.REVENUE_EXPLANATION),
        ("Which products are performing best or worst?", Intent.PRODUCT_PERFORMANCE),
        ("Which products should be restocked first?", Intent.RESTOCK_PRIORITY),
        ("Which customers are most valuable?", Intent.TOP_CUSTOMERS),
        ("Which high-value customers are at risk of becoming inactive?", Intent.CHURN_RISK),
        ("Are there any unusual expense patterns?", Intent.EXPENSE_ANOMALIES),
        ("Is website traffic converting effectively?", Intent.TRAFFIC_CONVERSION),
        ("What are the most important business issues right now?", Intent.BUSINESS_ISSUES_SUMMARY),
        ("what is the meaning of life", Intent.UNKNOWN),
        ("", Intent.UNKNOWN),
    ],
)
def test_classify_intent(question, expected):
    assert classify_intent(question) == expected


def test_classify_intent_is_case_insensitive():
    assert classify_intent("WHICH PRODUCTS SHOULD BE RESTOCKED FIRST?") == Intent.RESTOCK_PRIORITY


@pytest.mark.parametrize(
    "question",
    [
        "Why did revenue increase or decrease?",
        "Which products are performing best or worst?",
        "Which products should be restocked first?",
        "Which customers are most valuable?",
        "Which high-value customers are at risk of becoming inactive?",
        "Are there unusual expense patterns?",
        "Is website traffic converting effectively?",
        "What are the most important business issues right now?",
    ],
)
def test_answer_question_produces_grounded_response(session, question):
    response = agent.answer_question(session, question)

    assert response.confidence == "high"
    assert response.intent != Intent.UNKNOWN.value
    assert response.answer
    assert response.generated_by == "template"
    # Every metric value must already be JSON-primitive (str/int/float/bool/list/dict/None) --
    # this is what the API's dict[str, Any] response model will actually serialize.
    import json

    json.dumps(response.supporting_metrics)


def test_unknown_question_gets_helpful_fallback_not_an_error(session):
    response = agent.answer_question(session, "what is the meaning of life")

    assert response.intent == Intent.UNKNOWN.value
    assert response.confidence == "low"
    assert "restock" in response.answer.lower() or "revenue" in response.answer.lower()


def test_empty_question_is_handled_gracefully(session):
    response = agent.answer_question(session, "   ")
    assert response.intent == Intent.UNKNOWN.value
    assert response.answer


def test_retrieval_failure_is_caught_and_returns_low_confidence(session, monkeypatch):
    def boom(_session, _today):
        raise RuntimeError("simulated failure")

    monkeypatch.setitem(agent._RETRIEVERS, Intent.REVENUE_EXPLANATION, boom)

    response = agent.answer_question(session, "Why did revenue change?")
    assert response.confidence == "low"
    assert response.answer
    assert response.intent == Intent.REVENUE_EXPLANATION.value


def test_restock_priority_answer_matches_inventory_service(session):
    from omni_retail import services

    response = agent.answer_question(session, "Which products should be restocked first?")
    flagged = services.low_stock_products(session)

    assert response.supporting_metrics["out_of_stock_count"] + response.supporting_metrics["low_stock_count"] == len(flagged)
    assert len(response.related_alert_ids) == len(flagged)


def test_business_issues_summary_matches_alert_engine(session):
    from omni_retail.automation import run_all_rules

    response = agent.answer_question(session, "What are the most important business issues right now?")
    alerts = run_all_rules(session)

    assert response.supporting_metrics["total_alerts"] == len(alerts)
    assert len(response.related_alert_ids) == len(alerts)


def test_revenue_explanation_reflects_actual_pct_change(session):
    from omni_retail import services
    from omni_retail.automation import config as automation_config
    from datetime import timedelta

    today = date.today()
    start = today - timedelta(days=automation_config.REVENUE_PERIOD_DAYS - 1)
    from omni_retail.automation.rules import prior_period

    prev_start, prev_end = prior_period(start, today)
    current = services.revenue(session, start, today)
    previous = services.revenue(session, prev_start, prev_end)
    expected_pct = round((current - previous) / previous * 100, 1)

    response = agent.answer_question(session, "Why did revenue increase or decrease?")
    assert response.supporting_metrics["pct_change"] == expected_pct


def test_unknown_intent_synthesis_lists_example_topics():
    result = get_synthesizer().synthesize("gibberish", Intent.UNKNOWN, {})
    assert result.answer
    assert result.recommended_actions == []
