"""Local MCP server and read-only query tests."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from local_aso_tracker.database import run_migrations, session_scope
from local_aso_tracker.mcp_server import MCPRuntime
from local_aso_tracker.models import RankCheck
from local_aso_tracker.repositories.data import (
    list_targets,
    save_listing_metadata,
    seed_catalog,
    seed_targets,
)
from local_aso_tracker.services import mcp_queries


@pytest.fixture
def mcp_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    with session_scope() as session:
        seed_catalog(session)
        seed_targets(session)
        target = list_targets(
            session,
            apple_id=6771773264,
            country="us",
            keyword="learn astrology",
        )[0]
        session.add(
            RankCheck(
                tracking_target_id=target.id,
                checked_at=datetime.now(UTC),
                rank=3,
                found=True,
                result_limit=200,
                response_time_ms=10,
                status="success",
            )
        )
        save_listing_metadata(
            session,
            6771773264,
            "us",
            name="Learn Astrology: AstroLingo",
            subtitle="Birth chart lessons",
            keyword_field="learn astrology, birth chart, astrology",
        )


def test_mcp_queries_are_read_only_database_views(mcp_database: None) -> None:
    apps = mcp_queries.list_apps()
    assert apps["count"] == 1
    rankings = mcp_queries.get_keyword_rankings(6771773264, "us", "iphone", "learn astrology")
    assert rankings["count"] == 1
    assert rankings["rankings"][0]["rank"] == 3
    summary = mcp_queries.get_app_summary(6771773264, "us")
    assert summary["summary"]["top_10"] == 1  # type: ignore[index]
    coverage = mcp_queries.get_listing_coverage(6771773264, "us")
    assert coverage["hasMetadata"] is True
    assert coverage["analysis"]["ranked_keywords"] == 1  # type: ignore[index]


@pytest.mark.asyncio
async def test_streamable_http_mcp_endpoint_exposes_tools(mcp_database: None) -> None:
    runtime = MCPRuntime(port=_unused_port())
    assert runtime.start()
    try:
        async with (
            streamable_http_client(runtime.url) as (read, write, _),
            ClientSession(read, write) as client,
        ):
            await client.initialize()
            tools = await client.list_tools()
            assert {tool.name for tool in tools.tools} == {
                "add_app",
                "add_keywords",
                "get_app_summary",
                "get_keyword_rankings",
                "get_listing_coverage",
                "list_apps",
                "list_storefronts",
                "run_checks",
                "stop_tracking_keywords",
            }
            result = await client.call_tool("list_apps", {})
            assert result.isError is False
            assert result.structuredContent is not None
            assert result.structuredContent["count"] == 1
            added = await client.call_tool(
                "add_keywords",
                {
                    "apple_app_id": 6771773264,
                    "keywords": ["mcp action keyword"],
                    "countries": ["us"],
                    "check_now": False,
                },
            )
            assert added.isError is False
            assert added.structuredContent is not None
            assert added.structuredContent["targetsCreated"] == 1
            with session_scope() as session:
                targets = list_targets(
                    session,
                    apple_id=6771773264,
                    country="us",
                    keyword="mcp action keyword",
                    active_only=True,
                )
            assert len(targets) == 1
    finally:
        runtime.stop()


def _unused_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
