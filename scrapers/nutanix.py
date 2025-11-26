# scrapers/nutanix.py

from __future__ import annotations

import asyncio
import random
import uuid
import time
from typing import List, Dict, Any, Tuple
import os
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from core.logger import get_company_logger
from core.context import get_company
from core.scrape_types import ScrapeResult
from core.decision import retry_and_decide
from core.fetcher import get_text_resilient

from models.nutanix_job import NutanixJob

logger = get_company_logger()

BASE_URL = "https://careers.nutanix.com/en/jobs/"

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

MAX_PAGES = 120
NUTANIX_COOKIE_HEADER = os.getenv("NUTANIX_COOKIE") or ""


def _build_page_url(page: int, pagesize: int = 20) -> str:
    params = {
        "page": page,
        "pagesize": pagesize,
        "country": "United States"
    }
    return f"{BASE_URL}?{urlencode(params)}"


def _parse_jobs(html: str) -> List[NutanixJob]:
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    for card in soup.select("div.card.card-job"):
        title_a = card.select_one("h3.card-title a")
        if not title_a:
            continue

        title = title_a.get_text(strip=True)
        relative = title_a.get("href", "")
        url = urljoin(BASE_URL, relative)

        team_el = card.select_one("p.card-subtitle")
        team = team_el.get_text(strip=True) if team_el else "Unknown"

        actions = card.select_one("div.card-job-actions.js-job")
        job_id = actions.get("data-id") if actions and actions.has_attr("data-id") else None

        loc_lis = card.select("ul.locations li")
        locations = [li.get_text(strip=True) for li in loc_lis] or ["Unknown"]

        jobs.append(
            NutanixJob(
                job_id=job_id or "",
                title=title,
                url=url,
                locations=locations,
                team=team,
            )
        )

    return jobs


async def _fetch_page(url: str, headers: Dict[str, str], scrape_id: str, page: int):
    company = get_company()
    t0 = time.time()
    text = await get_text_resilient(
        url,
        headers=headers,
        max_retries=3,
        base_timeout=10,
        max_backoff=20,
        logger=logger,
    )
    dt = int((time.time() - t0) * 1000)
    if text is not None:
        logger.info(
            f"[company={company}] [{scrape_id}] ⬇️ Page {page} OK (ms={dt} size={len(text)})"
        )
    else:
        logger.error(
            f"[company={company}] [{scrape_id}] ❌ Page {page} fetch failed (ms={dt})"
        )
    return text


def should_persist_jobs(result: ScrapeResult, min_expected_count: int = 10) -> Tuple[bool, str]:
    company = get_company()

    if result is None:
        return False, "no_result"

    if result.anomalous_zero:
        return False, "anomalous_zero"

    n = len(result.jobs or [])

    if n == 0:
        return False, "zero_jobs"

    if n < min_expected_count:
        return False, f"too_few({n}<{min_expected_count})"

    return True, "ok"

async def _scrape_once(label: str, company: str) -> ScrapeResult:
        ua = random.choice(USER_AGENTS)
        scrape_id = str(uuid.uuid4())[:8]

        logger.info(
            f"[company={company}] [{scrape_id}] 🚀 Starting Nutanix scrape ({label})"
        )

        headers = {
            "User-Agent": ua,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": BASE_URL,
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Sec-Ch-Ua": '"Chromium";v="120", "Not A(Brand";v="24", "Google Chrome";v="120"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
        }

        if NUTANIX_COOKIE_HEADER:
            headers["Cookie"] = NUTANIX_COOKIE_HEADER
        all_jobs: List[NutanixJob] = []
        empty_streak = 0
        page = 1
        pages_processed = 0

        while page <= MAX_PAGES:
            url = _build_page_url(page)
            html = await _fetch_page(url, headers, scrape_id, page)
            pages_processed += 1

            if not html:
                empty_streak += 1
                logger.warning(
                    f"[company={company}] [{scrape_id}] ⚠️ Empty HTML page {page}. streak={empty_streak}/3"
                )
            else:
                jobs = _parse_jobs(html)
                if len(jobs) == 0:
                    empty_streak += 1
                    logger.info(
                        f"[company={company}] [{scrape_id}] 🈳 Page {page} has 0 jobs. streak={empty_streak}/3"
                    )
                else:
                    empty_streak = 0
                    all_jobs.extend(jobs)
                    logger.info(
                        f"[company={company}] [{scrape_id}] 📦 Page {page}: {len(jobs)} jobs"
                    )

            if empty_streak >= 3:
                logger.warning(
                    f"[company={company}] [{scrape_id}] 🛑 Stopping: 3 empty pages reached."
                )
                break

            page += 1
            await asyncio.sleep(random.uniform(0.25, 0.6))

        by_id = {job.job_id: job for job in all_jobs}
        final_jobs = list(by_id.values())

        anomalous_zero = len(final_jobs) == 0

        return ScrapeResult(
            jobs=final_jobs,
            scrape_id=scrape_id,
            anomalous_zero=anomalous_zero,
            stats={"pages": pages_processed},
            meta={"source": "phenom-html"},
        )

async def get_jobs(min_expected_count: int = 10) -> ScrapeResult:
    company = get_company()

    first = await _scrape_once("first-pass", company=company)

    decided = await retry_and_decide(
        company=company,
        logger=logger,
        first_result=first,
        retry_fn=lambda: _scrape_once("retry", company=company),
        min_expected_count=min_expected_count,
        should_persist_fn=should_persist_jobs,
    )

    return decided
