import random
import hashlib
import time
import traceback
import aiohttp
import asyncio
from core.logger import get_company_logger
import json
from typing import Optional, Dict, Any
from core.context import get_company



MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds
BASE_TIMEOUT = 10  # seconds
MAX_BACKOFF = 20   # seconds
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 15

# Used for Apple, content type is application/json , reusable for JSON APIs
async def post_json(url, payload, headers):
    logger = get_company_logger()
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.warning(f"⚠️ Status {response.status} from {url}")
        except Exception as e:
            logger.error(f"⚠️ Attempt {attempt} failed: {e}")

        await asyncio.sleep(RETRY_DELAY)

    logger.error(f"❌ All {MAX_RETRIES} attempts failed for {url}")
    return None

def _short_hash(s: str) -> str:
    try:
        return hashlib.sha256(s.encode("utf-8")).hexdigest()[:10]
    except Exception:
        return "na"
    
async def post_form(
    url: str,
    payload: str,
    headers: Dict[str, str],
    cookies: Optional[Dict[str, str] | str] = None,
    parse_json: bool = True,
) -> Optional[Dict[str, Any] | str]:
    logger = get_company_logger()
    company = get_company()
    req_id = _short_hash(f"{time.time()}:{random.random()}")

    # Normalize cookie string → dict
    if isinstance(cookies, str):
        try:
            cookies = dict(pair.split("=", 1) for pair in cookies.split("; "))
        except Exception:
            cookies = None

    timeout = aiohttp.ClientTimeout(total=None, connect=CONNECT_TIMEOUT, sock_read=READ_TIMEOUT)

    for attempt in range(1, MAX_RETRIES + 1):
        t0 = time.time()
        text = None
        status = None
        err = None
        try:
            async with aiohttp.ClientSession(cookies=cookies, timeout=timeout) as session:
                async with session.post(url, data=payload, headers=headers) as response:
                    status = response.status
                    text = await response.text()

            elapsed_ms = int((time.time() - t0) * 1000)
            body_len = len(text or "")
            body_hash = _short_hash(text[:2048] or "") if text else "na"

            if status == 200:
                if parse_json:
                    try:
                        data = json.loads(text)
                        # Don’t spam; one concise success line:
                        logger.info(
                            f"[company={company}] [req={req_id}] ✅ 200 OK "
                            f"(attempt={attempt} ms={elapsed_ms} len={body_len} hash={body_hash})"
                        )
                        return data
                    except Exception as json_error:
                        logger.error(
                            f"[company={company}] [req={req_id}] ❌ JSON parse error "
                            f"(attempt={attempt} ms={elapsed_ms} len={body_len} hash={body_hash}): {json_error}"
                        )
                        # Show a small head of body for debugging (safe-ish):
                        logger.error(text[:400] + ("..." if body_len > 400 else ""))
                        # no return; fall through to retry below
                else:
                    logger.info(
                        f"[company={company}] [req={req_id}] ✅ 200 OK (text mode) "
                        f"(attempt={attempt} ms={elapsed_ms} len={body_len} hash={body_hash})"
                    )
                    return text
            else:
                # Non-200
                logger.warning(
                    f"[company={company}] [req={req_id}] ⚠️ Non-200 "
                    f"status={status} (attempt={attempt} ms={elapsed_ms} len={body_len} hash={body_hash})"
                )
        except Exception as e:
            err = e
            elapsed_ms = int((time.time() - t0) * 1000)
            # Don’t access response here; it may not exist.
            logger.error(
                f"[company={company}] [req={req_id}] ❌ Exception on POST "
                f"(attempt={attempt} ms={elapsed_ms}): {e}\n{traceback.format_exc()}"
            )

        # Backoff with jitter before next attempt
        if attempt < MAX_RETRIES:
            sleep_s = RETRY_DELAY * attempt * random.uniform(1.0, 2.0)
            logger.warning(f"[company={company}] [req={req_id}] 🔁 retrying in {sleep_s:.1f}s… (attempt={attempt+1})")
            await asyncio.sleep(sleep_s)

    logger.error(f"[company={company}] [req={req_id}] ❌ All {MAX_RETRIES} attempts failed for {url}")
    return None

# Used for Netflix
async def get_json(url, headers=None, params=None, cookies=None):
    logger = get_company_logger()
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with aiohttp.ClientSession(cookies=cookies) as session:
                # logger.debug(f"🌐 Attempt {attempt}: GET {url} "
                #              f"headers={headers} params={params}")  # log request details

                async with session.get(url, headers=headers, params=params, timeout=10) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            logger.debug(f"✅ Success from {url} (attempt {attempt}), "
                                         f"length={len(str(data))} chars")
                            return data
                        except Exception as parse_err:
                            logger.error(f"⚠️ Failed to parse JSON from {url} "
                                         f"(attempt {attempt}): {parse_err}")
                            return None
                    else:
                        text = await response.text()
                        logger.warning(f"⚠️ Status {response.status} from {url} "
                                       f"(attempt {attempt}), body snippet={text[:200]}")

        except Exception as e:
            logger.error(f"⚠️ Attempt {attempt} failed for {url}: {e}")

        await asyncio.sleep(RETRY_DELAY)

    logger.error(f"❌ All {MAX_RETRIES} attempts failed for {url} "
                 f"headers={headers} params={params}")
    return None


async def get_text_resilient(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    cookies: Optional[Dict[str, str]] = None,
    max_retries: int = 3,
    base_timeout: int = 10,
    max_backoff: int = 20,
    logger=None,
) -> Optional[str]:
    """Fetch plain text with retries/backoff, similar to get_json_resilient."""
    attempt = 0
    async with aiohttp.ClientSession(cookies=cookies) as session:
        while attempt < max_retries:
            attempt += 1
            delay = None
            try:
                timeout = aiohttp.ClientTimeout(total=base_timeout)
                async with session.get(url, headers=headers, params=params, timeout=timeout) as resp:
                    text = await resp.text()
                    if resp.status == 200:
                        return text

                    if logger:
                        body_snip = text[:300]
                        logger.warning(
                            f"⚠️ GET {url} -> {resp.status}; params={params} body: {body_snip}"
                        )

                    if not _retryable_status(resp.status):
                        return None

                    ra = resp.headers.get("Retry-After")
                    if ra:
                        try:
                            delay = float(ra)
                        except Exception:
                            delay = None
                    if delay is None:
                        delay = min(max_backoff, 2 ** attempt + random.random())
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if logger:
                    logger.warning(f"⚠️ GET attempt {attempt} failed: {e}")
                delay = min(max_backoff, 2 ** attempt + random.random())

            if delay is None:
                delay = 1.0
            await asyncio.sleep(delay)

    if logger:
        logger.error(f"❌ All {max_retries} GET attempts failed for {url} with params={params}")
    return None


def _retryable_status(status: Optional[int]) -> bool:
    # Retry on 429 and 5xx
    return status == 429 or (status is not None and 500 <= status < 600)


async def _read_json_lenient_resp(resp: aiohttp.ClientResponse, logger=None) -> Optional[Dict[str, Any]]:
    # Try normal JSON first; fall back to text->json if content-type is off
    try:
        return await resp.json()
    except Exception:
        try:
            txt = await resp.text()
            return json.loads(txt)
        except Exception:
            if logger:
                snippet = (txt[:300] + "…") if 'txt' in locals() and txt else "<no body>"
                logger.warning(f"⚠️ Failed to parse JSON; body snippet: {snippet}")
            return None

# Used for Microsoft    
async def get_json_resilient(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    cookies: Optional[Dict[str, str]] = None,
    max_retries: int = 3,
    base_timeout: int = 10,
    max_backoff: int = 20,
    logger=None,
) -> Optional[Dict[str, Any]]:
    """
    Keyword-only parameters to avoid accidental (headers, params) swap.
    - Retries on 429/5xx and timeouts, honoring Retry-After when present.
    - Exponential backoff + jitter.
    - Lenient JSON parsing (handles text/json mismatches).
    """
    attempt = 0
    async with aiohttp.ClientSession(cookies=cookies) as session:
        while attempt < max_retries:
            attempt += 1
            delay = None
            try:
                timeout = aiohttp.ClientTimeout(total=base_timeout)
                async with session.get(url, headers=headers, params=params, timeout=timeout) as resp:
                    if resp.status == 200:
                        return await _read_json_lenient_resp(resp, logger=logger)

                    body_snip = (await resp.text())[:300]
                    if logger:
                        logger.warning(f"⚠️ GET {url} -> {resp.status}; params={params} body: {body_snip}")

                    if not _retryable_status(resp.status):
                        return None

                    # Retry-After support (seconds)
                    ra = resp.headers.get("Retry-After")
                    if ra:
                        try:
                            delay = float(ra)
                        except Exception:
                            delay = None
                    if delay is None:
                        delay = min(max_backoff, 2 ** attempt + random.random())
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if logger:
                    logger.warning(f"⚠️ GET attempt {attempt} failed: {e}")
                delay = min(max_backoff, 2 ** attempt + random.random())

            if delay is None:
                delay = 1.0
            await asyncio.sleep(delay)

    if logger:
        logger.error(f"❌ All {max_retries} GET attempts failed for {url} with params={params}")
    return None