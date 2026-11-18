"""Local app audit orchestration and persistence tests."""

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from local_aso_tracker.apple.client import SearchOutcome
from local_aso_tracker.apple.listing import AppleListing
from local_aso_tracker.apple.schemas import AppleSearchResponse
from local_aso_tracker.database import run_migrations, session_scope
from local_aso_tracker.models import AuditFinding, AuditKeyword, RankCheck
from local_aso_tracker.repositories.audits import (
    audit_dashboard_payload,
    create_audit_run,
)
from local_aso_tracker.repositories.data import (
    add_app,
    add_keyword,
    add_storefront,
    add_target,
    save_listing_metadata,
)
from local_aso_tracker.services.agent import (
    AgentProvider,
    AuditFindingSuggestion,
    AuditKeywordSuggestion,
    AuditLocalizationResult,
    AuditMarketSuggestion,
    AuditSynthesisResult,
)
from local_aso_tracker.services.audits import AuditRunner, KeywordEvidence
from local_aso_tracker.services.keyword_popularity import PopularityReading
from local_aso_tracker.web.server import DashboardService


class FakeAppleClient:
    def __init__(self, app_id: int) -> None:
        self.app_id = app_id
        self.calls: list[tuple[str, str, str]] = []

    async def __aenter__(self) -> "FakeAppleClient":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def search(self, keyword: str, country: str, device: str) -> SearchOutcome:
        self.calls.append((keyword, country, device))
        return SearchOutcome(
            response=AppleSearchResponse.model_validate(
                {
                    "resultCount": 2,
                    "results": [
                        {
                            "trackId": self.app_id,
                            "trackName": "Learn Astrology",
                            "userRatingCount": 20_000,
                            "averageUserRating": 4.8,
                        },
                        {
                            "trackId": 99,
                            "trackName": "Competitor",
                            "userRatingCount": 80_000,
                            "averageUserRating": 4.6,
                        },
                    ],
                }
            ),
            response_time_ms=5,
            raw_response_hash="test",
        )


def sample_listing(app_id: int) -> AppleListing:
    return AppleListing.model_validate(
        {
            "trackId": app_id,
            "trackName": "Learn Astrology",
            "description": "Learn astrology with guided chart lessons.",
            "primaryGenreName": "Education",
            "languageCodesISO2A": ["EN", "FR"],
        }
    )


def fake_localization_review(
    **kwargs: object,
) -> tuple[str, AuditLocalizationResult]:
    facts = kwargs["facts"]
    assert isinstance(facts, list)
    evidence_id = str(facts[0]["id"])
    return (
        "codex",
        AuditLocalizationResult(
            summary="The saved listing has a measurable metadata opportunity.",
            findings=[
                AuditFindingSuggestion(
                    category="metadata",
                    tone="warning",
                    title="Review indexed metadata efficiency",
                    detail="Use the saved metadata evidence before changing the listing.",
                    terms=[],
                    evidence_ids=[evidence_id],
                )
            ],
            candidatePhrases=[],
        ),
    )


def fake_audit_synthesis(
    **kwargs: object,
) -> tuple[str, AuditSynthesisResult]:
    evidence = kwargs["evidence"]
    assert isinstance(evidence, list)
    term = str(evidence[0]["keyword"]) if evidence else ""
    evidence_id = str(evidence[0]["id"]) if evidence else "market.context"
    return (
        "codex",
        AuditSynthesisResult(
            summary="Prioritize the verified phrase with the clearest next action.",
            findings=[
                AuditFindingSuggestion(
                    category="opportunity",
                    tone="info",
                    title=f"Act on “{term}”",
                    detail=(
                        "Use the verified Apple evidence and saved listing before the "
                        "next iteration."
                    ),
                    terms=[term] if term else [],
                    evidence_ids=[evidence_id],
                )
            ],
        ),
    )


def test_audit_runner_persists_grounded_market_results(
    tmp_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    with session_scope() as session:
        app, _ = add_app(session, "Learn Astrology", 6771773264)
        add_storefront(session, "us", "United States")
        add_storefront(session, "fr", "France")
        save_listing_metadata(
            session,
            app.apple_app_id,
            "us",
            name="Learn Astrology",
            subtitle="Birth chart lessons",
            keyword_field="astrology, birth chart",
            channel_goal="aso_seo_aeo",
            brand_term="AstroLingo",
        )
        keyword, _ = add_keyword(session, "learn astrology")
        target, _ = add_target(session, app.apple_app_id, keyword.keyword, "us")
        session.add(
            RankCheck(
                tracking_target_id=target.id,
                checked_at=datetime.now(UTC),
                rank=3,
                found=True,
                result_limit=200,
                status="success",
                response_time_ms=1,
            )
        )
        run = create_audit_run(
            session,
            app_id=app.id,
            scope="country",
            country_code="us",
            device="iphone",
            provider="codex",
            country_codes=["us"],
        )
        run_id = run.id

    fake_client = FakeAppleClient(6771773264)

    def fake_agent(**kwargs: object) -> tuple[str, dict[str, AuditMarketSuggestion]]:
        if kwargs.get("instruction"):
            keywords = [
                AuditKeywordSuggestion(
                    keyword="zodiac houses",
                    intent="study houses",
                    rationale="Adds a new learning phrase.",
                )
            ]
        else:
            keywords = [
                AuditKeywordSuggestion(
                    keyword="learn astrology",
                    intent="learning",
                    rationale="Core product intent.",
                ),
                AuditKeywordSuggestion(
                    keyword="birth chart lessons",
                    intent="birth chart",
                    rationale="Matches the subtitle.",
                ),
            ]
        return (
            "codex",
            {
                "us": AuditMarketSuggestion(
                    country="us",
                    language="English",
                    keywords=keywords,
                )
            },
        )

    runner = AuditRunner(
        agent_runner=fake_agent,
        localization_runner=fake_localization_review,
        synthesis_runner=fake_audit_synthesis,
        listing_loader=lambda app_id, _country, **_kwargs: sample_listing(app_id),
        apple_client_factory=lambda _settings: fake_client,
    )
    runner.run(run_id)

    assert fake_client.calls == [
        ("learn astrology", "us", "iphone"),
        ("birth chart lessons", "us", "iphone"),
    ]
    assert runner.expand_country(run_id, "us", "Add another angle") == 1
    with session_scope() as session:
        legacy = session.scalar(select(AuditFinding).where(AuditFinding.category == "opportunity"))
        assert legacy is not None
        legacy_term = json.loads(legacy.terms)[0]
        legacy.title = f"“{legacy_term}” is already visible"
        legacy.detail = "Legacy visibility copy."
        legacy.tone = "positive"
        legacy_keyword = session.scalar(
            select(AuditKeyword).where(AuditKeyword.normalized_keyword == legacy_term.casefold())
        )
        assert legacy_keyword is not None
        legacy_keyword.rank = 73
        legacy_keyword.found = True
        payload = audit_dashboard_payload(session, app_id=1)
        result = payload["run"]
        assert result["status"] == "success"  # type: ignore[index]
        assert result["startedAt"] is not None  # type: ignore[index]
        assert result["score"] > 0  # type: ignore[index]
        country = result["countries"][0]  # type: ignore[index]
        assert country["rankingScore"] == 100  # type: ignore[index]
        assert len(country["keywords"]) == 3  # type: ignore[index]
        assert country["keywords"][-1]["keyword"] == "zodiac houses"  # type: ignore[index]
        assert all(item["found"] for item in country["keywords"])  # type: ignore[index]
        assert any(finding["category"] == "visibility" for finding in country["findings"])  # type: ignore[index]
        assert all("already visible" not in finding["title"] for finding in country["findings"])  # type: ignore[index]
        assert any("outside the Top 50" in finding["title"] for finding in country["findings"])  # type: ignore[index]


def test_audit_runner_marks_missing_agent_market_results(
    tmp_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    with session_scope() as session:
        app, _ = add_app(session, "Learn Astrology", 6771773264)
        add_storefront(session, "us", "United States")
        add_storefront(session, "fr", "France")
        run = create_audit_run(
            session,
            app_id=app.id,
            scope="country",
            country_code="fr",
            device="iphone",
            provider="codex",
            country_codes=["fr"],
        )
        run_id = run.id

    def fake_agent(**_kwargs: object) -> tuple[str, dict[str, AuditMarketSuggestion]]:
        return (
            "codex",
            {
                "us": AuditMarketSuggestion(
                    country="us",
                    language="English",
                    keywords=[
                        AuditKeywordSuggestion(
                            keyword="learn astrology",
                            intent="learning",
                            rationale="Core intent.",
                        )
                    ],
                )
            },
        )

    client = FakeAppleClient(6771773264)
    AuditRunner(
        agent_runner=fake_agent,
        localization_runner=fake_localization_review,
        synthesis_runner=fake_audit_synthesis,
        listing_loader=lambda app_id, _country, **_kwargs: sample_listing(app_id),
        apple_client_factory=lambda _settings: client,
    ).run(run_id)

    with session_scope() as session:
        result = audit_dashboard_payload(
            session,
            app_id=1,
            country_code="fr",
        )["run"]
        countries = {item["code"]: item for item in result["countries"]}  # type: ignore[index]
        assert countries["fr"]["status"] == "error"
        assert result["status"] == "error"


def test_audit_runner_runs_specialists_and_verifies_their_phrase_candidates(
    tmp_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    with session_scope() as session:
        app, _ = add_app(session, "Learn Astrology", 6771773264)
        add_storefront(session, "us", "United States")
        save_listing_metadata(
            session,
            app.apple_app_id,
            "us",
            name="Learn Astrology",
            subtitle="Birth chart lessons",
            keyword_field="astrology",
            channel_goal="aso_seo_aeo",
            brand_term="AstroLingo",
        )
        run = create_audit_run(
            session,
            app_id=app.id,
            scope="country",
            country_code="us",
            device="iphone",
            provider="codex",
            country_codes=["us"],
        )
        run_id = run.id

    calls = {"discovery": 0, "localization": 0, "synthesis": 0}

    def discovery(**kwargs: object) -> tuple[str, dict[str, AuditMarketSuggestion]]:
        calls["discovery"] += 1
        assert kwargs["provider"] == "codex"
        return (
            "codex",
            {
                "us": AuditMarketSuggestion(
                    country="us",
                    language="English",
                    keywords=[
                        AuditKeywordSuggestion(
                            keyword="learn astrology",
                            intent="learning",
                            rationale="Core intent.",
                        )
                    ],
                )
            },
        )

    def localization(**kwargs: object) -> tuple[str, AuditLocalizationResult]:
        calls["localization"] += 1
        facts = kwargs["facts"]
        assert isinstance(facts, list)
        return (
            "codex",
            AuditLocalizationResult(
                summary="The listing needs a more natural adjacent phrase.",
                findings=[
                    AuditFindingSuggestion(
                        category="copy",
                        tone="info",
                        title="Try a natural adjacent phrase",
                        detail="Verify the proposed phrase before adding it.",
                        terms=[],
                        evidence_ids=[str(facts[0]["id"])],
                    )
                ],
                candidate_phrases=[
                    AuditKeywordSuggestion(
                        keyword="zodiac houses",
                        intent="study houses",
                        rationale="Natural learning phrase.",
                    )
                ],
            ),
        )

    def synthesis(**kwargs: object) -> tuple[str, AuditSynthesisResult]:
        calls["synthesis"] += 1
        evidence = kwargs["evidence"]
        assert isinstance(evidence, list)
        return (
            "codex",
            AuditSynthesisResult(
                summary="Use the verified phrases in the next listing iteration.",
                findings=[
                    AuditFindingSuggestion(
                        category="opportunity",
                        tone="info",
                        title="Verified phrase opportunity",
                        detail="Both discovered phrases were checked against Apple.",
                        terms=[str(evidence[0]["keyword"])],
                        evidence_ids=[str(evidence[0]["id"])],
                    )
                ],
            ),
        )

    client = FakeAppleClient(6771773264)
    AuditRunner(
        agent_runner=discovery,
        localization_runner=localization,
        synthesis_runner=synthesis,
        listing_loader=lambda app_id, _country, **_kwargs: sample_listing(app_id),
        apple_client_factory=lambda _settings: client,
    ).run(run_id)

    assert calls == {"discovery": 1, "localization": 1, "synthesis": 1}
    assert {call[0] for call in client.calls} == {"learn astrology", "zodiac houses"}
    with session_scope() as session:
        result = audit_dashboard_payload(session, app_id=1, country_code="us")["run"]
        country = result["countries"][0]  # type: ignore[index]
        assert {item["keyword"] for item in country["keywords"]} == {  # type: ignore[index]
            "learn astrology",
            "zodiac houses",
        }
        assert any(
            finding["title"] == "Verified phrase opportunity"
            for finding in country["findings"]  # type: ignore[index]
        )


def test_audit_worker_can_be_constructed_without_starting_threads() -> None:
    from local_aso_tracker.services.audits import AuditWorker

    worker = AuditWorker(runner=AuditRunner())
    assert worker is not None


def test_dashboard_start_audit_queues_a_market_scoped_run(
    tmp_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    with session_scope() as session:
        add_app(session, "Learn Astrology", 6771773264)
        add_storefront(session, "us", "United States")
    monkeypatch.setattr(
        "local_aso_tracker.web.server.provider_status",
        lambda **_kwargs: [
            AgentProvider("codex", "Codex", True),
            AgentProvider("claude", "Claude", True),
        ],
    )
    service = DashboardService()
    service.audit_worker.start = lambda _run_id: None  # type: ignore[method-assign]

    payload = service.start_audit(
        {
            "appId": 6771773264,
            "scope": "country",
            "country": "us",
            "device": "iphone",
            "provider": "codex",
        }
    )

    assert payload["appId"] == 6771773264
    run = payload["run"]
    assert run["status"] == "queued"  # type: ignore[index]
    assert run["scope"] == "country"  # type: ignore[index]
    assert run["country"] == "us"  # type: ignore[index]


def test_dashboard_rejects_all_country_audits(
    tmp_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    with session_scope() as session:
        add_app(session, "Learn Astrology", 6771773264)
        add_storefront(session, "us", "United States")
    monkeypatch.setattr(
        "local_aso_tracker.web.server.provider_status",
        lambda **_kwargs: [AgentProvider("codex", "Codex", True)],
    )

    with pytest.raises(ValueError, match="per country only"):
        DashboardService().start_audit(
            {
                "appId": 6771773264,
                "scope": "all",
                "device": "iphone",
                "provider": "codex",
            }
        )


@pytest.mark.parametrize("prompt_version", ["audit-v1", "audit-v2-country-language"])
def test_dashboard_hides_retired_audit_pipelines(
    tmp_path: object,
    monkeypatch: pytest.MonkeyPatch,
    prompt_version: str,
) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    with session_scope() as session:
        app, _ = add_app(session, "Learn Astrology", 6771773264)
        add_storefront(session, "us", "United States")
        run = create_audit_run(
            session,
            app_id=app.id,
            scope="country",
            country_code="us",
            device="iphone",
            provider="codex",
            country_codes=["us"],
        )
        run.prompt_version = prompt_version

    with session_scope() as session:
        payload = audit_dashboard_payload(
            session,
            app_id=1,
            country_code="us",
            device="iphone",
        )
    assert payload["run"] is None


def _evidence(
    keyword: str,
    *,
    rank: int | None,
    volume: int | None = 50,
    difficulty: int | None = 40,
    popularity: int | None = None,
    measured: bool = True,
) -> KeywordEvidence:
    return KeywordEvidence(
        keyword=keyword,
        intent="intent",
        rationale="rationale",
        rank=rank,
        found=rank is not None,
        result_limit=200,
        volume=volume,
        difficulty=difficulty,
        sample_size=10,
        status="success",
        error=None,
        popularity=popularity,
        popularity_status=(
            None if not measured else "measured" if popularity is not None else "unavailable"
        ),
    )


def _finding_titles(evidence: list[KeywordEvidence]) -> list[tuple[str, list[str]]]:
    findings = AuditRunner._findings(
        country="us",
        tracked=[],
        evidence=evidence,
        metadata=None,
        all_keywords=[item.keyword for item in evidence],
    )
    return [(item.title, item.terms) for item in findings]


def test_opportunity_score_follows_popularity_difficulty_and_rank() -> None:
    absent = _evidence("natal chart", rank=None, popularity=40, difficulty=64)
    assert absent.opportunity == 14  # 40 x 0.36
    assert _evidence("x", rank=5, popularity=40, difficulty=64).opportunity == 12
    assert _evidence("x", rank=1, popularity=40, difficulty=64).opportunity == 0
    assert _evidence("x", rank=None, popularity=None, difficulty=64).opportunity is None


def test_quick_win_prefers_apple_demand_over_closer_rank() -> None:
    titles = _finding_titles(
        [
            _evidence("niche phrase", rank=12, volume=80, popularity=5),
            _evidence("birth chart reading", rank=25, volume=20, popularity=30),
        ]
    )
    quick_win = next(terms for title, terms in titles if "close to the Top 10" in title)
    assert quick_win[0] == "birth chart reading"


def test_gaps_use_apple_popularity_and_ignore_floor_phrases() -> None:
    titles = _finding_titles(
        [
            # High ratings-based estimate but Apple says almost nobody searches it.
            _evidence("astrology", rank=None, volume=90, popularity=5),
            _evidence("horoscope gratuit", rank=None, volume=30, popularity=37, difficulty=50),
            _evidence("tarot", rank=None, volume=30, popularity=5),
        ]
    )
    gap_titles = [title for title, _ in titles if "High-demand phrase gap" in title]
    assert gap_titles == ["High-demand phrase gap: “horoscope gratuit”"]
    assert any("too few searches" in title for title, _ in titles)


def test_gaps_fall_back_to_estimates_without_apple_ads() -> None:
    titles = _finding_titles(
        [_evidence("birth chart", rank=None, volume=60, popularity=None, measured=False)]
    )
    assert any(title == "High-demand phrase gap: “birth chart”" for title, _ in titles)


def test_audit_runner_attaches_and_persists_apple_popularity(
    tmp_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    with session_scope() as session:
        app, _ = add_app(session, "Learn Astrology", 6771773264)
        add_storefront(session, "us", "United States")
        run = create_audit_run(
            session,
            app_id=app.id,
            scope="country",
            country_code="us",
            device="iphone",
            provider="codex",
            country_codes=["us"],
        )
        run_id = run.id

    def fake_agent(**_kwargs: object) -> tuple[str, dict[str, AuditMarketSuggestion]]:
        return (
            "codex",
            {
                "us": AuditMarketSuggestion(
                    country="us",
                    language="English",
                    keywords=[
                        AuditKeywordSuggestion(
                            keyword="Natal Chart", intent="charts", rationale="Core."
                        ),
                        AuditKeywordSuggestion(
                            keyword="astrology", intent="broad", rationale="Broad."
                        ),
                    ],
                )
            },
        )

    measured_requests: list[tuple[list[str], str]] = []

    def fake_measurer(keywords: list[str], country: str) -> dict[str, PopularityReading]:
        measured_requests.append((keywords, country))
        return {"natal chart": PopularityReading(26, "measured")}

    synthesis_evidence: list[dict[str, object]] = []

    def capturing_synthesis(**kwargs: object) -> tuple[str, AuditSynthesisResult]:
        synthesis_evidence.extend(kwargs["evidence"])  # type: ignore[arg-type]
        return fake_audit_synthesis(**kwargs)

    AuditRunner(
        agent_runner=fake_agent,
        localization_runner=fake_localization_review,
        synthesis_runner=capturing_synthesis,
        listing_loader=lambda app_id, _country, **_kwargs: sample_listing(app_id),
        apple_client_factory=lambda _settings: FakeAppleClient(6771773264),
        popularity_measurer=fake_measurer,
    ).run(run_id)

    assert measured_requests == [(["Natal Chart", "astrology"], "us")]
    by_keyword = {str(item["keyword"]): item for item in synthesis_evidence}
    assert by_keyword["Natal Chart"]["applePopularity"] == 26
    assert by_keyword["Natal Chart"]["opportunityScore"] is not None
    assert by_keyword["astrology"]["applePopularity"] is None
    with session_scope() as session:
        payload = audit_dashboard_payload(session, app_id=1)
    keywords = {
        item["keyword"]: item
        for item in payload["run"]["countries"][0]["keywords"]  # type: ignore[index]
    }
    assert keywords["Natal Chart"]["popularity"] == 26
    assert keywords["Natal Chart"]["popularityStatus"] == "measured"
    assert keywords["astrology"]["popularity"] is None


def test_discovery_receives_app_scoped_apple_demand_signals(
    tmp_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from local_aso_tracker.models import AppleAdsSuggestion

    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    with session_scope() as session:
        app, _ = add_app(session, "Learn Astrology", 6771773264)
        other, _ = add_app(session, "Vocabulary", 1111111111)
        add_storefront(session, "us", "United States")
        add_target(session, app.apple_app_id, add_keyword(session, "natal chart")[0].keyword, "us")
        add_target(
            session,
            app.apple_app_id,
            add_keyword(session, "how to read my birth chart")[0].keyword,
            "us",
        )
        # Another app's keyword must not leak into this app's discovery context.
        add_target(
            session, other.apple_app_id, add_keyword(session, "vocabulaire")[0].keyword, "us"
        )
        session.add(
            AppleAdsSuggestion(
                app_id=app.id,
                country_or_region="US",
                text="zodiac",
                normalized_text="zodiac",
                popularity=None,
            )
        )
        run = create_audit_run(
            session,
            app_id=app.id,
            scope="country",
            country_code="us",
            device="iphone",
            provider="codex",
            country_codes=["us"],
        )
        run_id = run.id

    readings = {
        "natal chart": PopularityReading(26, "measured"),
        "how to read my birth chart": PopularityReading(5, "measured"),
        "zodiac": PopularityReading(36, "measured"),
        "vocabulaire": PopularityReading(18, "measured"),
    }
    discovery_contexts: list[dict[str, object]] = []

    def fake_agent(**kwargs: object) -> tuple[str, dict[str, AuditMarketSuggestion]]:
        discovery_contexts.append(kwargs["app_context"])  # type: ignore[arg-type]
        return (
            "codex",
            {
                "us": AuditMarketSuggestion(
                    country="us",
                    language="English",
                    keywords=[
                        AuditKeywordSuggestion(keyword="zodiac", intent="signs", rationale="x"),
                    ],
                )
            },
        )

    AuditRunner(
        agent_runner=fake_agent,
        localization_runner=fake_localization_review,
        synthesis_runner=fake_audit_synthesis,
        listing_loader=lambda app_id, _country, **_kwargs: sample_listing(app_id),
        apple_client_factory=lambda _settings: FakeAppleClient(6771773264),
        popularity_measurer=lambda keywords, _country: {
            key: value for key, value in readings.items() if key in {k.casefold() for k in keywords}
        },
    ).run(run_id)

    signals = discovery_contexts[0]["demandSignals"]["us"]  # type: ignore[index]
    assert signals["searchedQueries"] == [  # type: ignore[index]
        {"keyword": "zodiac", "applePopularity": 36},
        {"keyword": "natal chart", "applePopularity": 26},
    ]
    assert signals["floorQueries"] == ["how to read my birth chart"]  # type: ignore[index]
    assert signals["appleRelatedSearches"] == ["zodiac"]  # type: ignore[index]
    assert "vocabulaire" not in json.dumps(signals)


def test_discovery_prompt_mentions_demand_only_when_measured() -> None:
    from local_aso_tracker.services.agent import _build_audit_prompt

    markets = [{"country": "us", "language": "English"}]
    plain = _build_audit_prompt({"name": "App"}, markets)
    grounded = _build_audit_prompt(
        {"name": "App", "demandSignals": {"us": {"searchedQueries": []}}}, markets
    )
    assert "floorQueries" not in plain
    assert "searchedQueries" in grounded
    assert "one to three words" in grounded
    assert "brand" in grounded


def test_floor_warning_survives_a_full_editor_finding_list() -> None:
    from local_aso_tracker.services.audits import CountryFinding, _keep_demand_warning

    editor = [CountryFinding("info", "listing", f"Editor {index}", "d", []) for index in range(6)]
    warning = CountryFinding(
        "info", "competition", "8 of 8 checked phrases have too few searches to score", "d", []
    )
    kept = _keep_demand_warning(editor, [warning])
    assert len(kept) == 6
    assert kept[-1] is warning
    assert _keep_demand_warning(editor, []) == editor


def test_competitor_brand_searches_become_apple_ads_keywords(
    tmp_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from local_aso_tracker.models import AppleAdsSuggestion, CompetitorApp

    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    run_migrations()
    with session_scope() as session:
        app, _ = add_app(session, "Learn Astrology", 6771773264)
        add_storefront(session, "us", "United States")
        add_target(session, app.apple_app_id, add_keyword(session, "natal chart")[0].keyword, "us")
        session.add(CompetitorApp(apple_app_id=42, name="Co\u2013Star Personalized Astrology"))
        session.add(CompetitorApp(apple_app_id=43, name="CHANI: Your Astrology Guide"))
        for text in ("co star", "costar", "zodiac"):
            session.add(
                AppleAdsSuggestion(
                    app_id=app.id,
                    country_or_region="US",
                    text=text,
                    normalized_text=text,
                    popularity=None,
                )
            )
        run = create_audit_run(
            session,
            app_id=app.id,
            scope="country",
            country_code="us",
            device="iphone",
            provider="codex",
            country_codes=["us"],
        )
        run_id = run.id

    readings = {
        "natal chart": PopularityReading(26, "measured"),
        "zodiac": PopularityReading(36, "measured"),
        "costar": PopularityReading(56, "measured"),
        "co star": PopularityReading(5, "measured"),
        "chani": PopularityReading(12, "measured"),
    }
    discovery_contexts: list[dict[str, object]] = []

    def fake_agent(**kwargs: object) -> tuple[str, dict[str, AuditMarketSuggestion]]:
        discovery_contexts.append(kwargs["app_context"])  # type: ignore[arg-type]
        return (
            "codex",
            {
                "us": AuditMarketSuggestion(
                    country="us",
                    language="English",
                    keywords=[
                        AuditKeywordSuggestion(keyword="zodiac", intent="signs", rationale="x"),
                        AuditKeywordSuggestion(keyword="Chani", intent="brand", rationale="x"),
                    ],
                )
            },
        )

    fake_client = FakeAppleClient(6771773264)
    AuditRunner(
        agent_runner=fake_agent,
        localization_runner=fake_localization_review,
        synthesis_runner=fake_audit_synthesis,
        listing_loader=lambda app_id, _country, **_kwargs: sample_listing(app_id),
        apple_client_factory=lambda _settings: fake_client,
        popularity_measurer=lambda keywords, _country: {
            key: value for key, value in readings.items() if key in {k.casefold() for k in keywords}
        },
    ).run(run_id)

    signals = discovery_contexts[0]["demandSignals"]["us"]  # type: ignore[index]
    assert "costar" not in json.dumps(signals)
    with session_scope() as session:
        payload = audit_dashboard_payload(session, app_id=1)
    country = payload["run"]["countries"][0]  # type: ignore[index]
    assert [item["keyword"] for item in country["keywords"]] == ["zodiac"]
    paid = country["paidKeywords"]
    # Both spellings are kept: Apple scores them separately.
    assert [item["keyword"] for item in paid] == ["costar", "Chani", "co star"]
    assert paid[0]["brandOwner"] == "Co\u2013Star Personalized Astrology"
    assert paid[0]["popularity"] == 56
    assert ("costar", "us", "iphone") in fake_client.calls
