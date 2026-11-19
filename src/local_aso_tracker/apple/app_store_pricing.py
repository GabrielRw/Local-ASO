"""App Store Connect pricing reads and writes for the app, IAPs, and subscriptions.

Apple prices are price points: opaque ids, one per territory and tier. Reads return
current prices, a territory's price ladder, and Apple's equalizations (the same tier
converted to every other territory). Writes replace a price schedule (app and IAPs)
or add a subscription price per territory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from local_aso_tracker.apple.app_store_connect import AppStoreConnectClient, AppStoreConnectError

ItemKind = Literal["app", "iap", "subscription"]


@dataclass(frozen=True)
class PricePoint:
    id: str
    territory: str
    customer_price: float


@dataclass(frozen=True)
class ManualPrice:
    """One scheduled manual price: `start_date` None means it applies now."""

    point: PricePoint
    start_date: str | None
    end_date: str | None


@dataclass(frozen=True)
class PricedItem:
    kind: ItemKind
    id: str
    name: str
    product_id: str = ""


@dataclass
class PriceSchedule:
    """What applies today per territory, plus every manual price to keep on a rewrite."""

    base_territory: str
    current: dict[str, PricePoint] = field(default_factory=dict)
    manual: list[ManualPrice] = field(default_factory=list)


@dataclass(frozen=True)
class _Paths:
    schedule: str
    ladder: str
    ladder_version: str
    equalizations: str
    equalizations_version: str
    point_type: str
    point_relation: str


_PATHS: dict[ItemKind, _Paths] = {
    "app": _Paths(
        schedule="/appPriceSchedules/{id}",
        ladder="/apps/{id}/appPricePoints",
        ladder_version="v1",
        equalizations="/appPricePoints/{id}/equalizations",
        equalizations_version="v3",
        point_type="appPricePoints",
        point_relation="appPricePoint",
    ),
    "iap": _Paths(
        schedule="/inAppPurchasePriceSchedules/{id}",
        ladder="/inAppPurchases/{id}/pricePoints",
        ladder_version="v2",
        equalizations="/inAppPurchasePricePoints/{id}/equalizations",
        equalizations_version="v1",
        point_type="inAppPurchasePricePoints",
        point_relation="inAppPurchasePricePoint",
    ),
    "subscription": _Paths(
        schedule="",
        ladder="/subscriptions/{id}/pricePoints",
        ladder_version="v1",
        equalizations="/subscriptionPricePoints/{id}/equalizations",
        equalizations_version="v1",
        point_type="subscriptionPricePoints",
        point_relation="subscriptionPricePoint",
    ),
}

DEFAULT_BASE_TERRITORY = "USA"


def _relation_id(item: dict[str, Any], name: str) -> str | None:
    data = ((item.get("relationships") or {}).get(name) or {}).get("data")
    return str(data["id"]) if isinstance(data, dict) and data.get("id") else None


def _price(value: object) -> float:
    try:
        return float(str(value))
    except ValueError:
        return 0.0


def _point(item: dict[str, Any], territory: str | None = None) -> PricePoint:
    attributes = item.get("attributes") or {}
    return PricePoint(
        id=str(item["id"]),
        territory=territory or _relation_id(item, "territory") or "",
        customer_price=_price(attributes.get("customerPrice")),
    )


def _applies_today(start: str | None, end: str | None, today: str) -> bool:
    return (start is None or start <= today) and (end is None or end > today)


class AppStoreConnectPricing:
    """Pricing calls on top of an authenticated App Store Connect client."""

    def __init__(self, client: AppStoreConnectClient) -> None:
        self.client = client

    # --- reads --------------------------------------------------------------

    def app_id(self, bundle_id: str) -> str:
        apps = self.client._request(
            "GET",
            "/apps",
            params={"filter[bundleId]": bundle_id, "fields[apps]": "bundleId", "limit": 5},
        ).get("data", [])
        if not apps:
            raise AppStoreConnectError("the App Store Connect API key cannot access this bundle ID")
        return str(apps[0]["id"])

    def territories(self) -> dict[str, str]:
        """Territory id (ISO 3166 alpha-3) -> currency code."""

        items = self.client._get_all(
            "/territories", params={"limit": 200, "fields[territories]": "currency"}
        )
        return {
            str(item["id"]): str((item.get("attributes") or {}).get("currency") or "")
            for item in items
        }

    def items(self, app_id: str) -> list[PricedItem]:
        found = [PricedItem(kind="app", id=app_id, name="App price")]
        for iap in self.client._get_all(
            f"/apps/{app_id}/inAppPurchasesV2",
            params={"limit": 200, "fields[inAppPurchases]": "name,productId,inAppPurchaseType"},
        ):
            attributes = iap.get("attributes") or {}
            found.append(
                PricedItem(
                    kind="iap",
                    id=str(iap["id"]),
                    name=str(attributes.get("name") or attributes.get("productId") or iap["id"]),
                    product_id=str(attributes.get("productId") or ""),
                )
            )
        included: dict[tuple[str, str], dict[str, Any]] = {}
        self.client._get_all(
            f"/apps/{app_id}/subscriptionGroups",
            params={"limit": 50, "include": "subscriptions", "limit[subscriptions]": 50},
            included=included,
        )
        for (kind, item_id), item in sorted(included.items()):
            if kind != "subscriptions":
                continue
            attributes = item.get("attributes") or {}
            found.append(
                PricedItem(
                    kind="subscription",
                    id=item_id,
                    name=str(attributes.get("name") or attributes.get("productId") or item_id),
                    product_id=str(attributes.get("productId") or ""),
                )
            )
        return found

    def schedule(self, item: PricedItem, *, today: str | None = None) -> PriceSchedule:
        day = today or datetime.now(UTC).date().isoformat()
        if item.kind == "subscription":
            return self._subscription_schedule(item, day)
        paths = _PATHS[item.kind]
        root = paths.schedule.format(id=item.id)
        base = self.client._request("GET", f"{root}/baseTerritory").get("data") or {}
        schedule = PriceSchedule(base_territory=str(base.get("id") or DEFAULT_BASE_TERRITORY))
        price_type = "appPrices" if item.kind == "app" else "inAppPurchasePrices"
        for relation, manual in (("automaticPrices", False), ("manualPrices", True)):
            included: dict[tuple[str, str], dict[str, Any]] = {}
            prices = self.client._get_all(
                f"{root}/{relation}",
                params={
                    "limit": 200,
                    "include": f"{paths.point_relation},territory",
                    f"fields[{price_type}]": f"startDate,endDate,{paths.point_relation},territory",
                },
                included=included,
            )
            for price in prices:
                attributes = price.get("attributes") or {}
                start, end = attributes.get("startDate"), attributes.get("endDate")
                territory = _relation_id(price, "territory")
                point_id = _relation_id(price, paths.point_relation)
                if not territory or not point_id:
                    continue
                raw = included.get((paths.point_type, point_id), {"id": point_id})
                point = _point(raw, territory)
                if manual and (end is None or end > day):
                    schedule.manual.append(ManualPrice(point=point, start_date=start, end_date=end))
                if _applies_today(start, end, day):
                    schedule.current[territory] = point
        return schedule

    def _subscription_schedule(self, item: PricedItem, day: str) -> PriceSchedule:
        included: dict[tuple[str, str], dict[str, Any]] = {}
        prices = self.client._get_all(
            f"/subscriptions/{item.id}/prices",
            params={"limit": 200, "include": "subscriptionPricePoint,territory"},
            included=included,
        )
        schedule = PriceSchedule(base_territory=DEFAULT_BASE_TERRITORY)
        latest: dict[str, str] = {}
        for price in prices:
            start = (price.get("attributes") or {}).get("startDate")
            territory = _relation_id(price, "territory")
            point_id = _relation_id(price, "subscriptionPricePoint")
            if not territory or not point_id or (start is not None and start > day):
                continue
            begins = start or ""
            if territory in latest and latest[territory] > begins:
                continue
            latest[territory] = begins
            raw = included.get(("subscriptionPricePoints", point_id), {"id": point_id})
            schedule.current[territory] = _point(raw, territory)
        if schedule.current and DEFAULT_BASE_TERRITORY not in schedule.current:
            schedule.base_territory = sorted(schedule.current)[0]
        return schedule

    def ladder(self, item: PricedItem, territory: str) -> list[PricePoint]:
        """Every price point of one territory, cheapest first."""

        paths = _PATHS[item.kind]
        points = self.client._get_all(
            paths.ladder.format(id=item.id),
            params={"filter[territory]": territory, "limit": 200},
            version=paths.ladder_version,
        )
        return sorted(
            (_point(point, territory) for point in points), key=lambda p: p.customer_price
        )

    def equalizations(self, item: PricedItem, point: PricePoint) -> dict[str, PricePoint]:
        """The same tier in every other territory, keyed by territory."""

        paths = _PATHS[item.kind]
        points = self.client._get_all(
            paths.equalizations.format(id=point.id),
            params={"limit": 200, "include": "territory"},
            version=paths.equalizations_version,
        )
        result = {point.territory: point}
        for raw in points:
            converted = _point(raw)
            if converted.territory:
                result[converted.territory] = converted
        return result

    # --- writes -------------------------------------------------------------

    def replace_schedule(
        self,
        item: PricedItem,
        *,
        base_territory: str,
        prices: list[tuple[PricePoint, str | None]],
    ) -> None:
        """Write a full manual price schedule for the app or an IAP.

        `prices` must hold every manual price to keep (Apple drops any left out), as
        (price point, start date or None for now).
        """

        if item.kind == "subscription":
            raise ValueError("subscriptions are priced per territory, not by schedule")
        paths = _PATHS[item.kind]
        is_app = item.kind == "app"
        price_type = "appPrices" if is_app else "inAppPurchasePrices"
        included: list[dict[str, Any]] = []
        for index, (point, start) in enumerate(prices):
            relationships: dict[str, Any] = {
                paths.point_relation: {"data": {"type": paths.point_type, "id": point.id}}
            }
            if not is_app:
                relationships["inAppPurchaseV2"] = {
                    "data": {"type": "inAppPurchases", "id": item.id}
                }
            included.append(
                {
                    "type": price_type,
                    "id": f"${{price-{index}}}",
                    "attributes": {"startDate": start},
                    "relationships": relationships,
                }
            )
        owner = (
            {"app": {"data": {"type": "apps", "id": item.id}}}
            if is_app
            else {"inAppPurchase": {"data": {"type": "inAppPurchases", "id": item.id}}}
        )
        self.client._request(
            "POST",
            "/appPriceSchedules" if is_app else "/inAppPurchasePriceSchedules",
            json_body={
                "data": {
                    "type": "appPriceSchedules" if is_app else "inAppPurchasePriceSchedules",
                    "relationships": {
                        **owner,
                        "baseTerritory": {"data": {"type": "territories", "id": base_territory}},
                        "manualPrices": {
                            "data": [{"type": price_type, "id": entry["id"]} for entry in included]
                        },
                    },
                },
                "included": included,
            },
        )

    def set_subscription_price(
        self,
        item: PricedItem,
        point: PricePoint,
        *,
        preserve_current_price: bool,
        start_date: str | None = None,
    ) -> None:
        self.client._request(
            "POST",
            "/subscriptionPrices",
            json_body={
                "data": {
                    "type": "subscriptionPrices",
                    "attributes": {
                        "startDate": start_date,
                        "preserveCurrentPrice": preserve_current_price,
                    },
                    "relationships": {
                        "subscription": {"data": {"type": "subscriptions", "id": item.id}},
                        "subscriptionPricePoint": {
                            "data": {"type": "subscriptionPricePoints", "id": point.id}
                        },
                        "territory": {"data": {"type": "territories", "id": point.territory}},
                    },
                }
            },
        )
