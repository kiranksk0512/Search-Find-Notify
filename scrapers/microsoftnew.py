import aiohttp
import json
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from multidict import MultiDict
from typing import List, Dict, Any, Optional

from core.logger import get_company_logger
from core.context import get_company
from core.scrape_types import ScrapeResult
from core.decision import retry_and_decide

from models.microsoftnew_job import MicrosoftNewJob


# ============================================================
# CONFIG
# ============================================================

BASE_URL = "https://apply.careers.microsoft.com/api/pcsx/search"
PAGE_SIZE = 10

PROFESSIONS = [
    "product management",
    "technology sales",
    "digital sales and solutions",
    "consulting services",
    "design & creative",
    "technical support",
    "analytics",
    "learning",
    "software engineering",
    "data center",
    "research, applied, & data sciences",
]

logger = get_company_logger("microsoftnew")


# ============================================================
# UTIL HELPERS
# ============================================================

def new_scrape_id() -> str:
    return str(uuid.uuid4())[:8]


def convert_ts(ts: Optional[int]) -> str:
    try:
        if not ts:
            return "Unknown"
        dt = datetime.fromtimestamp(ts, tz=ZoneInfo("America/New_York"))
        return dt.strftime("%b %d, %Y %I:%M %p %Z")
    except Exception:
        return "Unknown"


def log_page_fetch(scrape_id: str, start: int, attempt: int, status: int, elapsed_ms: int, size: int):
    logger.info(
        f"[MicrosoftNew] [{scrape_id}] ⬇️ PageFetch start={start} "
        f"attempt={attempt} status={status} ms={elapsed_ms} size={size}"
    )


def log_page_stats(scrape_id: str, start: int, parsed: int, added: int, total: int):
    logger.info(
        f"[MicrosoftNew] [{scrape_id}] 📦 PageStats start={start} "
        f"parsed={parsed} added={added} total={total}"
    )


def log_stop(scrape_id: str, reason: str):
    logger.warning(f"[MicrosoftNew] [{scrape_id}] 🛑 Stop: {reason}")


def log_parse_error(scrape_id: str, start: int, exc: Exception, snippet: str):
    logger.error(
        f"[MicrosoftNew] [{scrape_id}] ❌ ParseError start={start}: {exc}\n"
        f"snippet={snippet[:300]}"
    )


# ============================================================
# REQUEST BUILDING
# ============================================================

def build_params(start: int) -> MultiDict:
    p = MultiDict()
    p.add("domain", "microsoft.com")
    p.add("query", "")
    p.add("location", "United States")
    p.add("start", str(start))
    p.add("sort_by", "timestamp")

    for prof in PROFESSIONS:
        p.add("filter_profession", prof)

    return p


# ============================================================
# PAGE FETCH
# ============================================================

async def fetch_page(session: aiohttp.ClientSession, scrape_id: str, params: MultiDict, start: int, attempt: int = 1):
    t0 = time.time()

    try:
        async with session.get(BASE_URL, params=params) as resp:
            text = await resp.text()
            elapsed_ms = int((time.time() - t0) * 1000)

            log_page_fetch(scrape_id, start, attempt, resp.status, elapsed_ms, len(text))

            if resp.status != 200:
                snippet = text[:200]
                logger.warning(
                    f"[MicrosoftNew] [{scrape_id}] ⚠️ Non-200 start={start} status={resp.status} body={snippet}"
                )
                return None

            try:
                return json.loads(text)
            except Exception as e:
                log_parse_error(scrape_id, start, e, text)
                return None

    except Exception as e:
        logger.error(
            f"[MicrosoftNew] [{scrape_id}] ❌ Exception fetching page start={start}: {e}"
        )
        return None


# ============================================================
# JOB PARSING
# ============================================================

def parse_job(scrape_id: str, raw: Dict[str, Any], start: int) -> Optional[MicrosoftNewJob]:
    try:
        job_id = str(raw["id"])
        title = raw.get("name", "Unknown")

        url = f"https://apply.careers.microsoft.com{raw.get('positionUrl', '')}"

        locations = raw.get("standardizedLocations") or raw.get("locations") or ["Unknown"]
        location = locations[0]

        job = MicrosoftNewJob(
            job_id=job_id,
            title=title,
            url=url,
            location=location,
            department=raw.get("department", "Unknown"),
            display_job_id=raw.get("displayJobId", ""),
            work_location=raw.get("workLocationOption", "Unknown"),
            posted=raw.get("postedTs"),
            created_date=raw.get("createdDateTs"),
            isHotJob=raw.get("isHotJob", 0)
        )

        # logger.debug(f"[MicrosoftNew] [{scrape_id}] 🆕 Parsed {job_id} – {title}")
        return job

    except Exception as e:
        snippet = json.dumps(raw)[:200]
        log_parse_error(scrape_id, start, e, snippet)
        return None


# ============================================================
# MAIN PAGE SCRAPER (NO RETRY HERE)
# ============================================================

async def scrape_all_pages(scrape_id: str) -> List[MicrosoftNewJob]:
    logger.info(f"[MicrosoftNew] [{scrape_id}] ▶️ Begin multi-page scrape")

    jobs: List[MicrosoftNewJob] = []
    seen = set()

    empty_pages = 0
    start = 0

    async with aiohttp.ClientSession() as session:
        while True:
            params = build_params(start)
            page = await fetch_page(session, scrape_id, params, start)

            if not page:
                empty_pages += 1
                log_stop(scrape_id, f"FailedPage start={start} empty={empty_pages}")

                if empty_pages >= 3:
                    log_stop(scrape_id, "3 consecutive failed pages")
                    break

                start += PAGE_SIZE
                continue

            empty_pages = 0

            positions = page.get("data", {}).get("positions", []) or []
            parsed_count = len(positions)

            if parsed_count == 0:
                empty_pages += 1
                log_stop(scrape_id, f"NoPositions start={start} empty={empty_pages}")

                if empty_pages >= 3:
                    log_stop(scrape_id, "3 consecutive empty pages")
                    break

                start += PAGE_SIZE
                continue

            added_count = 0
            for raw in positions:
                jid = str(raw.get("id"))

                if jid in seen:
                    continue
                seen.add(jid)

                job_obj = parse_job(scrape_id, raw, start)
                if job_obj:
                    jobs.append(job_obj)
                    added_count += 1

            log_page_stats(scrape_id, start, parsed_count, added_count, len(jobs))

            total = page.get("data", {}).get("count")
            if total and len(seen) >= total:
                log_stop(scrape_id, f"Reached API total={total}")
                break

            start += PAGE_SIZE

    logger.info(f"[MicrosoftNew] [{scrape_id}] 🎉 Completed scrape total={len(jobs)}")
    return jobs


# ============================================================
# RETRY + DECISION WRAPPER
# ============================================================

def _should_persist(result: ScrapeResult, min_expected_count: int = 30):
    sid = result.scrape_id

    if result is None:
        return False, "no_result"

    if result.anomalous_zero:
        logger.warning(f"[MicrosoftNew] [{sid}] 🧯 anomalous_zero=True")
        return False, "anomalous_zero"

    count = len(result.jobs or [])

    if count == 0:
        return False, "zero_jobs"

    if count < min_expected_count:
        logger.warning(
            f"[MicrosoftNew] [{sid}] 🧯 Too few jobs: {count} < {min_expected_count}"
        )
        return False, f"too_few({count}<{min_expected_count})"

    return True, "ok"


async def _scrape_once(label: str) -> ScrapeResult:
    scrape_id = new_scrape_id()
    logger.info(f"[MicrosoftNew] [{scrape_id}] 🚀 Starting scrape ({label})")

    try:
        jobs = await scrape_all_pages(scrape_id)
        anomalous_zero = (len(jobs) == 0)

        return ScrapeResult(
            jobs=jobs,
            scrape_id=scrape_id,
            anomalous_zero=anomalous_zero,
            stats={"count": len(jobs)},
        )

    except Exception as e:
        logger.exception(f"[MicrosoftNew] [{scrape_id}] ❌ Scrape failed: {e}")
        return ScrapeResult(
            jobs=[],
            scrape_id=scrape_id,
            anomalous_zero=True,
            error=str(e),
            stats={"count": 0},
        )


# ============================================================
# PUBLIC ENTRY POINT (used by main.py)
# ============================================================

async def get_jobs(min_expected_count: int = 50) -> ScrapeResult:
    company = get_company()

    first = await _scrape_once("first-pass")

    decided = await retry_and_decide(
        company=company,
        logger=logger,
        first_result=first,
        retry_fn=lambda: _scrape_once("retry"),
        min_expected_count=min_expected_count,
        should_persist_fn=_should_persist,
    )

    return decided
