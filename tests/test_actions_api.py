def _generate(client):
    response = client.post("/api/actions/generate")
    assert response.status_code == 200
    return response.json()


def test_generate_creates_proposals(fresh_client):
    created = _generate(fresh_client)
    assert len(created) > 0
    assert all(a["status"] == "proposed" for a in created)


def test_generate_is_idempotent(fresh_client):
    first = _generate(fresh_client)
    second = _generate(fresh_client)
    assert len(first) > 0
    assert second == []


def test_list_actions_returns_all(fresh_client):
    created = _generate(fresh_client)
    response = fresh_client.get("/api/actions")
    assert response.status_code == 200
    assert len(response.json()) == len(created)


def test_list_actions_filters_by_status(fresh_client):
    _generate(fresh_client)
    response = fresh_client.get("/api/actions", params={"status": "approved"})
    assert response.status_code == 200
    assert response.json() == []


def test_list_actions_rejects_unknown_status(fresh_client):
    response = fresh_client.get("/api/actions", params={"status": "not-a-real-status"})
    assert response.status_code == 400


def test_get_action_detail(fresh_client):
    created = _generate(fresh_client)
    action_id = created[0]["id"]
    response = fresh_client.get(f"/api/actions/{action_id}")
    assert response.status_code == 200
    assert response.json()["id"] == action_id


def test_get_action_detail_404_for_unknown_id(fresh_client):
    response = fresh_client.get("/api/actions/999999")
    assert response.status_code == 404


def test_approve_action_executes_and_returns_result(fresh_client):
    created = _generate(fresh_client)
    action_id = created[0]["id"]

    response = fresh_client.post(f"/api/actions/{action_id}/approve", json={"decided_by": "Brandon Fung"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("executed", "failed")
    assert body["decided_by"] == "Brandon Fung"
    assert body["execution_result"] is not None


def test_approve_with_edited_parameters(fresh_client):
    created = _generate(fresh_client)
    win_back = next(a for a in created if a["action_type"] == "win_back_offer")

    response = fresh_client.post(
        f"/api/actions/{win_back['id']}/approve",
        json={"decided_by": "Admin", "edited_parameters": {"customer_email": "override@example.com"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["edited_parameters"] == {"customer_email": "override@example.com"}
    assert "override@example.com" in body["execution_result"]["detail"]


def test_reject_action(fresh_client):
    created = _generate(fresh_client)
    action_id = created[0]["id"]

    response = fresh_client.post(f"/api/actions/{action_id}/reject", json={"decided_by": "Admin", "reason": "Skip"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["rejection_reason"] == "Skip"


def test_double_approve_is_rejected_with_409(fresh_client):
    created = _generate(fresh_client)
    action_id = created[0]["id"]
    fresh_client.post(f"/api/actions/{action_id}/approve", json={"decided_by": "Admin"})

    response = fresh_client.post(f"/api/actions/{action_id}/approve", json={"decided_by": "Admin"})
    assert response.status_code == 409


def test_approve_unknown_action_404(fresh_client):
    response = fresh_client.post("/api/actions/999999/approve", json={"decided_by": "Admin"})
    assert response.status_code == 404


def test_restock_action_can_fail_via_edited_quantity(fresh_client):
    created = _generate(fresh_client)
    restock = next(a for a in created if a["action_type"] == "restock_request")

    response = fresh_client.post(
        f"/api/actions/{restock['id']}/approve",
        json={"decided_by": "Admin", "edited_parameters": {"restock_quantity": 999999}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert "Supplier cannot fulfill" in body["execution_result"]["failure_reason"]
