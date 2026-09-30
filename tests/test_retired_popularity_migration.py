"""Retiring old features must not remove any rank-tracking data."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text

from local_aso_tracker.database import create_db_engine, run_migrations, session_scope
from local_aso_tracker.models import (
    App,
    Base,
    DashboardOnboarding,
    Keyword,
    RankCheck,
    Storefront,
    TrackingTarget,
)
from local_aso_tracker.repositories.data import list_targets, seed_catalog, seed_targets
from local_aso_tracker.repositories.onboarding import complete_onboarding


def test_upgrade_removes_only_retired_tables_and_preserves_tracking(tmp_path: Path) -> None:
    path = tmp_path / "aso.db"
    root = Path(__file__).resolve().parents[1]
    config = Config(root / "alembic.ini")
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    command.upgrade(config, "0006")
    engine = create_db_engine(path)
    with session_scope(engine) as session:
        seed_catalog(session)
        seed_targets(session)
        target = list_targets(session, country="us")[0]
        session.add(
            RankCheck(
                tracking_target_id=target.id,
                rank=12,
                found=True,
                result_limit=200,
                response_time_ms=15,
                status="success",
            )
        )
        session.execute(
            text(
                "INSERT INTO listing_metadata_audits "
                "(app_id, storefront_id, subtitle, keywords_field, created_at, updated_at) "
                "VALUES (:app, :store, 'Saved subtitle', 'saved,metadata', "
                "'2026-07-12', '2026-07-12')"
            ),
            {"app": target.app_id, "store": target.storefront_id},
        )
        complete_onboarding(session)
        session.execute(
            text(
                "INSERT INTO keyword_popularities "
                "(app_id, keyword_id, storefront_id, score, report_id, synced_at) "
                "VALUES (:app, :keyword, :store, 4, 91, '2026-07-12 12:00:00')"
            ),
            {"app": target.app_id, "keyword": target.keyword_id, "store": target.storefront_id},
        )
        session.execute(
            text(
                "INSERT INTO apple_ads_discovered_terms "
                "(app_id, storefront_id, search_term, normalized_term, "
                "score, report_id, synced_at) "
                "VALUES (:app, :store, 'legacy term', 'legacy term', 4, 91, '2026-07-12 12:00:00')"
            ),
            {"app": target.app_id, "store": target.storefront_id},
        )
        session.execute(
            text(
                "INSERT INTO popularity_syncs "
                "(app_id, storefront_id, report_id, state, started_at, updated_at) "
                "VALUES (:app, :store, 91, 'completed', '2026-07-12', '2026-07-12')"
            ),
            {"app": target.app_id, "store": target.storefront_id},
        )
    models = (App, Keyword, Storefront, TrackingTarget, RankCheck)
    with session_scope(engine) as session:
        before = {
            model.__tablename__: len(session.scalars(select(model)).all()) for model in models
        }

    command.upgrade(config, "0007")
    with session_scope(engine) as session:
        assert session.scalar(text("SELECT subtitle FROM listing_metadata_audits")) == (
            "Saved subtitle"
        )
    run_migrations(path)
    run_migrations(path)
    assert set(inspect(engine).get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
    with session_scope(engine) as session:
        after = {model.__tablename__: len(session.scalars(select(model)).all()) for model in models}
        assert after == before
        check = session.scalar(select(RankCheck))
        assert check is not None and check.rank == 12 and check.found
        assert session.get(DashboardOnboarding, 1) is not None
        assert session.execute(text("PRAGMA foreign_key_check")).all() == []

    command.downgrade(config, "0007")
    assert "listing_metadata_audits" in inspect(engine).get_table_names()
    command.downgrade(config, "0006")
    assert "keyword_popularities" in inspect(engine).get_table_names()
    run_migrations(path)
    assert set(inspect(engine).get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
    with session_scope(engine) as session:
        assert len(session.scalars(select(RankCheck)).all()) == before["rank_checks"]
    engine.dispose()
