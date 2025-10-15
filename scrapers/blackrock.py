"""
Asynchronous scraper for BlackRock careers.

This module follows the patterns used throughout the ``scrapers`` package
for other companies.  It periodically fetches a list of current job
postings and returns them as instances of :class:`models.blackrock_job.BlackrockJob`.

Unlike some other companies in this repository (e.g. Amazon or Meta),
BlackRock does not expose a public JSON or GraphQL endpoint for its
careers search.  The dynamic search interface on
``careers.blackrock.com`` uses background API calls behind a
client-side layer that is difficult to access without reproducing
browser state and tokens.  Instead, BlackRock publishes a fully
comprehensive XML sitemap which lists every active job posting.  Each
individual job page includes a ``<script type="application/ld+json">``
block containing structured data about the job, including the title,
location, posting date and identifier.  This scraper fetches the
sitemap, extracts the job URLs, retrieves each job page, parses the
embedded JSON‑LD and returns a list of jobs matching the user’s
filters.

References:

* The search results page uses ``data-ajax-url="/search-jobs/results"`` and
  ``data-ajax-post-url="/search-jobs/resultspost"`` attributes but
  requires dynamic tokens; the sitemap avoids this complexity【605730603268694†L92-L104】.
* The ``GetSearchRequestGeoLocation`` endpoint reveals the expected
  parameter names for the dynamic search API but does not return
  results on its own【508216137743536†L0-L7】.
* Each job page embeds structured data describing the posting inside
  a ``<script type="application/ld+json">`` block; this includes
  fields such as ``title``, ``datePosted`` and location data【214329013590365†L70-L76】.
* The XML sitemap published by BlackRock lists all job URLs along
  with last‑modified dates, making it a reliable source to crawl【517520700742628†L24-L27】.

Usage:
    The ``get_jobs`` coroutine is discovered automatically by
    ``core.scraper_loader.discover_scrapers``.  It accepts no
    arguments and returns a list of :class:`BlackrockJob` objects.  To
    customise which jobs are returned (e.g. by location or team) edit
    the ``FILTERS`` dictionary below.

Note:
    Network calls are retried up to three times with a short delay as
    defined in ``core.fetcher``.  A semaphore limits concurrent
    requests to avoid overwhelming BlackRock’s servers.  If the
    environment cannot access the network (e.g. due to corporate
    firewall rules), the scraper will return an empty list.
"""

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import aiohttp
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

from models.blackrock_job import BlackrockJob
from core.logger import get_company_logger


# URL of the XML sitemap that lists all current BlackRock job postings.
SITEMAP_URL = "https://careers.blackrock.com/sitemap.xml"

# Semaphore limit for concurrent HTTP requests.  Adjust this value
# downward if you encounter rate limiting or network timeouts.
CONCURRENCY_LIMIT = 5
counter = 0

# Filters to restrict which jobs are returned.  Update these lists to
# constrain the scraper to a particular country, city or team.  A
# ``None`` value means no filtering on that dimension.
FILTERS = {
    "countries": ["United States"],  # e.g. ["United States", "Canada"]
    "cities": None,                   # e.g. ["New York", "San Francisco"]
    "teams": ["engineer"],                    # e.g. ["Engineering", "Data Analytics"]
}

async def fetch_text(session: aiohttp.ClientSession, url: str) -> Optional[str]:
    """Fetch the text content of a URL with retry logic.

    Args:
        session: An existing aiohttp ClientSession.
        url: The URL to fetch.

    Returns:
        The response text if the request succeeds, otherwise ``None``.
    """
    logger = get_company_logger()
    
    # Common headers to mimic a real browser.  Without a realistic
    # User‑Agent some BlackRock endpoints return 403 Forbidden.  We
    # include Accept and Accept-Language headers to look like a
    # standard web browser.
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        " AppleWebKit/537.36 (KHTML, like Gecko)"
        " Chrome/117.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9"
        ",image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }

    for attempt in range(1, 4):
        try:
            async with session.get(url, headers=DEFAULT_HEADERS, timeout=20) as resp:
                if resp.status == 200:
                    return await resp.text()
                else:
                    logger.warning(f"⚠️ Status {resp.status} fetching {url}")
        except Exception as exc:
            logger.warning(f"⚠️ Attempt {attempt} failed for {url}: {exc}")
        await asyncio.sleep(2)
    logger.error(f"❌ All attempts failed for {url}")
    return None


def parse_sitemap(xml_text: str) -> List[str]:
    """Parse the XML sitemap and return a list of job URLs.

    Only URLs containing ``/job/`` in their path are considered job
    postings; other links (e.g. category pages) are ignored.

    Args:
        xml_text: The raw XML string from the sitemap.

    Returns:
        A list of absolute URLs to individual job pages.
    """
    job_urls: List[str] = []
    try:
        # The sitemap uses the standard namespace for sitemaps.
        root = ElementTree.fromstring(xml_text)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        for loc in root.findall(".//sm:loc", ns):
            url = loc.text or ""
            if "/job/" in url:
                job_urls.append(url.strip())
    except Exception:
        # Fall back to a regex parse if XML parsing fails
        for match in re.findall(r"<loc>([^<]+/job/[^<]+)</loc>", xml_text):
            job_urls.append(match.strip())
    return job_urls


def extract_jsonld(html_text: str) -> Optional[dict]:
    """Extract the JobPosting JSON‑LD object from an HTML page.

    Args:
        html_text: Raw HTML of a job page.

    Returns:
        A dict representing the parsed JSON‑LD JobPosting, or ``None`` if not
        found.
    """
    # Match the first script tag of type application/ld+json.  Some pages
    # may contain multiple JSON‑LD entries (e.g. for breadcrumb lists);
    # therefore we later look for an entry with "@type": "JobPosting".
    script_matches = re.findall(
        r"<script[^>]*type=\"application/ld\+json\"[^>]*>(.*?)</script>",
        html_text,
        re.DOTALL | re.IGNORECASE,
    )
    for script in script_matches:
        try:
            data = json.loads(script.strip())
        except Exception:
            continue
        # The JSON may be a list or a single dict.  Find a JobPosting.
        if isinstance(data, dict) and data.get("@type") == "JobPosting":
            return data
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("@type") == "JobPosting":
                    return item
    return None


def passes_filters(job_data: dict) -> bool:
    # Country filter: match if any configured country is a prefix of the
    # job's country string (so 'United States' matches 'United States of America').
    if FILTERS["countries"]:
        locations = job_data.get("jobLocation") or []
        if isinstance(locations, dict):
            locations = [locations]
        if not any(
            (
                loc.get("address", {}).get("addressCountry", "").lower().startswith(c.lower())
            )
            for loc in locations
            for c in FILTERS["countries"]
        ):
            return False

    # City filter: exact case-insensitive match if provided.
    if FILTERS["cities"]:
        locations = job_data.get("jobLocation") or []
        if isinstance(locations, dict):
            locations = [locations]
        if not any(
            (
                loc.get("address", {}).get("addressLocality", "").lower() == c.lower()
            )
            for loc in locations
            for c in FILTERS["cities"]
        ):
            return False

    # Team filter: search the job title, department name and hiring organisation
    # for any of the keywords in FILTERS["teams"].
    if FILTERS["teams"]:
        title = job_data.get("title", "")
        department_name = job_data.get("department", {}).get("name", "")
        org_name = job_data.get("hiringOrganization", {}).get("name", "")
        combined = f"{title} {department_name} {org_name}".lower()
        if not any(term.lower() in combined for term in FILTERS["teams"]):
            return False

    return True


async def fetch_job(session: aiohttp.ClientSession, url: str) -> Optional[BlackrockJob]:
    """Fetch a single job page and return a BlackrockJob object.

    Args:
        session: An existing aiohttp ClientSession.
        url: The absolute URL of the job posting.

    Returns:
        A populated :class:`BlackrockJob` instance if parsing succeeds and
        the job passes all filters; otherwise ``None``.
    """
    html_text = await fetch_text(session, url)
    if not html_text:
        return None
    job_data = extract_jsonld(html_text)
    if not job_data:
        return None
    if not passes_filters(job_data):
        return None
    # Extract required fields with sensible fallbacks
    title = job_data.get("title", "Unknown")
    # Parse datePosted into a human readable format
    raw_date = job_data.get("datePosted")
    if raw_date:
        try:
            dt = datetime.fromisoformat(raw_date)
            dt_edt = dt.astimezone(ZoneInfo("America/New_York"))
            date_posted = dt_edt.strftime("%b %d, %Y")
        except Exception:
            date_posted = raw_date
    else:
        date_posted = "Unknown"
    # Construct location string from address components
    location_parts = []
    try:
        addr = job_data["jobLocation"]["address"]
        for key in ["addressLocality", "addressRegion", "addressCountry"]:
            part = addr.get(key)
            if part:
                location_parts.append(part)
    except Exception:
        pass
    location = ", ".join(location_parts) if location_parts else "Unknown"
    # Determine team or department name.  If no explicit department is
    # provided, fall back to the hiring organisation or the job title.
    team = (
        job_data.get("department", {}).get("name")
        or job_data.get("hiringOrganization", {}).get("name")
        or job_data.get("title")
        or "Unknown"
    )
    # Job identifier may be provided in the JSON; it can be a dict or a string.
    identifier = job_data.get("identifier")
    job_id: str
    if isinstance(identifier, dict):
        job_id = identifier.get("value") or ""
    elif isinstance(identifier, str):
        job_id = identifier
    else:
        job_id = ""
    # Fall back to the slug in the URL if identifier is missing.
    if not job_id:
        job_id = url.rstrip("/").split("/")[-1]
    return BlackrockJob(
        job_id=job_id,
        title=title,
        url=url,
        date_posted=date_posted,
        team=team,
        location=location,
    )


async def get_jobs() -> List[BlackrockJob]:
    """Entry point for the scraper loader to obtain all current jobs.

    Returns:
        A list of :class:`BlackrockJob` objects representing current
        openings that meet the configured filters.
    """
    logger = get_company_logger()
    logger.info("Starting BlackRock job scrape…")
    jobs: List[BlackrockJob] = []
    # Random jitter before starting, imitating human browsing patterns
    await asyncio.sleep(asyncio.get_event_loop().time() % 3)
    async with aiohttp.ClientSession() as session:
        sitemap_text = await fetch_text(session, SITEMAP_URL)
        if not sitemap_text:
            logger.error("❌ Failed to download sitemap – returning empty job list")
            return jobs
        job_urls = parse_sitemap(sitemap_text)
        # print(job_urls[0])
        if not job_urls:
            logger.warning("⚠️ No job URLs found in sitemap")
            return jobs
        logger.info(f"Discovered {len(job_urls)} potential job URLs")
        sem = asyncio.Semaphore(CONCURRENCY_LIMIT)

        async def sem_fetch(u: str) -> Optional[BlackrockJob]:
            async with sem:
                return await fetch_job(session, u)

        tasks = [asyncio.create_task(sem_fetch(u)) for u in job_urls]
        for coro in asyncio.as_completed(tasks):
            job = await coro
            if job:
                jobs.append(job)
        logger.info(f"Scraped {len(jobs)} BlackRock jobs after filtering")
        return jobs