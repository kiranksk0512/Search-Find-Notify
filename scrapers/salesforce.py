from __future__ import annotations

import asyncio
import random
import uuid
import time
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlencode, urljoin

import aiohttp
from bs4 import BeautifulSoup

from core.logger import get_company_logger
from core.context import get_company
from core.scrape_types import ScrapeResult
from core.decision import retry_and_decide

from models.salesforce_job import SalesforceJob

logger = get_company_logger()

BASE_URL = "https://careers.salesforce.com/en/jobs/"

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)... Chrome/142.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)... Chrome/142.0",
    "Mozilla/5.0 (X11; Linux x86_64)... Chrome/142.0",
]


def _hash_short(s: str) -> str:
    try:
        return hashlib.sha256(str(s).encode("utf-8")).hexdigest()[:10]
    except:
        return "na"


def _parse_jobs_from_html(html: str) -> List[SalesforceJob]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: List[SalesforceJob] = []

    for card in soup.select("div.card.card-job"):
        # Title + URL
        title_a = card.select_one("h3.card-title a")
        if not title_a:
            continue

        title = title_a.get_text(strip=True)
        relative = title_a.get("href", "")
        url = urljoin(BASE_URL, relative)

        # Team
        team_el = card.select_one("p.card-subtitle")
        team = team_el.get_text(strip=True) if team_el else "Unknown"

        # Job ID
        actions = card.select_one("div.card-job-actions.js-job")
        job_id = actions.get("data-id") if actions and actions.has_attr("data-id") else _hash_short(title)

        # Locations
        loc_lis = card.select("ul.locations li")
        locations = [li.get_text(strip=True) for li in loc_lis] or ["Unknown"]

        jobs.append(
            SalesforceJob(
                job_id=job_id,
                title=title,
                url=url,
                locations=locations,
                team=team,
            )
        )

    return jobs


# def _get_last_page(html: str) -> int:
#     soup = BeautifulSoup(html, "html.parser")
#     nav = soup.select_one('nav[aria-label="Pagination"]')
#     if not nav:
#         return 1
#     nums = []
#     for a in nav.select("ul.pagination li.page-item a"):
#         t = a.get_text(strip=True)
#         if t.isdigit():
#             nums.append(int(t))
#     return max(nums) if nums else 1


async def _fetch_html(session: aiohttp.ClientSession, url: str, scrape_id: str, page: int):
    company = get_company()
    t0 = time.time()

    try:
        async with session.get(url) as resp:
            text = await resp.text()
            dt = int((time.time() - t0) * 1000)

            logger.info(
                f"[company={company}] [{scrape_id}] ⬇️ HTML fetch OK (page={page} ms={dt} size={len(text)})"
            )
            return text
    except Exception as e:
        dt = int((time.time() - t0) * 1000)
        logger.error(
            f"[company={company}] [{scrape_id}] ❌ HTML fetch failed (page={page} ms={dt}): {e}"
        )
        return None


def _build_page_url(page: int, country: str = "United States of America", pagesize: int = 20) -> str:
    params = {
        "page": page,
        "country": country,
        "pagesize": pagesize,
    }
    return f"{BASE_URL}?{urlencode(params)}"

def should_persist_jobs(result: ScrapeResult, min_expected_count: int = 30) -> Tuple[bool, str]:
    company = get_company()

    if result is None:
        return False, "no_result"

    if result.anomalous_zero:
        logger.warning(f"[company={company}] [{result.scrape_id}] anomalous_zero=True")
        return False, "anomalous_zero"

    count = len(result.jobs or [])
    if count == 0:
        return False, "zero_jobs"

    if count < min_expected_count:
        return False, f"too_few({count}<{min_expected_count})"

    return True, "ok"


async def _scrape_once(label: str):
        company = get_company()
        ua = random.choice(USER_AGENTS)
        scrape_id = str(uuid.uuid4())[:8]

        logger.info(
            f"[company={company}] [{scrape_id}] 🚀 Starting Salesforce scrape ({label})"
        )

        headers = {
            "User-Agent": ua,
            "Accept-Language": "en-US,en;q=0.9",
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            all_jobs = []
            empty_streak = 0
            page = 1

            while True:
                url = _build_page_url(page)
                html = await _fetch_html(session, url, scrape_id, page)

                if not html:
                    empty_streak += 1
                    logger.warning(
                        f"[company={company}] [{scrape_id}] ⚠️ Empty HTML (page={page}). "
                        f"empty_streak={empty_streak}/3"
                    )
                else:
                    jobs = _parse_jobs_from_html(html)

                    if len(jobs) == 0:
                        empty_streak += 1
                        logger.info(
                            f"[company={company}] [{scrape_id}] 🈳 No jobs on page {page}. "
                            f"empty_streak={empty_streak}/3"
                        )
                    else:
                        empty_streak = 0  # reset streak
                        all_jobs.extend(jobs)
                        logger.info(
                            f"[company={company}] [{scrape_id}] 📦 Page {page}: {len(jobs)} jobs"
                        )

                # Stop rule:
                if empty_streak >= 3:
                    logger.warning(
                        f"[company={company}] [{scrape_id}] 🛑 Stopping pagination after "
                        f"{empty_streak} consecutive empty responses."
                    )
                    break

                page += 1
                await asyncio.sleep(random.uniform(0.3, 0.7))
            last_page = page - 1
        # dedupe
        by_id = {job.job_id: job for job in all_jobs}
        final_jobs = list(by_id.values())

        anomalous_zero = len(final_jobs) == 0

        logger.info(
            f"[company={company}] [{scrape_id}] 🎉 Salesforce total={len(final_jobs)} pages={last_page}"
        )

        return ScrapeResult(
            jobs=final_jobs,
            scrape_id=scrape_id,
            anomalous_zero=anomalous_zero,
            stats={"pages": last_page},
            meta={"note": "html-scrape"},
        )

async def get_jobs(min_expected_count: int = 30) -> ScrapeResult:

    company = get_company()

    # First scrape
    first = await _scrape_once(label="first-pass")

   
    decided = await retry_and_decide(
        company=company,
        logger=logger,
        first_result=first,
        retry_fn=lambda: _scrape_once("retry"),
        min_expected_count=min_expected_count,
        should_persist_fn=should_persist_jobs,
    )

    return decided
