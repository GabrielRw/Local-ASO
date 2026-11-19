"""Country pricing: bundled PPP data, suggestion maths, and App Store Connect writes (mocked)."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from local_aso_tracker.apple.app_store_connect import AppStoreConnectClient
from local_aso_tracker.apple.app_store_pricing import PricePoint
from local_aso_tracker.config import Settings
from local_aso_tracker.database import run_migrations, session_scope
from local_aso_tracker.models import App, PricePushEvent
from local_aso_tracker.repositories.data import add_app, add_storefront
from local_aso_tracker.services import pricing

APP = 6756268723
ASC = "https://api.appstoreconnect.apple.com"


@pytest.fixture
def app_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path / "data"))
    run_migrations()
    with session_scope() as session:
        add_app(session, "Spiritual Couple", APP)
        session.query(App).filter_by(apple_app_id=APP).one().bundle_id = "com.example.couple"
        for code in ("us", "fr", "in"):
            add_storefront(session, code)


def _client(
    tmp_path: Path, handler: Callable[[httpx.Request], httpx.Response]
) -> AppStoreConnectClient:
    key_path = tmp_path / "AuthKey_TEST.p8"
    key_path.write_bytes(
        ec.generate_private_key(ec.SECP256R1()).private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    os.chmod(key_path, 0o600)
    settings = Settings(
        app_store_connect_issuer_id="issuer-test",
        app_store_connect_key_id="key-test",
        app_store_connect_key_path=str(key_path),
    )
    client = AppStoreConnectClient(
        settings, client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    client._sleep = lambda _seconds: None  # type: ignore[method-assign]
    return client


def _price(price_id: str, point: str, territory: str, start: str | None = None) -> dict[str, Any]:
    return {
        "type": "appPrices",
        "id": price_id,
        "attributes": {"startDate": start, "endDate": None},
        "relationships": {
            "appPricePoint": {"data": {"type": "appPricePoints", "id": point}},
            "territory": {"data": {"type": "territories", "id": territory}},
        },
    }


def _point(point: str, price: str) -> dict[str, Any]:
    return {"type": "appPricePoints", "id": point, "attributes": {"customerPrice": price}}


def test_bundled_ppp_table_covers_major_territories() -> None:
    ratios = pricing.ppp_ratios()
    assert ratios["USA"] == pytest.approx(1.0)
    for territory in ("FRA", "DEU", "JPN", "BRA", "IND", "GBR", "MEX", "TUR"):
        assert 0.05 < ratios[territory] < 3
    assert ratios["IND"] < ratios["FRA"] < ratios["USA"]
    assert pricing.iso3_for("fr") == "FRA"
    meta = pricing.ppp_meta()
    assert "World Bank" in str(meta["source"])
    assert int(meta["countries"]) > 150  # type: ignore[call-overload]


def test_suggestions_scale_equalized_prices_and_snap_to_real_tiers() -> None:
    ladder = [
        PricePoint(f"usa-{price}", "USA", price) for price in (0.0, 0.99, 2.99, 4.99, 6.99, 9.99)
    ]
    rates = {"USA": 1.0, "FRA": 0.95, "IND": 85.0, "CHE": 0.9, "XXX": 1.0}
    calls: list[str] = []

    def equalize(point: PricePoint) -> dict[str, PricePoint]:
        calls.append(point.id)
        return {
            territory: PricePoint(
                f"{territory}-{point.customer_price}",
                territory,
                round(point.customer_price * rate, 2),
            )
            for territory, rate in rates.items()
        }

    rows = pricing.suggest_prices(
        base=ladder[-1],
        base_ladder=ladder,
        equalize=equalize,
        current={"USA": ladder[-1], "FRA": PricePoint("FRA-manual", "FRA", 10.99)},
        territories=["USA", "FRA", "IND", "CHE", "XXX", "ZZZ"],
        ratios={"USA": 1.0, "FRA": 0.74, "IND": 0.24, "CHE": 1.1},
    )
    by = {row["territory"]: row for row in rows}
    assert set(by) == {"FRA", "IND", "CHE", "XXX"}  # base and unsold territories are skipped
    # France: 9.99 x 0.74 = 7.39 -> nearest US tier 6.99 -> France's equalization of 6.99.
    assert by["FRA"]["suggestedPointId"] == "FRA-6.99"
    assert by["FRA"]["currentPrice"] == 10.99 and by["FRA"]["manual"] is True
    assert by["FRA"]["changePercent"] == pytest.approx(round((6.64 / 10.99 - 1) * 100, 1))
    # India is clamped to the 0.35 floor: 3.50 -> tier 2.99.
    assert by["IND"]["ratio"] == 0.35 and by["IND"]["suggestedPointId"] == "IND-2.99"
    # Switzerland is above the US but capped at the 1.0 ceiling: its equalized price.
    assert by["CHE"]["suggestedPointId"] == "CHE-9.99"
    # No PPP data: no suggestion, nothing invented.
    assert by["XXX"]["suggestedPrice"] is None and by["XXX"]["pppRatio"] is None
    assert sorted(calls) == sorted(["usa-9.99", "usa-6.99", "usa-2.99"])  # one call per tier

    with pytest.raises(ValueError):
        pricing.suggest_prices(
            base=ladder[-1], base_ladder=ladder, equalize=equalize, current={},
            territories=[], ratios={}, floor=0.8, ceiling=0.5,
        )  # fmt: skip


def _schedule_handler(
    writes: list[httpx.Request], *, write_status: int = 201
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST":
            writes.append(request)
            if write_status >= 400:
                return httpx.Response(write_status, json={"errors": [{"detail": "Forbidden"}]})
            return httpx.Response(201, json={"data": {"id": "new"}})
        if path == "/v1/apps":
            return httpx.Response(200, json={"data": [{"type": "apps", "id": "asc-1"}]})
        if path.endswith("/baseTerritory"):
            return httpx.Response(200, json={"data": {"type": "territories", "id": "USA"}})
        if path.endswith("/automaticPrices"):
            return httpx.Response(200, json={"data": []})
        if path.endswith("/manualPrices"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        _price("p1", "pt-usa", "USA"),
                        _price("p2", "pt-deu", "DEU", "2020-01-01"),
                        _price("p3", "pt-fra-old", "FRA", "2021-05-01"),
                        _price("p4", "pt-fra-future", "FRA", "2099-01-01"),
                    ],
                    "included": [
                        _point("pt-usa", "9.99"),
                        _point("pt-deu", "9.99"),
                        _point("pt-fra-old", "10.99"),
                        _point("pt-fra-future", "12.99"),
                    ],
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    return handler


def test_app_push_keeps_untouched_manual_prices_and_logs_before(
    app_db: None, tmp_path: Path
) -> None:
    writes: list[httpx.Request] = []
    result = pricing.push_prices(
        APP,
        kind="app",
        item_id="asc-1",
        item_name="App price",
        changes=[
            {"territory": "FRA", "pricePointId": "pt-fra-new", "price": 6.99, "currency": "EUR"}
        ],
        client=_client(tmp_path, _schedule_handler(writes)),
    )
    assert result == {"results": [{"territory": "FRA", "error": None}]}
    assert len(writes) == 1 and writes[0].url.path == "/v1/appPriceSchedules"
    body = json.loads(writes[0].content)
    points = {
        entry["relationships"]["appPricePoint"]["data"]["id"]: entry["attributes"]["startDate"]
        for entry in body["included"]
    }
    # The replaced current French price is gone; everything else is sent back.
    assert points == {
        "pt-usa": None,
        "pt-deu": None,
        "pt-fra-future": "2099-01-01",
        "pt-fra-new": None,
    }
    assert body["data"]["relationships"]["baseTerritory"]["data"]["id"] == "USA"
    assert body["data"]["relationships"]["app"]["data"]["id"] == "asc-1"
    assert len(body["data"]["relationships"]["manualPrices"]["data"]) == 4
    with session_scope() as session:
        event = session.query(PricePushEvent).one()
        assert (event.territory, event.before_price, event.after_price, event.status) == (
            "FRA",
            "10.99",
            "6.99",
            "success",
        )


def test_base_territory_changes_are_refused_before_writing(app_db: None, tmp_path: Path) -> None:
    writes: list[httpx.Request] = []
    with pytest.raises(ValueError, match="base territory"):
        pricing.push_prices(
            APP,
            kind="app",
            item_id="asc-1",
            item_name="App price",
            changes=[{"territory": "USA", "pricePointId": "pt-x", "price": 4.99}],
            client=_client(tmp_path, _schedule_handler(writes)),
        )
    assert writes == []


def test_permission_refusals_are_explained_and_logged(app_db: None, tmp_path: Path) -> None:
    writes: list[httpx.Request] = []
    result = pricing.push_prices(
        APP,
        kind="app",
        item_id="asc-1",
        item_name="App price",
        changes=[{"territory": "FRA", "pricePointId": "pt-fra-new", "price": 6.99}],
        client=_client(tmp_path, _schedule_handler(writes, write_status=403)),
    )
    assert result["results"][0]["error"] == pricing.PERMISSION_MESSAGE  # type: ignore[index]
    with session_scope() as session:
        assert session.query(PricePushEvent).one().status == "failed"

    def forbidden(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"errors": [{"detail": "Forbidden"}]})

    with pytest.raises(ValueError, match="Admin or App Manager"):
        pricing.list_items(APP, client=_client(tmp_path, forbidden))


def test_subscription_prices_preserve_existing_subscribers_by_default(
    app_db: None, tmp_path: Path
) -> None:
    writes: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            writes.append(request)
            return httpx.Response(201, json={"data": {"id": "price"}})
        if request.url.path == "/v1/subscriptions/sub-1/prices":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "type": "subscriptionPrices",
                            "id": "s1",
                            "attributes": {"startDate": None},
                            "relationships": {
                                "subscriptionPricePoint": {
                                    "data": {"type": "subscriptionPricePoints", "id": "sp-ind"}
                                },
                                "territory": {"data": {"type": "territories", "id": "IND"}},
                            },
                        }
                    ],
                    "included": [
                        {
                            "type": "subscriptionPricePoints",
                            "id": "sp-ind",
                            "attributes": {"customerPrice": "799"},
                        }
                    ],
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    result = pricing.push_prices(
        APP,
        kind="subscription",
        item_id="sub-1",
        item_name="Premium monthly",
        changes=[
            {"territory": "IND", "pricePointId": "sp-ind-new", "price": 299, "currency": "INR"}
        ],
        client=_client(tmp_path, handler),
    )
    assert result == {"results": [{"territory": "IND", "error": None}]}
    body = json.loads(writes[0].content)
    assert writes[0].url.path == "/v1/subscriptionPrices"
    assert body["data"]["attributes"] == {"startDate": None, "preserveCurrentPrice": True}
    assert body["data"]["relationships"]["territory"]["data"]["id"] == "IND"
    with session_scope() as session:
        event = session.query(PricePushEvent).one()
        assert (event.before_price, event.after_price, event.currency) == ("799.0", "299.0", "INR")


def test_suggest_route_reads_only(app_db: None, tmp_path: Path) -> None:
    """The suggestion flow issues GETs only and reports tracked territories."""

    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        path = request.url.path
        if path == "/v1/territories":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"type": "territories", "id": code, "attributes": {"currency": currency}}
                        for code, currency in (("USA", "USD"), ("FRA", "EUR"), ("IND", "INR"))
                    ]
                },
            )
        if path.endswith("/baseTerritory"):
            return httpx.Response(200, json={"data": {"type": "territories", "id": "USA"}})
        if path.endswith("/manualPrices"):
            return httpx.Response(
                200,
                json={
                    "data": [_price("p1", "pt-usa", "USA")],
                    "included": [_point("pt-usa", "4.99")],
                },
            )
        if path.endswith("/automaticPrices"):
            return httpx.Response(
                200,
                json={
                    "data": [_price("a1", "pt-fra", "FRA"), _price("a2", "pt-ind", "IND")],
                    "included": [_point("pt-fra", "4.99"), _point("pt-ind", "449")],
                },
            )
        if path == "/v1/apps/asc-1/appPricePoints":
            return httpx.Response(
                200,
                json={
                    "data": [
                        _point("pt-usa-199", "1.99"),
                        _point("pt-usa", "4.99"),
                        _point("pt-usa-299", "2.99"),
                    ]
                },
            )
        if path.startswith("/v3/appPricePoints/"):
            point = path.split("/")[3]
            prices = {
                "pt-usa": ("4.99", "449"),
                "pt-usa-299": ("2.99", "299"),
                "pt-usa-199": ("1.99", "199"),
            }
            fra, ind = prices[point]
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            **_point(f"{point}-fra", fra),
                            "relationships": {"territory": {"data": {"id": "FRA"}}},
                        },
                        {
                            **_point(f"{point}-ind", ind),
                            "relationships": {"territory": {"data": {"id": "IND"}}},
                        },
                    ]
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    result = pricing.suggestions(
        APP, kind="app", item_id="asc-1", client=_client(tmp_path, handler)
    )
    assert set(methods) == {"GET"}
    rows = {row["territory"]: row for row in result["rows"]}  # type: ignore[attr-defined]
    assert set(rows) == {"FRA", "IND"}
    assert rows["FRA"]["currency"] == "EUR"
    assert rows["IND"]["suggestedPointId"] == "pt-usa-199-ind"  # 4.99 x 0.35 = 1.75 -> 1.99 tier
    assert result["baseTerritory"] == "USA" and result["basePrice"] == 4.99
