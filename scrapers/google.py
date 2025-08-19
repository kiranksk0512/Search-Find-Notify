import random
import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import html
from models.google_job import GoogleJob
from core.logger import get_company_logger
from core.fetcher import post_form
from core.google_utils import extract_google_tokens_and_cookies

logger = get_company_logger()

GOOGLE_URL = "https://www.google.com/about/careers/applications/_/HiringCportalFrontendUi/data/batchexecute"
SOURCE_PATH = "/about/careers/applications/jobs/results/"

SEARCH_TITLES = ["Software Engineer", "ai-spotlight"]

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)... Chrome/138.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)... Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64)... Chrome/138.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3)... Version/16.4 Safari/605.1.15"
]

ACCEPT_LANGUAGES = [
    "en-GB,en-US;q=0.9,en;q=0.8",
    "en-US,en;q=0.9",
    "en;q=0.9"
]

def build_form_payload(page: int, rpcid: str, query_term: str, at_token: str = None):
    device_value = [1] if page == 1 else None

    job_query = [
        [f"\"{query_term}\"", None, None, device_value, "en", None, [["United States"]], page]
    ]

    f_req = [
        [[rpcid, json.dumps(job_query), None, "3"]]
    ]

    payload = {
        "f.req": json.dumps(f_req)  # Wrap the entire payload as a JSON string
    }

    # if at_token:
    #     payload["at"] = at_token

    return payload

async def get_jobs():
    logger.info("Starting Google job scrape...")

    # 🔄 Get dynamic tokens and cookies
    tokens = await extract_google_tokens_and_cookies()
    rpcids = tokens.get("rpcids")
    f_sid = tokens.get("f.sid")
    bl = tokens.get("bl")
    at_token = tokens.get("at")
    cookies_dict = tokens.get("cookies")

    if not (rpcids and f_sid and bl):
        logger.error("❌ Missing required Google tokens. Aborting scrape.")
        return []

    # Reconstruct cookie header
    raw_cookie_header = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())

    # Build base query params
    QUERY_PARAMS = {
        "rpcids": rpcids,
        "source-path": SOURCE_PATH,
        "f.sid": f_sid,
        "bl": bl,
        "hl": "en",
        "soc-app": "1",
        "soc-platform": "1",
        "soc-device": "1",
        "rt": "c",
    }
    query_string = "&".join(f"{k}={v}" for k, v in QUERY_PARAMS.items())
    url = f"{GOOGLE_URL}?{query_string}"

    all_jobs = []

    # Add random jitter before starting to look human
    await asyncio.sleep(random.uniform(0, 20))

    for query in SEARCH_TITLES:
        logger.info(f"🔍 Searching for jobs with query: {query}")
        page = 1
        consecutive_empty_pages = 0

        while True:
            # Randomize headers each page
            HEADERS = {
                "accept": "*/*",
                "accept-encoding": "gzip, deflate, br, zstd",
                "accept-language": random.choice(ACCEPT_LANGUAGES),
                "cache-control": "no-cache",
                "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
                "origin": "https://www.google.com",
                "pragma": "no-cache",
                "referer": "https://www.google.com/about/careers/applications/jobs/results/",
                "user-agent": random.choice(USER_AGENTS),
            }

            payload = build_form_payload(page, rpcids, query, at_token)
            response_text = await post_form(
                url=url,
                payload=payload,
                headers=HEADERS,
                parse_json=False,
                cookies=raw_cookie_header
            )

            if response_text is None:
                logger.error(f"❌ Failed to get response for '{query}' page {page}")
                break

            try:
                cleaned_response = response_text.lstrip(")]}'\n")
                job_string = None

                for line in cleaned_response.splitlines():
                    try:
                        parsed = json.loads(line)
                        for entry in parsed:
                            if isinstance(entry, list) and entry[0] == "wrb.fr" and entry[1] == "r06xKb":
                                job_string = entry[2]
                                break
                    except Exception:
                        continue

                if not job_string:
                    logger.warning(f"⚠️ No job String found for '{query}' on page {page}")
                    consecutive_empty_pages += 1
                    if consecutive_empty_pages >= 3:
                        logger.warning(f"⚠️ Stopping '{query}': 3 empty pages.")
                        break
                    page += 1
                    continue

                job_entries = json.loads(job_string)[0]
                if not job_entries:
                    logger.warning(f"⚠️ No job entries for '{query}' on page {page}")
                    consecutive_empty_pages += 1
                    if consecutive_empty_pages >= 3:
                        logger.warning(f"⚠️ Stopping '{query}': 3 empty pages.")
                        break
                    page += 1
                    continue

                consecutive_empty_pages = 0

                for job in job_entries:
                    job_id = job[0]
                    job_title = html.unescape(job[1])
                    job_url = f"https://www.google.com/about/careers/applications/jobs/results/{job_id}"
                    date_posted = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")

                    all_jobs.append(GoogleJob(
                        job_id=job_id,
                        title=job_title,
                        url=job_url,
                        date_posted=date_posted
                    ))

                logger.info(f"✅ '{query}' Page {page}: Parsed {len(job_entries)} jobs.")
                page += 1

                # Add random delay between pages
                await asyncio.sleep(random.uniform(1, 5))

            except Exception as e:
                logger.exception(f"❌ Error parsing jobs for '{query}' page {page}: {e}")
                break

    logger.info(f"🎉 Total Google jobs found: {len(all_jobs)}")
    return all_jobs