"""Explicitly opt-in live Apple contract check."""

import os

import pytest

from local_aso_tracker.apple.client import AppleSearchClient, extract_rank


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("ASO_RUN_INTEGRATION") != "1", reason="set ASO_RUN_INTEGRATION=1")
async def test_real_apple_search_contract() -> None:
    async with AppleSearchClient(request_delay=0) as client:
        outcome = await client.search("learn astrology", "us")
        ipad_outcome = await client.search("learn astrology", "us", "ipad")
    result = extract_rank(outcome.response, 6771773264)
    assert outcome.response.result_count >= 0
    assert isinstance(result.found, bool)
    assert ipad_outcome.response.result_count >= 0
