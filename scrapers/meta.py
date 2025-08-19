import json
from core.fetcher import post_form 
from core.logger import get_company_logger
from core.meta_utils import extract_meta_tokens
from models.meta_job import MetaJob
from datetime import datetime
from zoneinfo import ZoneInfo
import time
import random
import os
import asyncio


logger = get_company_logger()
GRAPHQL_URL = "https://www.metacareers.com/graphql"
DOC_ID = "29615178951461218"  # Persisted Meta job search doc ID
FRIENDLY_NAME = "CareersJobSearchResultsDataQuery"


# 'x-fb-lsd': Anti-CSRF token. Must be fetched dynamically or hardcoded per session.
# 'user-agent', 'sec-ch-ua', 'x-asbd-id': Might need updating every few months or per user.
# 'referer': Only if Meta changes frontend URLs.



COOKIES = {
    'datr': 'BNaDaLVxvClP3ifeL2rvnxJH',
    'wd': '514x832'
}

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

# 'cookies': Optional for now, but might be required in future.
# Right now you're not using them, and it's still working — but:

# The datr cookie is usually a browser fingerprint.

# The wd cookie is screen width-height. It’s usually not validated strictly.

# ✅ You can omit these for now. If Meta tightens validation, you might need to pass these.

def convert_to_edt(utc_timestamp):
    try:
        dt_utc = datetime.fromisoformat(utc_timestamp.replace("Z", "+00:00"))
        dt_edt = dt_utc.astimezone(ZoneInfo("America/New_York"))
        return dt_edt.strftime("%b %d, %Y %I:%M %p %Z")
    except Exception:
        return "Unknown"

import urllib.parse

def get_payload(tokens, *, sort_by_new=False, after_cursor=None, req_id="1"):
    variables = {
        "search_input": {
            "q": None,
            "divisions": [],
            "offices": [],
            "roles": [],
            "leadership_levels": [],
            "saved_jobs": [],
            "saved_searches": [],
            "sub_teams": [],
            "teams": [],
            "is_leadership": False,
            "is_remote_only": False,
            "sort_by_new": bool(sort_by_new),
            "results_per_page": None
        }
    }
    if after_cursor:
        variables["search_input"]["after_cursor"] = after_cursor

    payload_dict = {
        'av': '0',    
        '__user': '0',   # Static unless logged-in
        '__a': '1',
        '__req': req_id,   # ✅ Could change (request ID, used for batching)
        '__hs': tokens["__hs"], # ✅ Could change (server session, probably not critical)
        'dpr': '2',    # Device pixel ratio — static
        '__ccg': 'EXCELLENT',  # Static
        '__rev': tokens["__rev"], # ✅ Meta internal rev/version — **may change weekly**
        # '__s': 'u59kyl:8ogo8v:exjvo1', # ✅ Session fingerprint — **can change per session**
        '__hsi': tokens["__hsi"], # ✅ Internal session ID — **can change**
        '__dyn': '7xeUmwkHg7ebwKBAg5S1Dxu13wqovzEdEc8uxa1twYwJw5ux60Vo1upE4W0OE3nwaq1xwEw7Bx61vw4iwBgao1O82Iwb66oG0OU5a1qw8W1uwa-0raazoiwfe0Lo6-1FwcO0JE24wio1587u1rxC1RwkE', # ✅ Dynamic JS bundle encoding — often changes
        # '__hsdp': '...', # ✅ Possibly dynamic — can omit unless required
        'lsd': tokens["lsd"], # ✅ Same as header — CSRF token — **must match header**
        'jazoest': tokens["jazoest"],    # ✅ Internal integrity check — **depends on lsd and session**
        '__spin_r': tokens["__spin_r"], # ✅ Internal versioning — often changes
        '__spin_b': tokens["__spin_b"],  # Static
        '__spin_t': str(int(time.time())), # ✅ Timestamp — should reflect current UNIX time
        '__jssesw': '1', # Probably static
        'fb_api_caller_class': 'RelayModern',  # Static
        'fb_api_req_friendly_name': FRIENDLY_NAME, # Static
        'doc_id': DOC_ID,   # Static unless query changes
        'variables': json.dumps(variables),
        'server_timestamps': 'true', # Static
    }

    return urllib.parse.urlencode(payload_dict)


def parse_jobs(data):

    try:
        with open("meta_raw_data.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Failed to save raw Meta data: {e}")

    jobs = []
    all_jobs = data.get("data", {}).get("job_search_with_featured_jobs", {}).get("all_jobs", [])

    for job in all_jobs:
        job_id = job.get("id")
        title = job.get("title", "Unknown")
        url = f"https://www.metacareers.com/jobs/{job_id}"
        location = ", ".join(job.get("locations", [])) if "locations" in job else "Unknown"
        sub_teams = ", ".join(job.get("sub_teams", [])) if "sub_teams" in job else "Unknown"
        teams = ", ".join(job.get("teams", [])) if "teams" in job else "Unknown"
        posted = convert_to_edt(job.get("listed_on", ""))

        jobs.append(MetaJob(
            job_id=job_id,
            title=title,
            url=url,
            location=location,
            team=teams,
            sub_teams=sub_teams,
            date_posted=posted
        ))

    return jobs

async def fetch_all_pages_for_mode(tokens, *, sort_by_new: bool):
    logger.info(f"▶️ Meta scrape mode sort_by_new={sort_by_new}")
    collected = []
    seen_ids = set()
    after_cursor = None
    page = 1

    while True:
        req_id = str(page)
        HEADERS = {
            'accept': '*/*',
            'accept-language': random.choice(ACCEPT_LANGUAGES),
            'cache-control': 'no-cache',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://www.metacareers.com',
            'pragma': 'no-cache',
            'referer': 'https://www.metacareers.com/jobs',
            'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': random.choice(USER_AGENTS),
            'x-asbd-id': '359341',
            'x-fb-friendly-name': FRIENDLY_NAME,
            'x-fb-lsd': tokens["lsd"],
        }

        payload = get_payload(tokens, sort_by_new=sort_by_new, after_cursor=after_cursor, req_id=req_id)
        json_data = await post_form(GRAPHQL_URL, payload, HEADERS)
        if not json_data:
            logger.error("❌ Empty/failed GraphQL response.")
            break

        jobs = parse_jobs(json_data)
        # dedup within this mode
        new = [j for j in jobs if j.job_id not in seen_ids]
        for j in new:
            seen_ids.add(j.job_id)
        collected.extend(new)

        page_info = (json_data.get("data", {})
                               .get("job_search_with_featured_jobs", {})
                               .get("page_info", {}))
        if page_info.get("has_next_page") and page_info.get("end_cursor"):
            after_cursor = page_info["end_cursor"]
            page += 1
            await asyncio.sleep(random.uniform(1.0, 3.0))
        else:
            break

    logger.info(f"✅ mode sort_by_new={sort_by_new}: got {len(collected)} unique jobs")
    return collected


async def get_jobs():
    logger.info("Starting Meta job scrape (union of both sort modes)…")
    tokens = extract_meta_tokens()
    await asyncio.sleep(random.uniform(0, 2.5))  # small jitter

    # Fetch both views
    jobs_default, jobs_new = await asyncio.gather(
        fetch_all_pages_for_mode(tokens, sort_by_new=False),
        fetch_all_pages_for_mode(tokens, sort_by_new=True)
    )

    # Union by job_id (keep the first object; or merge fields if you like)
    by_id = {}
    for j in jobs_default + jobs_new:
        if j.job_id not in by_id:
            by_id[j.job_id] = j

    all_jobs = list(by_id.values())
    logger.info(f"🎉 Meta union: {len(all_jobs)} unique jobs (default={len(jobs_default)}, new={len(jobs_new)})")
    return all_jobs

