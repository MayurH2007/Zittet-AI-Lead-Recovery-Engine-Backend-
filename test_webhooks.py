"""Webhook endpoint tests, including idempotency (Case E)."""

from __future__ import annotations

from tests.conftest import TENANT_A, TENANT_B, webhook_payload


def test_webhook_accepted(client):
    body = webhook_payload(event_id="evt_1", lead_id="lead_wh")
    r = client.post("/api/v1/webhooks/leads", headers={"X-Tenant-ID": TENANT_A}, json=body)
    assert r.status_code == 202, r.text
    data = r.json()
    assert data["event_id"] == "evt_1"
    assert data["duplicate"] is False
    assert data["status"] == "received"


def test_case_e_duplicate_webhook_is_idempotent(client):
    body = webhook_payload(event_id="evt_dup", lead_id="lead_dup")
    r1 = client.post("/api/v1/webhooks/leads", headers={"X-Tenant-ID": TENANT_A}, json=body)
    assert r1.status_code == 202
    r2 = client.post("/api/v1/webhooks/leads", headers={"X-Tenant-ID": TENANT_A}, json=body)
    assert r2.status_code == 200
    data = r2.json()
    assert data["duplicate"] is True
    assert data["event_id"] == "evt_dup"


def test_webhook_tenant_mismatch(client):
    body = webhook_payload(event_id="evt_mismatch", tenant_id=TENANT_A)
    r = client.post("/api/v1/webhooks/leads", headers={"X-Tenant-ID": TENANT_B}, json=body)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "tenant_mismatch"


def test_webhook_missing_tenant_header(client):
    r = client.post("/api/v1/webhooks/leads", json=webhook_payload())
    assert r.status_code == 400


def test_webhook_invalid_payload(client):
    r = client.post(
        "/api/v1/webhooks/leads",
        headers={"X-Tenant-ID": TENANT_A},
        json={"event_id": "x"},
    )
    assert r.status_code == 422
