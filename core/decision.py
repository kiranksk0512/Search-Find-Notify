from __future__ import annotations
from typing import Callable, Awaitable, Optional, Dict, Any

# Result contract your code already uses
# expected keys: "jobs" (list), "scrape_id" (str), "anomalous_zero" (bool)
# optional keys: "default_count", "new_count"
Result = Dict[str, Any]
RetryFn = Callable[[], Awaitable[Result]]
ShouldPersistFn = Callable[[Result, int], bool]


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
    needs_retry = result.get("anomalous_zero") or too_few

    if needs_retry and retry_fn:
        reason = (
            "anomalous_zero" if result.get("anomalous_zero")
            else f"too_few({len(result.get('jobs') or [])}<{min_expected_count})"
        )

        logger.warning(
            f"[company={company}] [{result.get('scrape_id','na')}] "
            f"🧯 {reason}; retrying once…"
        )

        retry = await retry_fn()

        if len(retry.get("jobs") or []) >= len(result.get("jobs") or []):
            result = retry
        # else keep original

    should_persist, decision_reason = should_persist_fn(result, min_expected_count)

    result["should_persist"] = should_persist
    result["decision_reason"] = decision_reason

    logger.info(
        f"[company={company}] [{result.get('scrape_id','na')}] "
        f"🧭 decision={decision_reason}, persist={should_persist}, "
        f"count={len(result.get('jobs') or [])}"
    )

    return result

