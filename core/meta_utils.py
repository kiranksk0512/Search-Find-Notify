# core/meta_utils.py
import os, json, re, time, random, requests, hashlib
from typing import Optional, Dict, Any
from core.logger import get_company_logger
from core.context import get_company

REAL_USER_AGENTS = [
    # full, real UAs (no ellipses!)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

def _mask(v, keep: int = 4) -> str:
    if v is None:
        return "null"
    s = str(v)
    return f"{s[:keep]}…{len(s)}"

def _short_hash(s: str) -> str:
    try:
        return hashlib.sha256((s or "").encode("utf-8")).hexdigest()[:10]
    except Exception:
        return "na"

def _parse_tokens(html: str, logger, company: str):
    lsd_match = re.search(r'\["LSD",\[\],\{"token":"(.*?)"\}', html)
    lsd = lsd_match.group(1) if lsd_match else None
    if not lsd:
        logger.warning(f"[company={company}] ⚠️ LSD token not found")

    site_data_match = re.search(r'\["SiteData",\[\],(\{.*?\})\s*,\s*\d+\]', html, re.DOTALL)
    site_data = {}
    if site_data_match:
        try:
            site_data = json.loads(site_data_match.group(1))
        except Exception as e:
            logger.error(f"[company={company}] ❌ Failed to parse SiteData JSON: {e}")
    else:
        logger.warning(f"[company={company}] ⚠️ SiteData blob not found")

    spin_r = site_data.get("__spin_r")
    spin_b = site_data.get("__spin_b")
    spin_t = site_data.get("__spin_t")
    hs    = site_data.get("haste_session") or site_data.get("__hs")
    hsi   = site_data.get("hsi")
    rev   = site_data.get("client_revision") or site_data.get("__rev")

    jazoest = generate_jazoest(lsd, 2, False) if lsd else None

    return {
        "lsd": lsd, "jazoest": jazoest, "__spin_r": spin_r, "__spin_b": spin_b,
        "__spin_t": spin_t, "__hs": hs, "__hsi": hsi, "__rev": rev
    }

def extract_meta_tokens() -> Optional[Dict[str, Any]]:
    logger = get_company_logger()
    company = get_company()
    URL = "https://www.metacareers.com/jobs"

    # Attempt 1: vanilla requests (this is what worked for you before)
    t0 = time.time()
    try:
        resp = requests.get(URL, timeout=10)
        html = resp.text or ""
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.info(f"[company={company}] 🌐 token fetch A status={resp.status_code} ms={elapsed_ms} len={len(html)} hash={_short_hash(html[:4096])}")
        if resp.status_code == 200 and len(html) > 1000:
            tokens = _parse_tokens(html, logger, company)
            logger.info(f"[company={company}] 🔑 tokensA lsd={_mask(tokens['lsd'])} __hsi={_mask(tokens['__hsi'])} __rev={_mask(tokens['__rev'])}")
            return tokens
    except Exception as e:
        logger.error(f"[company={company}] ❌ Exception token fetch A: {e}")

    # Attempt 2: real UA + simple accept-language (no client hints)
    try:
        ua = random.choice(REAL_USER_AGENTS)
        headers = {
            "user-agent": ua,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "referer": "https://www.metacareers.com/",
            "upgrade-insecure-requests": "1",
        }
        # Optional cookies toggle via env
        cookies = {"datr": "BNaDaLVxvClP3ifeL2rvnxJH", "wd": "1280x800"} if os.getenv("META_SEND_COOKIES") == "1" else None

        t1 = time.time()
        resp = requests.get(URL, headers=headers, cookies=cookies, timeout=10)
        html = resp.text or ""
        elapsed_ms = int((time.time() - t1) * 1000)
        logger.info(f"[company={company}] 🌐 token fetch B status={resp.status_code} ms={elapsed_ms} len={len(html)} hash={_short_hash(html[:4096])} ua={ua.split(')')[0]})")
        if resp.status_code == 200 and len(html) > 1000:
            tokens = _parse_tokens(html, logger, company)
            logger.info(f"[company={company}] 🔑 tokensB lsd={_mask(tokens['lsd'])} __hsi={_mask(tokens['__hsi'])} __rev={_mask(tokens['__rev'])}")
            return tokens
    except Exception as e:
        logger.error(f"[company={company}] ❌ Exception token fetch B: {e}")

    logger.warning(f"[company={company}] ⚠️ All token attempts failed; returning None")
    return None

def generate_jazoest(lsd_token: str, version: int = 2, should_randomize: bool = False) -> str:
    total = sum(ord(c) for c in lsd_token)
    return (str(version) + str(total)) if not should_randomize else str(total)
