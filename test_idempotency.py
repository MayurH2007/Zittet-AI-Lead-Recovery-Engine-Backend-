"""Idempotency tests (Case E at the repository layer)."""

from __future__ import annotations

import pytest

from app.repositories.webhook_repository import WebhookRepository
from app.utils.idempotency import reserve_event


@pytest.mark.asyncio
async def test_reserve_event_inserts_once(sessionmaker):
    async with sessionmaker() as session:
        repo = WebhookRepository(session)
        event, duplicate = await reserve_event(
            repo,
            tenant_id="t1",
            event_id="e1",
            event_type="lead.updated",
            payload="{}",
        )
        await session.commit()
        assert duplicate is False
        assert event is not None
        assert event.event_id == "e1"


@pytest.mark.asyncio
async def test_reserve_event_detects_duplicate(sessionmaker):
    async with sessionmaker() as session:
        repo = WebhookRepository(session)
        await reserve_event(
            repo, tenant_id="t1", event_id="e2", event_type="lead.updated", payload="{}"
        )
        await session.commit()

    async with sessionmaker() as session:
        repo = WebhookRepository(session)
        event, duplicate = await reserve_event(
            repo, tenant_id="t1", event_id="e2", event_type="lead.updated", payload="{}"
        )
        await session.commit()
        assert duplicate is True
        assert event is not None
        assert event.event_id == "e2"


@pytest.mark.asyncio
async def test_different_tenants_same_event_id_both_succeed(sessionmaker):
    """event_id uniqueness is per (tenant_id, event_id)."""
    async with sessionmaker() as session:
        repo = WebhookRepository(session)
        _, dup_a = await reserve_event(
            repo, tenant_id="tA", event_id="shared", event_type="x", payload="{}"
        )
        _, dup_b = await reserve_event(
            repo, tenant_id="tB", event_id="shared", event_type="x", payload="{}"
        )
        await session.commit()
        assert dup_a is False
        assert dup_b is False
