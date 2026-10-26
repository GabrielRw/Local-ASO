"""Optional local MCP endpoint for ASO tracker queries and actions."""

from __future__ import annotations

import logging
import socket
import threading
import time

import uvicorn
from mcp.server.fastmcp import FastMCP

from local_aso_tracker.services import mcp_actions, mcp_queries

logger = logging.getLogger(__name__)


def create_mcp_server(*, host: str = "127.0.0.1", port: int = 8766) -> FastMCP:
    """Build the local MCP server and register read and action tools."""

    server = FastMCP(
        "Local ASO Tracker",
        instructions=(
            "Access and controlled actions for the user's local App Store keyword tracker. "
            "Data is stored in local SQLite. Actions may update local tracking targets and "
            "call Apple's public iTunes Search API; no hosted ASO service is used."
        ),
        host=host,
        port=port,
        streamable_http_path="/mcp",
        stateless_http=True,
    )

    @server.tool()
    def list_apps(include_inactive: bool = False) -> dict[str, object]:
        """List locally configured apps and their numerical App Store IDs."""

        return mcp_queries.list_apps(include_inactive)

    @server.tool()
    def list_storefronts(include_inactive: bool = False) -> dict[str, object]:
        """List App Store countries accepted by this local tracker."""

        return mcp_queries.list_storefronts(include_inactive)

    @server.tool()
    def get_keyword_rankings(
        apple_app_id: int,
        country: str,
        device: str = "iphone",
        keyword: str | None = None,
        limit: int = 100,
    ) -> dict[str, object]:
        """Get latest keyword ranks, rating-based estimates, and Top 5 competitors."""

        return mcp_queries.get_keyword_rankings(
            apple_app_id,
            country,
            device,
            keyword,
            limit,
        )

    @server.tool()
    def get_app_summary(
        apple_app_id: int,
        country: str,
        device: str = "iphone",
    ) -> dict[str, object]:
        """Get visibility totals and 7-day/30-day changes for an app and storefront."""

        return mcp_queries.get_app_summary(apple_app_id, country, device)

    @server.tool()
    def get_listing_coverage(
        apple_app_id: int,
        country: str,
        device: str = "iphone",
    ) -> dict[str, object]:
        """Get saved listing metadata matching and ranking coverage."""

        return mcp_queries.get_listing_coverage(apple_app_id, country, device)

    @server.tool()
    def add_app(apple_app_id: int, country: str = "us") -> dict[str, object]:
        """Add or restore an app using Apple's public lookup data. Mutates local data."""

        return mcp_actions.add_app(apple_app_id, country)

    @server.tool()
    def add_keywords(
        apple_app_id: int,
        keywords: list[str],
        countries: list[str],
        devices: list[str] | None = None,
        check_now: bool = True,
    ) -> dict[str, object]:
        """Add tracking keywords across markets and devices. Mutates local data."""

        return mcp_actions.add_keywords(
            apple_app_id,
            keywords,
            countries,
            devices=devices or ["iphone"],
            check_now=check_now,
        )

    @server.tool()
    def run_checks(
        apple_app_id: int | None = None,
        countries: list[str] | None = None,
        devices: list[str] | None = None,
        keyword: str | None = None,
    ) -> dict[str, object]:
        """Refresh ranks for a bounded target selection using Apple's public API."""

        return mcp_actions.run_rank_checks(
            apple_app_id=apple_app_id,
            countries=countries,
            devices=devices,
            keyword=keyword,
        )

    @server.tool()
    def stop_tracking_keywords(
        apple_app_id: int,
        keywords: list[str],
        countries: list[str] | None = None,
        devices: list[str] | None = None,
    ) -> dict[str, object]:
        """Stop tracking matching keywords while preserving rank history. Mutates local data."""

        return mcp_actions.stop_tracking_keywords(
            apple_app_id,
            keywords,
            countries=countries,
            devices=devices,
        )

    return server


class MCPRuntime:
    """Run the streamable HTTP MCP server in a background thread."""

    def __init__(self, *, host: str = "127.0.0.1", port: int = 8766) -> None:
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("MCP server must bind to a loopback host")
        self.host = host
        self.port = port
        self._server = create_mcp_server(host=host, port=port)
        self._uvicorn: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        host = "127.0.0.1" if self.host == "localhost" else self.host
        return f"http://{host}:{self.port}/mcp"

    def start(self, *, timeout: float = 5.0) -> bool:
        """Start the MCP endpoint and wait briefly for Uvicorn readiness."""

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((self.host, self.port))
            except OSError:
                return False
        config = uvicorn.Config(
            self._server.streamable_http_app(),
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
            lifespan="on",
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(
            target=server.run,
            name="local-aso-mcp",
            daemon=True,
        )
        thread.start()
        self._uvicorn = server
        self._thread = thread
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if server.started:
                return True
            if not thread.is_alive():
                return False
            time.sleep(0.05)
        self.stop()
        return False

    def stop(self) -> None:
        """Stop the MCP server if it is running."""

        if self._uvicorn is not None:
            self._uvicorn.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._uvicorn = None
        self._thread = None
