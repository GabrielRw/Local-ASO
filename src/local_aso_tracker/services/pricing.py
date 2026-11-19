"""Country pricing: purchasing-power suggestions reviewed in the dashboard, then pushed.

Suggestions start from Apple's own equalized price for each territory (the base price
converted at Apple's rates, taxes included) and scale it by the World Bank price level
ratio relative to the base territory, kept between a floor and a ceiling. The result is
snapped to a real Apple price point: the territory's equalization of the nearest base
tier. The PPP table is bundled static data (``services/data/ppp.json``); nothing is
fetched from the World Bank at runtime.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

from sqlalchemy import select

from local_aso_tracker.apple.app_store_connect import AppStoreConnectClient, AppStoreConnectError
from local_aso_tracker.apple.app_store_pricing import (
    AppStoreConnectPricing,
    ItemKind,
    PricedItem,
    PricePoint,
)
from local_aso_tracker.config import load_settings
from local_aso_tracker.database import session_scope
from local_aso_tracker.models import App, PricePushEvent, Storefront

PPP_PATH = Path(__file__).parent / "data" / "ppp.json"
DEFAULT_FLOOR = 0.35
DEFAULT_CEILING = 1.0
PERMISSION_MESSAGE = (
    "This App Store Connect key isn't allowed to change prices. Use a key with the Admin "
    "or App Manager role."
)


@cache
def ppp_table() -> dict[str, Any]:
    with PPP_PATH.open(encoding="utf-8") as handle:
        loaded: dict[str, Any] = json.load(handle)
    return loaded


def ppp_ratios() -> dict[str, float]:
    """Price level ratio (US = 1) by App Store territory id (ISO 3166 alpha-3)."""

    return {
        str(row["iso3"]): float(row["ratio"])
        for row in ppp_table()["countries"].values()
        if row.get("iso3")
    }


def iso3_for(country_code: str) -> str | None:
    row = ppp_table()["countries"].get(country_code.upper())
    return str(row["iso3"]) if row and row.get("iso3") else None


def ppp_meta() -> dict[str, object]:
    table = ppp_table()
    years = sorted({int(row["year"]) for row in table["countries"].values()})
    return {
        "source": table["source"],
        "sourceUrl": table["sourceUrl"],
        "retrieved": table["retrieved"],
        "indicator": table["indicator"],
        "countries": len(table["countries"]),
        "latestYear": years[-1] if years else None,
    }


def _nearest(ladder: list[PricePoint], target: float) -> PricePoint:
    paid = [point for point in ladder if point.customer_price > 0] or ladder
    return min(paid, key=lambda point: (abs(point.customer_price - target), point.customer_price))


def suggest_prices(
    *,
    base: PricePoint,
    base_ladder: list[PricePoint],
    equalize: Callable[[PricePoint], dict[str, PricePoint]],
    current: dict[str, PricePoint],
    territories: list[str],
    ratios: dict[str, float],
    floor: float = DEFAULT_FLOOR,
    ceiling: float = DEFAULT_CEILING,
) -> list[dict[str, object]]:
    """One row per territory: current, equalized, PPP ratio, and the suggested price point.

    `ratio` is the territory's price level relative to the base territory, clamped to
    [floor, ceiling]. Territories without PPP data or not sold get no suggestion.
    """

    if floor <= 0 or ceiling < floor:
        raise ValueError("the floor must be above 0 and not above the ceiling")
    base_ratio = ratios.get(base.territory, 1.0)
    cache: dict[str, dict[str, PricePoint]] = {base.id: equalize(base)}
    equalized = cache[base.id]
    plans: dict[str, tuple[float, float | None, PricePoint | None]] = {}
    for territory in territories:
        if territory == base.territory or territory not in equalized:
            continue
        raw = ratios.get(territory)
        if raw is None or base.customer_price <= 0:
            plans[territory] = (1.0, raw, None)
            continue
        ratio = min(max(raw / base_ratio, floor), ceiling)
        nearest = _nearest(base_ladder, base.customer_price * ratio) if base_ladder else base
        plans[territory] = (ratio, raw, nearest)
    rows: list[dict[str, object]] = []
    for territory, (ratio, raw, tier) in sorted(plans.items()):
        suggested: PricePoint | None = None
        if tier is not None:
            if tier.id not in cache:
                cache[tier.id] = equalize(tier)
            suggested = cache[tier.id].get(territory)
        now = current.get(territory) or equalized[territory]
        change = (
            round((suggested.customer_price / now.customer_price - 1) * 100, 1)
            if suggested and now.customer_price > 0
            else None
        )
        rows.append(
            {
                "territory": territory,
                "currentPrice": now.customer_price,
                "currentPointId": now.id,
                "manual": territory in current and current[territory].id != equalized[territory].id,
                "equalizedPrice": equalized[territory].customer_price,
                "pppRatio": raw,
                "ratio": round(ratio, 4) if tier is not None else None,
                "suggestedPrice": suggested.customer_price if suggested else None,
                "suggestedPointId": suggested.id if suggested else None,
                "changePercent": change,
            }
        )
    return rows


def _bundle_id(apple_app_id: int) -> tuple[int, str]:
    with session_scope() as session:
        app = session.scalar(select(App).where(App.apple_app_id == apple_app_id))
        if app is None:
            raise ValueError(f"unknown app ID: {apple_app_id}")
        if not app.bundle_id:
            raise ValueError("this app has no bundle ID; add it again from Apple to fetch it")
        return app.id, app.bundle_id


def _tracked_territories() -> list[str]:
    with session_scope() as session:
        codes = session.scalars(select(Storefront.country_code).where(Storefront.active.is_(True)))
        return sorted({iso3 for code in codes if (iso3 := iso3_for(code))})


def _open(client: AppStoreConnectClient | None) -> tuple[AppStoreConnectClient, bool]:
    return (client, False) if client is not None else (AppStoreConnectClient(load_settings()), True)


def _friendly(exc: AppStoreConnectError) -> ValueError:
    if exc.status in (401, 403):
        return ValueError(PERMISSION_MESSAGE)
    return ValueError(str(exc))


def pricing_payload(apple_app_id: int) -> dict[str, object]:
    """Local data only: the PPP source and the push log."""

    with session_scope() as session:
        app = session.scalar(select(App).where(App.apple_app_id == apple_app_id))
        if app is None:
            raise ValueError(f"unknown app ID: {apple_app_id}")
        events = session.scalars(
            select(PricePushEvent)
            .where(PricePushEvent.app_id == app.id)
            .order_by(PricePushEvent.created_at.desc(), PricePushEvent.id.desc())
            .limit(100)
        )
        return {
            "appId": apple_app_id,
            "ppp": ppp_meta(),
            "defaults": {"floor": DEFAULT_FLOOR, "ceiling": DEFAULT_CEILING},
            "trackedTerritories": _tracked_territories(),
            "events": [
                {
                    "itemType": event.item_type,
                    "itemName": event.item_name,
                    "territory": event.territory,
                    "currency": event.currency,
                    "beforePrice": event.before_price,
                    "afterPrice": event.after_price,
                    "status": event.status,
                    "error": event.error_message,
                    "createdAt": event.created_at.isoformat(),
                }
                for event in events
            ],
        }


def list_items(
    apple_app_id: int, *, client: AppStoreConnectClient | None = None
) -> dict[str, object]:
    _app_id, bundle_id = _bundle_id(apple_app_id)
    asc, owned = _open(client)
    try:
        pricing = AppStoreConnectPricing(asc)
        items = pricing.items(pricing.app_id(bundle_id))
    except AppStoreConnectError as exc:
        raise _friendly(exc) from exc
    finally:
        if owned:
            asc.__exit__(None, None, None)
    return {
        "items": [
            {"kind": item.kind, "id": item.id, "name": item.name, "productId": item.product_id}
            for item in items
        ]
    }


def _item(kind: str, item_id: str, name: str = "") -> PricedItem:
    if kind not in ("app", "iap", "subscription"):
        raise ValueError("unknown item type")
    typed: ItemKind = kind  # type: ignore[assignment]
    return PricedItem(kind=typed, id=item_id, name=name)


def suggestions(
    apple_app_id: int,
    *,
    kind: str,
    item_id: str,
    scope: str = "tracked",
    floor: float = DEFAULT_FLOOR,
    ceiling: float = DEFAULT_CEILING,
    client: AppStoreConnectClient | None = None,
) -> dict[str, object]:
    """Read current prices and compute suggestions; nothing is written."""

    _bundle_id(apple_app_id)
    item = _item(kind, item_id)
    ratios = ppp_ratios()
    asc, owned = _open(client)
    try:
        pricing = AppStoreConnectPricing(asc)
        currencies = pricing.territories()
        schedule = pricing.schedule(item)
        base = schedule.current.get(schedule.base_territory)
        if base is None:
            raise ValueError("this item has no price in its base territory yet")
        territories = sorted(currencies) if scope == "all" else _tracked_territories()
        rows = suggest_prices(
            base=base,
            base_ladder=pricing.ladder(item, schedule.base_territory),
            equalize=lambda point: pricing.equalizations(item, point),
            current=schedule.current,
            territories=territories,
            ratios=ratios,
            floor=floor,
            ceiling=ceiling,
        )
    except AppStoreConnectError as exc:
        raise _friendly(exc) from exc
    finally:
        if owned:
            asc.__exit__(None, None, None)
    for row in rows:
        row["currency"] = currencies.get(str(row["territory"]), "")
    return {
        "kind": item.kind,
        "id": item.id,
        "baseTerritory": schedule.base_territory,
        "basePrice": base.customer_price,
        "baseCurrency": currencies.get(schedule.base_territory, ""),
        "floor": floor,
        "ceiling": ceiling,
        "scope": scope,
        "rows": rows,
    }


def push_prices(
    apple_app_id: int,
    *,
    kind: str,
    item_id: str,
    item_name: str,
    changes: list[dict[str, Any]],
    preserve_current_price: bool = True,
    client: AppStoreConnectClient | None = None,
) -> dict[str, object]:
    """Write the reviewed price changes (the dashboard confirms each one first).

    App and IAP schedules are rewritten in full: every manual price that isn't being
    changed is sent back unchanged, so nothing is dropped. Subscriptions get one new
    price per territory; existing subscribers keep their price unless told otherwise.
    Each territory is logged with the price it replaced.
    """

    app_db_id, _bundle = _bundle_id(apple_app_id)
    item = _item(kind, item_id, item_name)
    wanted: dict[str, dict[str, Any]] = {}
    for change in changes:
        territory = str(change.get("territory", "")).upper()
        point_id = str(change.get("pricePointId", ""))
        if len(territory) != 3 or not point_id:
            raise ValueError("each change needs a territory and a price point")
        wanted[territory] = change
    if not wanted:
        raise ValueError("choose at least one price change")
    asc, owned = _open(client)
    results: list[dict[str, object]] = []
    try:
        pricing = AppStoreConnectPricing(asc)
        schedule = pricing.schedule(item)
        before = {territory: point.customer_price for territory, point in schedule.current.items()}
        if schedule.base_territory in wanted and item.kind != "subscription":
            raise ValueError(
                f"{schedule.base_territory} is the base territory; change it in App Store Connect"
            )
        new_points = {
            territory: PricePoint(
                id=str(change["pricePointId"]),
                territory=territory,
                customer_price=float(change.get("price") or 0),
            )
            for territory, change in wanted.items()
        }
        if item.kind == "subscription":
            for territory, point in sorted(new_points.items()):
                error: str | None = None
                try:
                    pricing.set_subscription_price(
                        item, point, preserve_current_price=preserve_current_price
                    )
                except AppStoreConnectError as exc:
                    error = str(_friendly(exc))
                results.append({"territory": territory, "error": error})
        else:
            today = datetime.now(UTC).date().isoformat()
            kept = [
                (entry.point, None if (entry.start_date or "") <= today else entry.start_date)
                for entry in schedule.manual
                if not (entry.point.territory in new_points and (entry.start_date or "") <= today)
            ]
            prices = kept + [(point, None) for point in new_points.values()]
            error = None
            try:
                pricing.replace_schedule(
                    item, base_territory=schedule.base_territory, prices=prices
                )
            except AppStoreConnectError as exc:
                error = str(_friendly(exc))
            results.extend({"territory": territory, "error": error} for territory in new_points)
    except AppStoreConnectError as exc:
        raise _friendly(exc) from exc
    finally:
        if owned:
            asc.__exit__(None, None, None)
    with session_scope() as session:
        for result in results:
            territory = str(result["territory"])
            change = wanted[territory]
            session.add(
                PricePushEvent(
                    app_id=app_db_id,
                    item_type=item.kind,
                    item_id=item.id,
                    item_name=item_name[:255],
                    territory=territory,
                    currency=str(change.get("currency") or "")[:3],
                    before_price=(str(before[territory]) if territory in before else None),
                    after_price=str(new_points[territory].customer_price),
                    after_price_point=new_points[territory].id[:128],
                    start_date=None,
                    status="failed" if result["error"] else "success",
                    error_message=str(result["error"]) if result["error"] else None,
                )
            )
    return {"results": results}
