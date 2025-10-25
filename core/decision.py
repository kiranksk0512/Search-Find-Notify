from __future__ import annotations
from typing import Callable, Awaitable, Optional, Dict, Any, Tuple

Result = Dict[str, Any]
RetryFn = Callable[[], Awaitable[Result]]
ShouldPersistFn = Callable[[Result, int], Tuple[bool, str]]  # returns (should_persist, decision_reason)

async def retry_and_decide(
    *,
    company: str,
    logger,
    first_result: Result,
    retry_fn: Optional[RetryFn],
    min_expected_count: int,
    should_persist_fn: ShouldPersistFn,
) -> Result:
    result = first_result

    too_few = len(result.get("jobs") or []) < min_expected_count
    needs_retry = bool(result.get("anomalous_zero")) or too_few

    if needs_retry and retry_fn:
        reason = "anomalous_zero" if result.get("anomalous_zero") else f"too_few({len(result.get('jobs') or [])}<{min_expected_count})"
        logger.warning(f"[company={company}] [{result.get('scrape_id','na')}] 🧯 {reason}; retrying once…")

        retry = await retry_fn()
        if len(retry.get("jobs") or []) >= len(result.get("jobs") or []):
            result = retry
        else:
            logger.info(f"[company={company}] [{result.get('scrape_id','na')}] ⚠️ Retry did not improve count; keeping first result.")

    should_persist, decision_reason = should_persist_fn(result, min_expected_count)
    result["should_persist"] = should_persist
    result["decision_reason"] = decision_reason

    # Optional logging of Meta-only counters if present (others will show 0)
    stats = result.get("stats") or {}
    dcnt = stats.get("default_count", 0)
    ncnt = stats.get("new_count", 0)

    logger.info(
        f"[company={company}] [{result.get('scrape_id','na')}] 🧭 decision={decision_reason} "
        f"persist={should_persist} total={len(result.get('jobs') or [])} default={dcnt} new={ncnt}"
    )
    return result
