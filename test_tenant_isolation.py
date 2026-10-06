"""Tenant isolation tests.

Tenant A creates a lead + analysis. Tenant B must NOT be able to retrieve it.
"""

from __future__ import annotations

from tests.conftest import TENANT_A, TENANT_B, analyze_payload


def test_tenant_b_cannot_read_tenant_a_analysis(client):
    body = analyze_payload(lead_id="lead_iso", tenant_id=TENANT_A)
    r = client.post("/api/v1/leads/analyze", headers={"X-Tenant-ID": TENANT_A}, json=body)
    assert r.status_code == 200

    # Tenant B tries to read tenant A's analysis using the same external lead id.
    r2 = client.get(
        "/api/v1/leads/lead_iso/analysis", headers={"X-Tenant-ID": TENANT_B}
    )
    assert r2.status_code == 404
    assert r2.json()["error"]["code"] == "analysis_not_found"


def test_tenant_b_cannot_get_followup(client):
    body = analyze_payload(lead_id="lead_iso2", tenant_id=TENANT_A)
    r = client.post("/api/v1/leads/analyze", headers={"X-Tenant-ID": TENANT_A}, json=body)
    assert r.status_code == 200

    r2 = client.post(
        "/api/v1/leads/lead_iso2/follow-up", headers={"X-Tenant-ID": TENANT_B}
    )
    assert r2.status_code == 404


def test_same_external_lead_id_different_tenants_are_isolated(client):
    """Two tenants can each have a lead with the same external id."""
    for tenant in (TENANT_A, TENANT_B):
        body = analyze_payload(lead_id="shared_id", tenant_id=tenant)
        r = client.post("/api/v1/leads/analyze", headers={"X-Tenant-ID": tenant}, json=body)
        assert r.status_code == 200

    # Each tenant reads its own analysis.
    for tenant in (TENANT_A, TENANT_B):
        r = client.get(
            "/api/v1/leads/shared_id/analysis", headers={"X-Tenant-ID": tenant}
        )
        assert r.status_code == 200
