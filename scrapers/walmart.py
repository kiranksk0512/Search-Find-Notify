from __future__ import annotations

import asyncio
import json
import os
import random
import secrets
import time
import uuid
from dataclasses import dataclass
from http.cookies import SimpleCookie
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import aiohttp

from core.context import get_company
from core.decision import retry_and_decide
from core.logger import get_company_logger
from core.scrape_types import ScrapeResult
from models.walmart_job import WalmartJob

logger = get_company_logger()

WALMART_ENDPOINT = "https://careers.walmart.com/api/streaming/careers-ai/api/chat/sync?chatBasedSearchJob"
JOB_URL_BASE = "https://careers.walmart.com/us/en/jobs"

DEFAULT_PROMPT = (
    "Filter for Technology area roles across categories Software Engineering and Architecture, "
    "Creative, Design and UX, Data Science and Analytics, Information Security, Technical Program Management, "
    "Information Technology. Limit the population to WALMART_EXT_CAMPUS_US, WALMART_EXT_FIELD_US, "
    "SAMS_EXT_CAMPUS_US, SAMS_EXT_FIELD_US, VIZIO_CAMPUS_EXTERNAL, VIZIO_FIELD_EXTERNAL."
)

DEFAULT_POPULATIONS: Tuple[str, ...] = (
    "WALMART_EXT_CAMPUS_US",
    "WALMART_EXT_FIELD_US",
    "SAMS_EXT_CAMPUS_US",
    "SAMS_EXT_FIELD_US",
    "VIZIO_CAMPUS_EXTERNAL",
    "VIZIO_FIELD_EXTERNAL",
)

ALLOWED_AREAS_DEFAULT: Tuple[str, ...] = ("Technology",)
ALLOWED_CATEGORIES_DEFAULT: Tuple[str, ...] = (
    "Software Engineering and Architecture",
    "Creative, Design and UX",
    "Data Science and Analytics",
    "Information Security",
    "Technical Program Management",
    "Information Technology",
)

STUDENTS_PROMPT_DEFAULT = "filter using areas Students and categories Internship"
STUDENTS_AREAS_DEFAULT: Tuple[str, ...] = ("Students",)
STUDENTS_CATEGORIES_DEFAULT: Tuple[str, ...] = ("Internship",)

CORPORATE_PROMPT_DEFAULT = (
    "filter using areas Corporate and categories Research and Development, Creative, Design and UX, Engineering"
)
CORPORATE_AREAS_DEFAULT: Tuple[str, ...] = ("Corporate",)
CORPORATE_CATEGORIES_DEFAULT: Tuple[str, ...] = (
    "Research and Development",
    "Creative, Design and UX",
    "Engineering",
)


@dataclass(frozen=True)
class ScenarioConfig:
    name: str
    prompt: str
    populations: Tuple[str, ...]
    allowed_areas: Tuple[str, ...]
    allowed_categories: Tuple[str, ...]
    allowed_populations: Tuple[str, ...]
    min_expected: int

USER_AGENTS: Tuple[str, ...] = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
)

HEADER_TEMPLATE: Dict[str, str] = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/json",
    "Origin": "https://careers.walmart.com",
    "Referer": "https://careers.walmart.com/us/jobs",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

MIN_EXPECTED_COUNT = int(os.getenv("WALMART_MIN_EXPECTED", "20"))
MAX_PAGES = int(os.getenv("WALMART_MAX_PAGES", "120"))
PAGE_RETRY_ATTEMPTS = int(os.getenv("WALMART_PAGE_RETRIES", "3"))
EMPTY_PAGE_THRESHOLD = int(os.getenv("WALMART_EMPTY_PAGE_THRESHOLD", "5"))

CLIENT_TIMEOUT_TOTAL = float(os.getenv("WALMART_TIMEOUT_TOTAL", "90"))
CLIENT_TIMEOUT_CONNECT = float(os.getenv("WALMART_TIMEOUT_CONNECT", "15"))
CLIENT_TIMEOUT_READ = float(os.getenv("WALMART_TIMEOUT_READ", "30"))
CLIENT_TIMEOUT = aiohttp.ClientTimeout(
    total=CLIENT_TIMEOUT_TOTAL,
    connect=CLIENT_TIMEOUT_CONNECT,
    sock_read=CLIENT_TIMEOUT_READ,
)

CHANNEL = os.getenv("WALMART_CHANNEL", "job_search")
ACTIVE_TAB = os.getenv("WALMART_ACTIVE_TAB", "jobs")
CLIENT_TYPE = os.getenv("WALMART_CLIENT_TYPE", "external")  # Walmart endpoint rejects other defaults
LOCALE = os.getenv("WALMART_LOCALE", "en_US")  # API validation expects underscore locale codes
SORT_ORDER = os.getenv("WALMART_SORT", "relevance")
REFINED_QUERY = os.getenv("WALMART_REFINED_QUERY", "jobId == '*'")
USER_AGENT_OVERRIDE = os.getenv("WALMART_USER_AGENT")
JOB_PAGE_SIZE_ENV = os.getenv("WALMART_JOB_PAGE_SIZE")

GRAPHQL_QUERY = """
query GetJobSearchAssistant($chatRequest: JobChatRequest!) {
  jobSearchAssistant(chatRequest: $chatRequest) {
    thread_id
    timestamp
    tool_messages {
      name
      status
      content
      tool_call_id
      artifact {
        applied_facets
        totalResults
        total_jobs
        page_size
        page_number
        job_page_number
        status
        jobs {
          job_id
          jobPostingTitle
          title
          city
          state
          country
          latitude
          longitude
          categories
          areas
          brand
          employmentTypes
          population
          storeNumber
          bannerName
          postalCode
          shifts
          shiftTime
          additionalLocationCities
          skills
          minPay
          maxPay
          payFrequency
          payRange {
            location
            code
            min
            max
          }
        }
        searchResults {
          jobId
          jobPostingTitle
          title
          categories
          areas
          brand
          employmentTypes
          population
          skills
          primaryLocationCity
          primaryLocationState
          primaryLocationCountry
        }
      }
    }
    ai_message {
      content
      role
    }
  }
}
"""


def _pair_from_env(min_key: str, max_key: str, default: Tuple[float, float]) -> Tuple[float, float]:
    try:
        min_val = float(os.getenv(min_key, str(default[0])))
        max_val = float(os.getenv(max_key, str(default[1])))
    except ValueError:
        return default
    if max_val < min_val:
        return max_val, min_val
    return min_val, max_val


REQUEST_DELAY_RANGE = _pair_from_env("WALMART_PAGE_DELAY_MIN", "WALMART_PAGE_DELAY_MAX", (0.6, 1.6))
RETRY_DELAY_RANGE = _pair_from_env("WALMART_RETRY_DELAY_MIN", "WALMART_RETRY_DELAY_MAX", (1.0, 2.5))


def _safe_list(value: Any) -> Tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(v).strip() for v in value if isinstance(v, str) and v.strip())
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    return ()


def _normalize_tokens(tokens: Iterable[str]) -> Set[str]:
    return {token.strip().lower() for token in tokens if token and token.strip()}


def _compose_location(city: Optional[str], state: Optional[str], country: Optional[str]) -> str:
    parts = [p for p in (city, state, country) if p]
    return ", ".join(parts) if parts else "Unknown"


def _parse_cookie_header(raw_cookie: str) -> Dict[str, str]:
    if not raw_cookie:
        return {}
    simple_cookie = SimpleCookie()
    try:
        simple_cookie.load(raw_cookie)
    except Exception:
        return {}
    return {key: morsel.value for key, morsel in simple_cookie.items() if morsel.value}


def _thread_seed() -> str:
    return f"{int(time.time() * 1000)}-{uuid.uuid4()}"


def _job_url(job_id: str) -> str:
    return f"{JOB_URL_BASE}/{job_id}"


def _build_headers(user_agent: str) -> Dict[str, str]:
    headers = dict(HEADER_TEMPLATE)
    headers["User-Agent"] = user_agent
    headers["x-client-name"] = "careers_ai"
    headers["x-application-group"] = "careers_ai"
    return headers


def _load_sequence(env_key: str, default: Sequence[str]) -> Tuple[str, ...]:
    raw = os.getenv(env_key, "")
    if not raw.strip():
        return tuple(default)
    tokens = [token.strip() for token in raw.replace("|", ",").split(",")]
    return tuple(token for token in tokens if token)


def _build_technology_config(default_min: int) -> ScenarioConfig:
    populations = _load_sequence("WALMART_POPULATIONS", DEFAULT_POPULATIONS)
    allowed_areas = _load_sequence("WALMART_ALLOWED_AREAS", ALLOWED_AREAS_DEFAULT)
    allowed_categories = _load_sequence("WALMART_ALLOWED_CATEGORIES", ALLOWED_CATEGORIES_DEFAULT)
    allowed_populations = _load_sequence("WALMART_ALLOWED_POPULATIONS", populations)
    prompt = os.getenv("WALMART_PROMPT", DEFAULT_PROMPT).strip() or DEFAULT_PROMPT
    min_expected = int(os.getenv("WALMART_MIN_EXPECTED", str(default_min)))
    return ScenarioConfig(
        name="technology",
        prompt=prompt,
        populations=populations,
        allowed_areas=allowed_areas,
        allowed_categories=allowed_categories,
        allowed_populations=allowed_populations,
        min_expected=min_expected,
    )


def _build_students_config(default_min: int) -> ScenarioConfig:
    populations = _load_sequence("WALMART_STUDENTS_POPULATIONS", DEFAULT_POPULATIONS)
    allowed_areas = _load_sequence("WALMART_STUDENTS_ALLOWED_AREAS", STUDENTS_AREAS_DEFAULT)
    allowed_categories = _load_sequence(
        "WALMART_STUDENTS_ALLOWED_CATEGORIES", STUDENTS_CATEGORIES_DEFAULT
    )
    allowed_populations = _load_sequence(
        "WALMART_STUDENTS_ALLOWED_POPULATIONS", populations
    )
    prompt = os.getenv("WALMART_STUDENTS_PROMPT", STUDENTS_PROMPT_DEFAULT).strip() or STUDENTS_PROMPT_DEFAULT
    min_expected = int(os.getenv("WALMART_STUDENTS_MIN_EXPECTED", "1"))
    return ScenarioConfig(
        name="students_internship",
        prompt=prompt,
        populations=populations,
        allowed_areas=allowed_areas,
        allowed_categories=allowed_categories,
        allowed_populations=allowed_populations,
        min_expected=min_expected if min_expected > 0 else default_min,
    )


def _build_corporate_config(default_min: int) -> ScenarioConfig:
    populations = _load_sequence("WALMART_CORPORATE_POPULATIONS", DEFAULT_POPULATIONS)
    allowed_areas = _load_sequence("WALMART_CORPORATE_ALLOWED_AREAS", CORPORATE_AREAS_DEFAULT)
    allowed_categories = _load_sequence(
        "WALMART_CORPORATE_ALLOWED_CATEGORIES", CORPORATE_CATEGORIES_DEFAULT
    )
    allowed_populations = _load_sequence(
        "WALMART_CORPORATE_ALLOWED_POPULATIONS", populations
    )
    prompt = os.getenv("WALMART_CORPORATE_PROMPT", CORPORATE_PROMPT_DEFAULT).strip() or CORPORATE_PROMPT_DEFAULT
    min_expected = int(os.getenv("WALMART_CORPORATE_MIN_EXPECTED", "1"))
    return ScenarioConfig(
        name="corporate_research",
        prompt=prompt,
        populations=populations,
        allowed_areas=allowed_areas,
        allowed_categories=allowed_categories,
        allowed_populations=allowed_populations,
        min_expected=min_expected if min_expected > 0 else default_min,
    )


def _scenario_from_name(name: str, default_min: int) -> Optional[ScenarioConfig]:
    key = name.lower()
    if key in {"technology", "tech", "default"}:
        return _build_technology_config(default_min)
    if key in {"students", "students_internship", "students-internship", "internship"}:
        return _build_students_config(default_min)
    if key in {"corporate", "corporate_research", "corporate-rnd", "corporate_design"}:
        return _build_corporate_config(default_min)
    return None


def _load_scenarios(default_min: int) -> List[ScenarioConfig]:
    raw = os.getenv(
        "WALMART_SCENARIOS",
        "technology,corporate_research,students_internship",
    )
    if raw.strip():
        scenarios: List[ScenarioConfig] = []
        for token in raw.split(","):
            name = token.strip()
            if not name:
                continue
            config = _scenario_from_name(name, default_min)
            if config is None:
                logger.warning(
                    "[walmart] Unknown WALMART_SCENARIOS entry '%s'; skipping.", name
                )
                continue
            scenarios.append(config)
        if scenarios:
            return scenarios

    # Fallback to the technology/default scenario.
    return [_build_technology_config(default_min)]


def _optional_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _build_payload(
    *,
    thread_id: str,
    prompt: str,
    page: int,
    include_prompt: bool,
    populations: Sequence[str],
    job_page_size: Optional[int],
) -> Dict[str, Any]:
    messages: List[Dict[str, Any]] = []
    if include_prompt and prompt:
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt,
                    }
                ],
            }
        )

    job_context: Dict[str, Any] = {
        "refined_query": REFINED_QUERY,
        "locale": LOCALE,
        "sort": SORT_ORDER,
        "active_tab": ACTIVE_TAB,
        "client_type": CLIENT_TYPE,
        "management_levels": [],
        "content_page": 0,
        "future_roles_page": 0,
        "job_page": page,
        "population": list(populations),
    }

    if job_page_size is not None and job_page_size > 0:
        job_context["job_page_size"] = job_page_size

    chat_request = {
        "messages": messages,
        "thread_id": thread_id or _thread_seed(),
        "channel": CHANNEL,
        "context": {
            "job_search_context": job_context,
        },
    }

    return {
        "query": GRAPHQL_QUERY,
        "variables": {"chatRequest": chat_request},
    }


async def _post_payload(
    session: aiohttp.ClientSession,
    payload: Dict[str, Any],
    *,
    scrape_id: str,
    page: int,
) -> Optional[Dict[str, Any]]:
    company = get_company()
    try:
        async with session.post(WALMART_ENDPOINT, json=payload) as resp:
            text = await resp.text()
            if resp.status != 200:
                logger.error(
                    f"[company={company}] [{scrape_id}] ❌ Walmart page {page} status={resp.status}"
                )
                logger.debug(
                    f"[company={company}] [{scrape_id}] Walmart response snippet: {text[:500]}"
                )
                return None
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                logger.error(
                    f"[company={company}] [{scrape_id}] ❌ Walmart JSON decode failure on page {page}"
                )
                logger.debug(
                    f"[company={company}] [{scrape_id}] Raw text: {text[:600]}"
                )
                return None
    except Exception as exc:
        logger.error(
            f"[company={company}] [{scrape_id}] ❌ Walmart exception on page {page}: {exc}"
        )
        return None


def _merge_search_result(job_entry: Dict[str, Any], card: Dict[str, Any]) -> None:
    mapping = {
        "jobId": "job_id",
        "jobPostingTitle": "jobPostingTitle",
        "title": "title",
        "primaryLocationCity": "city",
        "primaryLocationState": "state",
        "primaryLocationCountry": "country",
        "city": "city",
        "state": "state",
        "country": "country",
        "areas": "areas",
        "categories": "categories",
        "brand": "brand",
        "employmentTypes": "employmentTypes",
        "population": "population",
        "additionalLocationCities": "additionalLocationCities",
        "skills": "skills",
    }

    for src, dest in mapping.items():
        value = card.get(src)
        if value in (None, ""):
            continue
        if dest not in job_entry or not job_entry.get(dest):
            job_entry[dest] = value


def _coerce_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_jobs(
    payload: Dict[str, Any],
    *,
    scrape_id: str,
    page: int,
) -> Tuple[Dict[str, Dict[str, Any]], Optional[int], Optional[int], Optional[str], bool]:
    company = get_company()
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        logger.error(f"[company={company}] [{scrape_id}] ❌ Walmart response missing data on page {page}")
        return {}, None, None, None, False

    assistant = data.get("jobSearchAssistant")
    if not isinstance(assistant, dict):
        logger.error(f"[company={company}] [{scrape_id}] ❌ jobSearchAssistant missing on page {page}")
        try:
            logger.error(
                f"[company={company}] [{scrape_id}] Walmart raw payload snippet: {json.dumps(payload)[:600]}"
            )
        except Exception:
            logger.error(
                f"[company={company}] [{scrape_id}] Walmart payload (unserializable) type={type(payload)}"
            )
        return {}, None, None, None, False

    thread_id = assistant.get("thread_id")
    tool_messages = assistant.get("tool_messages") or []
    artifact = None
    for message in tool_messages:
        if isinstance(message, dict):
            artifact = message.get("artifact")
        if artifact:
            break

    if not isinstance(artifact, dict):
        logger.warning(
            f"[company={company}] [{scrape_id}] ⚠️ Walmart artifact missing on page {page}"
        )
        return {}, None, None, thread_id, False

    jobs_by_id: Dict[str, Dict[str, Any]] = {}
    raw_jobs = artifact.get("jobs") or []
    if isinstance(raw_jobs, list):
        for job in raw_jobs:
            if not isinstance(job, dict):
                continue
            job_id = str(job.get("job_id") or job.get("jobId") or "").strip()
            if not job_id:
                continue
            jobs_by_id[job_id] = dict(job)

    search_results = artifact.get("searchResults") or []
    if isinstance(search_results, list):
        for card in search_results:
            if not isinstance(card, dict):
                continue
            job_id = str(card.get("jobId") or card.get("job_id") or "").strip()
            if not job_id:
                continue
            job_entry = jobs_by_id.setdefault(job_id, {})
            _merge_search_result(job_entry, card)

    page_size = _coerce_int(artifact.get("page_size"))
    total_jobs = _coerce_int(artifact.get("total_jobs") or artifact.get("totalResults"))

    return jobs_by_id, page_size, total_jobs, thread_id, True


def _to_job(job_id: str, raw: Dict[str, Any]) -> WalmartJob:
    title = raw.get("title") or raw.get("jobPostingTitle") or "Unknown"
    location = _compose_location(raw.get("city"), raw.get("state"), raw.get("country"))
    return WalmartJob(
        job_id=job_id,
        title=str(title),
        url=_job_url(job_id),
        location=location,
        job_posting_title=str(raw.get("jobPostingTitle") or title),
        brand=str(raw.get("brand") or "Unknown"),
        areas=_safe_list(raw.get("areas")),
        categories=_safe_list(raw.get("categories")),
        employment_types=_safe_list(raw.get("employmentTypes")),
        population=str(raw.get("population")) if raw.get("population") is not None else None,
        additional_locations=_safe_list(raw.get("additionalLocationCities")),
        skills=_safe_list(raw.get("skills")),
    )


def _job_passes_filters(
    job: WalmartJob,
    *,
    allowed_area_tokens: Set[str],
    allowed_category_tokens: Set[str],
    allowed_populations: Set[str],
) -> bool:
    job_area_tokens = _normalize_tokens(job.areas)
    job_category_tokens = _normalize_tokens(job.categories)

    if allowed_area_tokens and not (job_area_tokens & allowed_area_tokens):
        return False

    if allowed_category_tokens and not (job_category_tokens & allowed_category_tokens):
        return False

    if allowed_populations:
        if job.population and job.population in allowed_populations:
            return True
        if job.population is None:
            return False
        return False

    return True


def should_persist_jobs(result: ScrapeResult, min_expected_count: int) -> Tuple[bool, str]:
    company = get_company()
    if result is None:
        return False, "no_result"

    if result.anomalous_zero:
        logger.warning(f"[company={company}] [{result.scrape_id}] anomalous_zero=True")
        return False, "anomalous_zero"

    total = len(result.jobs or [])
    if total == 0:
        return False, "zero_jobs"

    reported = result.stats.get("total_reported") if isinstance(result.stats, dict) else None
    if isinstance(reported, int) and reported > 0 and total < max(min_expected_count, int(reported * 0.5)):
        return False, f"too_few_vs_reported({total}<{reported})"

    if total < min_expected_count:
        return False, f"too_few({total}<{min_expected_count})"

    return True, "ok"


def _summarize_stats(stats: Dict[str, Any]) -> Dict[str, Any]:
    summary = dict(stats)
    summary["request_delay_range"] = REQUEST_DELAY_RANGE
    summary["retry_delay_range"] = RETRY_DELAY_RANGE
    return summary


async def _scrape_once(label: str, scenario: ScenarioConfig) -> ScrapeResult:
    company = get_company()
    scrape_id = secrets.token_hex(4)
    prompt_text = scenario.prompt
    populations = scenario.populations
    allowed_areas = scenario.allowed_areas
    allowed_categories = scenario.allowed_categories
    allowed_populations = scenario.allowed_populations

    allowed_area_tokens = _normalize_tokens(allowed_areas)
    allowed_category_tokens = _normalize_tokens(allowed_categories)
    allowed_population_set = {token for token in allowed_populations if token}

    job_page_size = _optional_int(JOB_PAGE_SIZE_ENV)
    cookie_header = os.getenv("WALMART_COOKIE", "")
    # cookie_header = "cx_website_access_new_v4=true; isExternal=true; AMCVS_B5281C8B53309CEF0A490D4D%40AdobeOrg=1; AMCV_B5281C8B53309CEF0A490D4D%40AdobeOrg=179643557%7CMCIDTS%7C20421%7CMCMID%7C58828219389498218662330012543307110542%7CMCAAMLH-1764958871%7C7%7CMCAAMB-1764958871%7CRKhpRz8krg2tLO6pguXWp5olkAcUniQYPHaMWWgdJ3xzPWQmdj0y%7CMCCIDH%7C-976838382%7CMCOPTOUT-1764361271s%7CNONE%7CvVersion%7C5.5.0; s_cc=true; wmcx_sessionmeta=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjYW5kaWRhdGVJZCI6IjVhNTBjMDlhLWYxNmUtNDhhZC04NTYxLTUzZWRiYjNmNWU3YSIsImlhdCI6MTc2NDM1NDA3MX0.eY2p6IHN4PBbSPQsAY1P6rv_Si4fvMbdCdCy7sfllDg; TS01265438=01d6701180098c64f053e23a6373030661bfbcccbd4b28fa89fce8380a95ca16b201bdc7c88496f028aa53ba58abdae9854ae502d0; TS01d71d9a=01d6701180098c64f053e23a6373030661bfbcccbd4b28fa89fce8380a95ca16b201bdc7c88496f028aa53ba58abdae9854ae502d0; TS7bfbe36e027=08e8211e93ab20000b5c08f48c6ecc7f71c5aa134b0c344093a30e8deebe35b648b0f86d4cd606d0088f36824b113000bd5efc4534afea3556fad042d52feab5c8742933626f663adc6556ad56fa619d02ccef70467712690a6b18682c9239cb"
    cookies = _parse_cookie_header(cookie_header)

    user_agent = USER_AGENT_OVERRIDE or random.choice(USER_AGENTS)
    headers = _build_headers(user_agent)

    logger.info(
        f"[company={company}] [{scrape_id}] 🚀 Walmart scrape ({scenario.name}:{label}) areas={sorted(allowed_areas)} categories={sorted(allowed_categories)}"
    )

    deduped: Dict[str, WalmartJob] = {}
    duplicates_skipped = 0
    filtered_out = 0
    artifact_failures = 0
    pages_attempted = 0
    pages_with_artifact = 0
    total_retries = 0
    thread_resets = 0
    empty_streak = 0
    zero_jobs_streak = 0
    total_reported: Optional[int] = None
    last_page_size: Optional[int] = None

    timeout = CLIENT_TIMEOUT
    connector = aiohttp.TCPConnector(limit_per_host=int(os.getenv("WALMART_CONNECTION_LIMIT", "8")))

    async with aiohttp.ClientSession(headers=headers, cookies=cookies, timeout=timeout, connector=connector) as session:
        thread_id: Optional[str] = None
        for page in range(MAX_PAGES):
            pages_attempted = page + 1
            payload = _build_payload(
                thread_id=thread_id or _thread_seed(),
                prompt=prompt_text,
                page=page,
                include_prompt=True,
                populations=populations,
                job_page_size=job_page_size,
            )

            page_jobs: List[WalmartJob] = []
            had_artifact = False
            response_thread: Optional[str] = None
            page_size: Optional[int] = None
            total_jobs: Optional[int] = None
            raw_job_count = 0
            page_filtered = 0
            page_duplicates = 0
            page_parse_errors = 0

            for attempt in range(1, PAGE_RETRY_ATTEMPTS + 1):
                response_json = await _post_payload(session, payload, scrape_id=scrape_id, page=page)
                if attempt > 1:
                    total_retries += 1
                if response_json is None:
                    artifact_failures += 1
                    thread_id = None
                    await asyncio.sleep(random.uniform(*RETRY_DELAY_RANGE))
                    continue

                jobs_map, page_size, total_jobs, response_thread, had_artifact = _parse_jobs(
                    response_json,
                    scrape_id=scrape_id,
                    page=page,
                )

                if had_artifact:
                    pages_with_artifact += 1
                if response_thread and response_thread != thread_id:
                    thread_id = response_thread
                elif not response_thread and not had_artifact:
                    thread_id = None
                    thread_resets += 1

                if not had_artifact:
                    artifact_failures += 1
                    await asyncio.sleep(random.uniform(*RETRY_DELAY_RANGE))
                    continue

                raw_job_count = len(jobs_map)
                logger.debug(
                    f"[company={company}] [{scrape_id}] Walmart [{scenario.name}] page {page} attempt {attempt} returned {raw_job_count} raw jobs"
                )
                for job_id, raw in jobs_map.items():
                    try:
                        job = _to_job(job_id, raw)
                    except Exception as err:
                        logger.error(
                            f"[company={company}] [{scrape_id}] ❌ Walmart job parse error job_id={job_id}: {err}"
                        )
                        page_parse_errors += 1
                        continue

                    if not _job_passes_filters(
                        job,
                        allowed_area_tokens=allowed_area_tokens,
                        allowed_category_tokens=allowed_category_tokens,
                        allowed_populations=allowed_population_set,
                    ):
                        filtered_out += 1
                        page_filtered += 1
                        continue

                    if job.job_id in deduped:
                        duplicates_skipped += 1
                        page_duplicates += 1
                        continue

                    deduped[job.job_id] = job
                    page_jobs.append(job)

                break

            if total_jobs is not None:
                total_reported = total_jobs
            if page_size is not None:
                last_page_size = page_size

            if not had_artifact:
                empty_streak += 1
                if empty_streak >= EMPTY_PAGE_THRESHOLD:
                    logger.warning(
                        f"[company={company}] [{scrape_id}] 🛑 Stopping Walmart scrape after {empty_streak} empty artifacts"
                    )
                    break
                await asyncio.sleep(random.uniform(*RETRY_DELAY_RANGE))
                continue

            empty_streak = 0

            if raw_job_count == 0:
                zero_jobs_streak += 1
                if zero_jobs_streak >= EMPTY_PAGE_THRESHOLD:
                    logger.warning(
                        f"[company={company}] [{scrape_id}] 🛑 Stopping Walmart scrape after {zero_jobs_streak} empty result pages"
                    )
                    break
            else:
                zero_jobs_streak = 0

            if not page_jobs:
                logger.debug(
                    f"[company={company}] [{scrape_id}] ℹ️ Walmart [{scenario.name}] page {page} produced no filtered jobs (raw={raw_job_count}, filtered={page_filtered}, duplicates={page_duplicates}, parse_errors={page_parse_errors})"
                )
                await asyncio.sleep(random.uniform(*REQUEST_DELAY_RANGE))
                continue

            logger.info(
                f"[company={company}] [{scrape_id}] 📦 Walmart [{scenario.name}] page {page}: {len(page_jobs)} jobs (unique={len(deduped)}, raw={raw_job_count}, filtered={page_filtered}, duplicates={page_duplicates}, parse_errors={page_parse_errors})"
            )

            if total_reported and len(deduped) >= total_reported:
                logger.debug(
                    f"[company={company}] [{scrape_id}] ℹ️ Walmart [{scenario.name}] reported total={total_reported} reached; continuing per config."
                )

            if page_size is not None and raw_job_count < page_size:
                logger.debug(
                    f"[company={company}] [{scrape_id}] ℹ️ Walmart [{scenario.name}] API returned {raw_job_count} < page_size {page_size}; continuing per config."
                )

            await asyncio.sleep(random.uniform(*REQUEST_DELAY_RANGE))

    final_jobs = list(deduped.values())
    anomalous_zero = len(final_jobs) == 0

    stats: Dict[str, Any] = {
        "unique_jobs": len(final_jobs),
        "duplicates_skipped": duplicates_skipped,
        "filtered_out": filtered_out,
        "artifact_failures": artifact_failures,
        "pages_attempted": pages_attempted,
        "pages_with_artifact": pages_with_artifact,
        "total_retries": total_retries,
        "thread_resets": thread_resets,
        "last_page_size": last_page_size,
        "total_reported": total_reported,
        "user_agent": user_agent,
        "scenario": scenario.name,
    }

    meta = {
        "prompt": prompt_text,
        "populations": list(populations),
        "allowed_areas": list(allowed_areas),
        "allowed_categories": list(allowed_categories),
        "allowed_populations": list(allowed_populations),
        "label": label,
        "scenario": scenario.name,
    }

    logger.info(
        f"[company={company}] [{scrape_id}] 🎉 Walmart [{scenario.name}] total={len(final_jobs)} anomalous_zero={anomalous_zero}"
    )

    return ScrapeResult(
        jobs=final_jobs,
        scrape_id=scrape_id,
        anomalous_zero=anomalous_zero,
        stats=_summarize_stats(stats),
        meta=meta,
    )


async def get_jobs(min_expected_count: int = MIN_EXPECTED_COUNT) -> ScrapeResult:
    company = get_company()
    scenarios = _load_scenarios(min_expected_count)

    combined_jobs: Dict[str, WalmartJob] = {}
    scenario_stats: List[Dict[str, Any]] = []
    scenario_meta: List[Dict[str, Any]] = []
    persisted_scenarios = 0

    multi_scrape_id = f"multi-{secrets.token_hex(4)}"

    for scenario in scenarios:

        async def _run(label: str) -> ScrapeResult:
            await asyncio.sleep(random.uniform(0.2, 0.8))
            return await _scrape_once(label, scenario)

        first = await _run(f"{scenario.name}-first-pass")

        decided = await retry_and_decide(
            company=company,
            logger=logger,
            first_result=first,
            retry_fn=lambda: _run(f"{scenario.name}-retry"),
            min_expected_count=scenario.min_expected,
            should_persist_fn=should_persist_jobs,
        )

        scenario_stats.append(
            {
                "name": scenario.name,
                "scrape_id": decided.scrape_id,
                "should_persist": decided.should_persist,
                "decision_reason": decided.decision_reason,
                "jobs_returned": len(decided.jobs or []),
                "min_expected": scenario.min_expected,
                "stats": decided.stats,
            }
        )
        scenario_meta_entry = dict(decided.meta)
        scenario_meta_entry.update(
            {
                "scrape_id": decided.scrape_id,
                "should_persist": decided.should_persist,
                "decision_reason": decided.decision_reason,
            }
        )
        scenario_meta.append(scenario_meta_entry)

        if decided.should_persist:
            persisted_scenarios += 1
            for job in decided.jobs or []:
                combined_jobs[job.job_id] = job

    final_jobs = list(combined_jobs.values())
    should_persist = persisted_scenarios > 0 and bool(final_jobs)
    decision_reason = "ok" if should_persist else "no_scenario_met_threshold"

    anomalous_zero = len(final_jobs) == 0

    stats: Dict[str, Any] = {
        "unique_jobs": len(final_jobs),
        "total_scenarios": len(scenarios),
        "persisted_scenarios": persisted_scenarios,
        "scenario_stats": scenario_stats,
    }

    meta = {
        "scenario_names": [scenario.name for scenario in scenarios],
        "scenario_meta": scenario_meta,
    }

    return ScrapeResult(
        jobs=final_jobs,
        scrape_id=multi_scrape_id,
        anomalous_zero=anomalous_zero,
        should_persist=should_persist,
        decision_reason=decision_reason,
        stats=_summarize_stats(stats),
        meta=meta,
    )
