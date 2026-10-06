"""Lead analysis endpoint tests, including evaluation cases A-D."""

from __future__ import annotations

from tests.conftest import TENANT_A, TENANT_B, analyze_payload


def test_case_a_high_intent_pricing(client):
    body = analyze_payload(
        lead_id="lead_high",
        conversation=[
            {"role": "customer", "message": "We have 50 employees and we need pricing."},
            {"role": "agent", "message": "Sure, what's your timeline?"},
            {"role": "customer", "message": "Looking to buy this month."},
        ],
    )
    r = client.post("/api/v1/leads/analyze", headers={"X-Tenant-ID": TENANT_A}, json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["priority"] == "high"
    assert data["intent"] == "purchase"
    assert 60 <= data["lead_score"] <= 100
    assert data["do_not_contact"] is False
    assert data["follow_up_message"]


def test_case_b_low_intent_information(client):
    body = analyze_payload(
        lead_id="lead_low",
        conversation=[{"role": "customer", "message": "What does your product do?"}],
    )
    r = client.post("/api/v1/leads/analyze", headers={"X-Tenant-ID": TENANT_A}, json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["priority"] == "low"
    assert data["intent"] == "information"
    assert data["lead_score"] <= 30


def test_case_c_demo_request(client):
    body = analyze_payload(
        lead_id="lead_demo",
        conversation=[{"role": "customer", "message": "Can we schedule a demo tomorrow?"}],
    )
    r = client.post("/api/v1/leads/analyze", headers={"X-Tenant-ID": TENANT_A}, json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["intent"] == "demo"
    assert data["stage"] == "demo_requested"
    assert "demo" in data["next_best_action"].lower()


def test_case_d_opt_out(client):
    body = analyze_payload(
        lead_id="lead_stop",
        conversation=[{"role": "customer", "message": "STOP. Don't message me again."}],
    )
    r = client.post("/api/v1/leads/analyze", headers={"X-Tenant-ID": TENANT_A}, json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["do_not_contact"] is True
    assert data["follow_up_channel"] == "none"
    assert data["follow_up_message"] == ""


def test_missing_tenant_header(client):
    r = client.post("/api/v1/leads/analyze", json=analyze_payload())
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "tenant_header_missing"


def test_tenant_mismatch(client):
    body = analyze_payload(tenant_id=TENANT_A)
    r = client.post("/api/v1/leads/analyze", headers={"X-Tenant-ID": TENANT_B}, json=body)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "tenant_mismatch"


def test_invalid_request_body(client):
    r = client.post(
        "/api/v1/leads/analyze",
        headers={"X-Tenant-ID": TENANT_A},
        json={"tenant_id": TENANT_A},
    )
    assert r.status_code == 422


def test_get_analysis_after_analyze(client):
    body = analyze_payload(lead_id="lead_get")
    r = client.post("/api/v1/leads/analyze", headers={"X-Tenant-ID": TENANT_A}, json=body)
    assert r.status_code == 200
    r2 = client.get(
        "/api/v1/leads/lead_get/analysis", headers={"X-Tenant-ID": TENANT_A}
    )
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["lead_score"] >= 0
    assert "prompt_version" in data
    assert data["prompt_version"] == "lead_recovery_v1"


def test_get_analysis_not_found(client):
    r = client.get("/api/v1/leads/nonexistent/analysis", headers={"X-Tenant-ID": TENANT_A})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "analysis_not_found"
