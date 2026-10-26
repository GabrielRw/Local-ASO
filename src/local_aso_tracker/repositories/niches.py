"""Persistence operations for app-independent niche research boards."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from local_aso_tracker.models import (
    NicheBoard,
    NicheKeyword,
    NicheMarket,
    NicheMetric,
    Storefront,
)
from local_aso_tracker.repositories.data import normalize_keyword


def get_niche_board(session: Session, board_id: int | None = None) -> NicheBoard | None:
    query = select(NicheBoard).options(
        selectinload(NicheBoard.keywords).selectinload(NicheKeyword.metrics),
        selectinload(NicheBoard.markets),
    )
    if board_id is None:
        query = query.order_by(NicheBoard.updated_at.desc(), NicheBoard.id.desc())
    else:
        query = query.where(NicheBoard.id == board_id)
    return session.scalar(query.limit(1))


def create_niche_board(
    session: Session,
    *,
    name: str,
    brief: str,
    provider: str,
    keywords: list[str],
    countries: list[str],
) -> NicheBoard:
    board = NicheBoard(
        name=" ".join(name.split())[:255] or "Untitled niche",
        brief=" ".join(brief.split()),
        provider=provider,
    )
    session.add(board)
    session.flush()
    add_niche_keywords(session, board, keywords)
    for position, country in enumerate(countries, start=1):
        board.markets.append(NicheMarket(country_code=country, position=position))
    session.flush()
    return board


def add_niche_keywords(
    session: Session,
    board: NicheBoard,
    keywords: list[str],
) -> list[NicheKeyword]:
    existing = {
        item.normalized_keyword
        for item in session.scalars(select(NicheKeyword).where(NicheKeyword.board_id == board.id))
    }
    next_position = (
        session.scalar(
            select(NicheKeyword.position)
            .where(NicheKeyword.board_id == board.id)
            .order_by(NicheKeyword.position.desc())
            .limit(1)
        )
        or 0
    )
    added: list[NicheKeyword] = []
    for value in keywords:
        normalized = normalize_keyword(value)
        if normalized in existing:
            continue
        next_position += 1
        item = NicheKeyword(
            board_id=board.id,
            keyword=" ".join(value.split()),
            normalized_keyword=normalized,
            position=next_position,
        )
        session.add(item)
        existing.add(normalized)
        added.append(item)
    board.updated_at = datetime.now(UTC)
    session.flush()
    return added


def add_niche_country(session: Session, board: NicheBoard, country: str) -> bool:
    if any(item.country_code == country for item in board.markets):
        return False
    position = max((item.position for item in board.markets), default=0) + 1
    board.markets.append(NicheMarket(country_code=country, position=position))
    board.updated_at = datetime.now(UTC)
    session.flush()
    return True


def remove_niche_country(session: Session, board: NicheBoard, country: str) -> bool:
    market = next((item for item in board.markets if item.country_code == country), None)
    if market is None:
        return False
    board.markets.remove(market)
    session.execute(
        delete(NicheMetric).where(
            NicheMetric.niche_keyword_id.in_(
                select(NicheKeyword.id).where(NicheKeyword.board_id == board.id)
            ),
            NicheMetric.country_code == country,
        )
    )
    board.updated_at = datetime.now(UTC)
    session.flush()
    return True


def niche_board_payload(session: Session, board_id: int | None = None) -> dict[str, object]:
    boards = list(
        session.scalars(
            select(NicheBoard).order_by(NicheBoard.updated_at.desc(), NicheBoard.id.desc())
        )
    )
    board = get_niche_board(session, board_id)
    countries = list(
        session.scalars(
            select(Storefront).where(Storefront.active.is_(True)).order_by(Storefront.country_code)
        )
    )
    country_names = {item.country_code: item.display_name for item in countries}
    payload: dict[str, object] = {
        "boards": [
            {
                "id": item.id,
                "name": item.name,
                "brief": item.brief,
                "updatedAt": _iso(item.updated_at),
            }
            for item in boards
        ],
        "availableCountries": [
            {
                "code": item.country_code,
                "name": item.display_name,
            }
            for item in countries
        ],
        "selectedBoardId": board.id if board else None,
        "board": None,
    }
    if board is None:
        return payload
    markets = sorted(board.markets, key=lambda item: (item.position, item.country_code))
    keywords = sorted(board.keywords, key=lambda item: (item.position, item.id))
    metrics = {
        (metric.niche_keyword_id, metric.country_code): metric
        for keyword in keywords
        for metric in keyword.metrics
    }
    payload["board"] = {
        "id": board.id,
        "name": board.name,
        "brief": board.brief,
        "provider": board.provider,
        "updatedAt": _iso(board.updated_at),
        "countries": [
            {
                "code": market.country_code,
                "name": country_names.get(market.country_code, market.country_code.upper()),
            }
            for market in markets
        ],
        "keywords": [
            {
                "id": keyword.id,
                "keyword": keyword.keyword,
                "metrics": [
                    _metric_dict(metrics.get((keyword.id, market.country_code)))
                    for market in markets
                ],
            }
            for keyword in keywords
        ],
    }
    return payload


def upsert_niche_metric(
    session: Session,
    *,
    keyword_id: int,
    country: str,
    device: str,
    volume: int | None,
    difficulty: int | None,
    sample_size: int,
    status: str,
    error: str | None = None,
) -> None:
    metric = session.scalar(
        select(NicheMetric).where(
            NicheMetric.niche_keyword_id == keyword_id,
            NicheMetric.country_code == country,
            NicheMetric.device == device,
        )
    )
    if metric is None:
        metric = NicheMetric(
            niche_keyword_id=keyword_id,
            country_code=country,
            device=device,
        )
        session.add(metric)
    metric.volume_estimate = volume
    metric.difficulty_estimate = difficulty
    metric.sample_size = sample_size
    metric.checked_at = datetime.now(UTC)
    metric.status = status
    metric.error_message = error


def _metric_dict(metric: NicheMetric | None) -> dict[str, object]:
    if metric is None:
        return {
            "volume": None,
            "difficulty": None,
            "sampleSize": None,
            "status": "pending",
            "checkedAt": None,
            "error": None,
        }
    return {
        "volume": metric.volume_estimate,
        "difficulty": metric.difficulty_estimate,
        "sampleSize": metric.sample_size,
        "status": metric.status,
        "checkedAt": _iso(metric.checked_at),
        "error": metric.error_message,
    }


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()
