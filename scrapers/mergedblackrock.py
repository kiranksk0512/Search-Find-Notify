# scrapers/mergedblackrock.py
from __future__ import annotations

import asyncio
import os
import random
from typing import Dict, List, Tuple, Optional
from urllib.parse import urlsplit, urlunsplit
from datetime import datetime
from zoneinfo import ZoneInfo

from core.logger import get_company_logger
from core.context import get_company
from core.scrape_types import ScrapeResult
from core.decision import retry_and_decide

from models.mergedblackrock_job import MergedBlackRockJob
from util.kiranblackrock import get_jobs as get_kiran_jobs
from util.blackrock import get_jobs as get_classic_jobs

logger = get_company_logger()

USE_KIRAN = os.getenv("BLACKROCK_USE_KIRAN", "true").lower() not in ("0", "false", "no")
USE_CLASSIC = os.getenv("BLACKROCK_USE_CLASSIC", "true").lower() not in ("0", "false", "no")
PREFER_SOURCE = os.getenv("BLACKROCK_TIEBREAK", "kiran").lower()


def _normalize_url(u: str) -> str:
    if not u:
        return ""
    try:
        parts = urlsplit(u.strip())
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))
    except Exception:
        return u.strip()


def _list_to_url_map(jobs: List[object]) -> Dict[str, object]:
    out = {}
    for j in jobs or []:
        url = getattr(j, "url", None)
        if not url:
            if isinstance(j, dict):
                url = j.get("url")
        key = _normalize_url(url or "")
        if key and key not in out:
            out[key] = j
    return out


def _wrap_union_entry(primary: Optional[object], secondary: Optional[object]) -> MergedBlackRockJob:
    def v(obj, prop, default="Unknown"):
        if obj is None:
            return default
        if hasattr(obj, prop):
            return getattr(obj, prop) or default
        if isinstance(obj, dict):
            return obj.get(prop, default)
        return default

    canon = primary or secondary

    job_obj = MergedBlackRockJob(
        job_id=v(canon, "job_id"),
        title=v(canon, "title"),
        url=v(canon, "url"),
        location=v(canon, "location"),
        team=v(canon, "team"),
        category=v(canon, "category"),
        date_posted=v(canon, "date_posted"),
        kiran_job=primary if primary and primary.__class__.__name__.lower().startswith("kiran") else None,
        blackrock_job=primary if primary and not primary.__class__.__name__.lower().startswith("kiran") else None,
    )
    return job_obj


def _dedupe_union_wrapped(a_jobs: List[object], b_jobs: List[object]):
    a_map = _list_to_url_map(a_jobs)
    b_map = _list_to_url_map(b_jobs)

    a_keys, b_keys = set(a_map), set(b_map)
    both = sorted(a_keys & b_keys)
    only_a = sorted(a_keys - b_keys)
    only_b = sorted(b_keys - a_keys)

    prefer_kiran = (PREFER_SOURCE != "classic")

    union: List[MergedBlackRockJob] = []
    union.extend(_wrap_union_entry(a_map[k], None) for k in only_a)
    union.extend(_wrap_union_entry(b_map[k], None) for k in only_b)

    for k in both:
        union.append(
            _wrap_union_entry(a_map[k], b_map[k]) if prefer_kiran else _wrap_union_entry(b_map[k], a_map[k])
        )

    return union, only_a, only_b, both


async def _run_source(name: str, fn, min_expected: int) -> List[object]:
    try:
        res = await fn(min_expected_count=min_expected)
    except TypeError:
        res = await fn()
    except Exception as e:
        logger.error(f"[mergedblackrock] source={name} FAILED: {e}")
        return []
    return res if isinstance(res, list) else (res.get("jobs") or [])


def should_persist_jobs(result: ScrapeResult, min_expected: int = 10):
    company = get_company()

    if not result:
        return False, "no_result"

    if result.anomalous_zero:
        return False, "anomalous_zero"

    total = len(result.jobs)
    if total == 0:
        return False, "zero_jobs"

    if total < min_expected:
        return False, f"too_few({total}<{min_expected})"

    return True, "ok"


async def _scrape_once(label: str, min_expected: int) -> ScrapeResult:
    company = get_company()
    await asyncio.sleep(1.0 + random.random() * 3)

    logger.info(f"[{company}] ▶️ BlackRock scrape ({label})")

    if not (USE_KIRAN or USE_CLASSIC):
        return ScrapeResult(
            jobs=[],
            scrape_id=str(os.getpid()),
            anomalous_zero=True,
            stats={"sources": []},
            meta={"disabled": True},
        )

    tasks = []
    sources = {}

    if USE_KIRAN:
        tasks.append(_run_source("kiran", get_kiran_jobs, min_expected))
        sources["kiran"] = True
    else:
        sources["kiran"] = False

    if USE_CLASSIC:
        tasks.append(_run_source("classic", get_classic_jobs, min_expected))
        sources["classic"] = True
    else:
        sources["classic"] = False

    results = await asyncio.gather(*tasks)

    a_jobs = results[0] if USE_KIRAN else []
    b_jobs = results[1] if USE_CLASSIC else results[0] if results else []

    union, only_a, only_b, both = _dedupe_union_wrapped(a_jobs, b_jobs)
    total = len(union)

    anomalous_zero = (total == 0)

    return ScrapeResult(
        jobs=union,
        scrape_id=str(os.getpid()),
        anomalous_zero=anomalous_zero,
        stats={
            "total": total,
            "only_kiran": len(only_a),
            "only_classic": len(only_b),
            "both": len(both),
            "sources": sources,
        },
        meta={"label": label},
    )


async def get_jobs(min_expected_count: int = 10) -> ScrapeResult:
    company = get_company()

    first = await _scrape_once("first-pass", min_expected_count)

    decided = await retry_and_decide(
        company=company,
        logger=logger,
        first_result=first,
        retry_fn=lambda: _scrape_once("retry-after-anomaly", min_expected_count),
        min_expected_count=min_expected_count,
        should_persist_fn=should_persist_jobs,
    )

    return decided
