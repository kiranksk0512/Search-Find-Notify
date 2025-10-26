from __future__ import annotations
from typing import Callable, Awaitable, Optional, Tuple
from core.scrape_types import ScrapeResult

RetryFn = Callable[[], Awaitable[ScrapeResult]]
ShouldPersistFn = Callable[[ScrapeResult, int], Tuple[bool, str]]

async def retry_and_decide(
    *,
    company: str,
    logger,
    first_result: ScrapeResult,
    retry_fn: Optional[RetryFn],
    min_expected_count: int,
    should_persist_fn: ShouldPersistFn,
) -> ScrapeResult:
    result = first_result

    too_few = len(result.jobs) < min_expected_count
    needs_retry = result.anomalous_zero or too_few

    if needs_retry and retry_fn:
        reason = (
            "anomalous_zero"
            if result.anomalous_zero
            else f"too_few({len(result.jobs)}<{min_expected_count})"
        )
        logger.warning(f"[company={company}] [{result.scrape_id}] 🧯 {reason}; retrying once…")

        retry = await retry_fn()
        if len(retry.jobs) >= len(result.jobs):
            result = retry
        else:
            logger.info(
                f"[company={company}] [{result.scrape_id}] ⚠️ Retry did not improve; keeping original result."
            )

    # Final decision
    result.should_persist, result.decision_reason = should_persist_fn(result, min_expected_count)

    stats = result.stats or {}
    dcnt = stats.get("default_count", 0)
    ncnt = stats.get("new_count", 0)
    logger.info(
        f"[company={company}] [{result.scrape_id}] 🧭 decision={result.decision_reason} "
        f"persist={result.should_persist} total={len(result.jobs)} "
        f"default={dcnt} new={ncnt}"
    )

    return result
