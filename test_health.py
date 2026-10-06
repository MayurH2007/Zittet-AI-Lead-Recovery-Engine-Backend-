"""Health endpoint tests."""

from __future__ import annotations


def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "zizzet-ai-lead-recovery"
    assert "status" in body
    assert "timestamp" in body


def test_health_db_checked(client):
    response = client.get("/health")
    body = response.json()
    # DB is the test SQLite engine => should be ok or degraded-but-present.
    assert "database" in body
