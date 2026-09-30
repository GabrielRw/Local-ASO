"""Read and persist the dashboard's first-run setup state."""

from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from local_aso_tracker.models import DashboardOnboarding, utc_now


def onboarding_completed(session: Session) -> bool:
    return session.get(DashboardOnboarding, 1) is not None


def complete_onboarding(session: Session) -> None:
    """Idempotently remember completion or dismissal without touching tracker data."""

    session.execute(
        insert(DashboardOnboarding)
        .values(id=1, completed_at=utc_now())
        .on_conflict_do_nothing(index_elements=["id"])
    )
