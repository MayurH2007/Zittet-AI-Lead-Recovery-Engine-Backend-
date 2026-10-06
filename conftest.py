"""Shared pytest fixtures.

Strategy:
  - A file-based SQLite DB (via aiosqlite) is created once per test session and
    torn down at the end. This lets the async engine + background tasks share
    state across requests within a single test.
  - The FastAPI `get_session` dependency is overridden to yield sessions from
    this test engine.
  - The MockLLMProvider is installed as the LLM provider so tests never touch
    the network.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Ensure a clean settings + provider state before imports.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")  # overridden below
os.environ.setdefault("OPENAI_API_KEY", "")  # force mock provider

from app.core import database as db_module  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.llm import set_llm_provider  # noqa: E402
from app.llm.mock_provider import MockLLMProvider  # noqa: E402
from app.main import app  # noqa: E402
from app.models.base import Base  # noqa: E402


# ---------------------------------------------------------------------------
# Engine + session
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_db_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    """A per-session file-based SQLite URL."""
    db_file = tmp_path_factory.mktemp("db") / "test.db"
    return f"sqlite+aiosqlite:///{db_file}"


@pytest.fixture(scope="session")
async def engine(test_db_url: str):
    """Create the test engine + schema once per session."""
    eng = create_async_engine(test_db_url, echo=False, future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture(scope="session")
def sessionmaker(engine):
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def _reset_provider():
    """Ensure each test starts with the standard mock provider."""
    set_llm_provider(MockLLMProvider(behavior="valid"))
    yield
    set_llm_provider(MockLLMProvider(behavior="valid"))


@pytest.fixture(autouse=True)
async def _truncate_tables(engine):
    """Clean all tables before each test for isolation."""
    from sqlalchemy import text

    async with engine.begin() as conn:
        for table in ["webhook_events", "analyses", "conversations", "leads"]:
            await conn.execute(text(f"DELETE FROM {table}"))


@pytest.fixture()
def client(sessionmaker) -> TestClient:
    """FastAPI TestClient wired to the test DB."""

    async def _get_session():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[db_module.get_session] = _get_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


TENANT_A = "business_001"
TENANT_B = "business_002"


def analyze_payload(
    *,
    tenant_id: str = TENANT_A,
    lead_id: str = "lead_1024",
    customer_name: str = "Arun Kumar",
    customer_phone: str = "+919876543210",
    source: str = "whatsapp",
    status: str = "contacted",
    conversation: list[dict] | None = None,
) -> dict:
    """Build a valid analyze request body."""
    if conversation is None:
        conversation = [
            {"role": "customer", "message": "I am interested in your CRM."},
            {"role": "agent", "message": "How many users do you need?"},
            {"role": "customer", "message": "Around 25 users. What is the pricing?"},
        ]
    return {
        "tenant_id": tenant_id,
        "lead_id": lead_id,
        "customer": {"name": customer_name, "phone": customer_phone},
        "lead": {
            "source": source,
            "status": status,
            "created_at": "2026-09-20",
            "last_contacted_at": "2026-09-25",
        },
        "conversation": conversation,
    }


def webhook_payload(
    *,
    tenant_id: str = TENANT_A,
    event_id: str = "evt_123",
    lead_id: str = "lead_1024",
    conversation: list[dict] | None = None,
) -> dict:
    if conversation is None:
        conversation = [
            {"role": "customer", "message": "50 employees and we need pricing."},
        ]
    return {
        "event_id": event_id,
        "event_type": "lead.updated",
        "tenant_id": tenant_id,
        "lead_id": lead_id,
        "customer": {"name": "Arun Kumar", "phone": "+919876543210"},
        "lead": {
            "source": "whatsapp",
            "status": "contacted",
            "created_at": "2026-09-20",
            "last_contacted_at": "2026-09-25",
        },
        "conversation": conversation,
    }
