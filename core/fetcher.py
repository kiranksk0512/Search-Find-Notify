import random
import aiohttp
import asyncio
from core.logger import get_company_logger
import json
from typing import Optional, Dict, Any



MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds
BASE_TIMEOUT = 10  # seconds
MAX_BACKOFF = 20   # seconds

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


async def post_form(url, payload, headers, cookies=None, parse_json=True):
    logger = get_company_logger()
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if isinstance(cookies, str):
                cookies = dict(pair.split("=", 1) for pair in cookies.split("; "))

            async with aiohttp.ClientSession(cookies=cookies) as session:
                async with session.post(url, data=payload, headers=headers, timeout=10) as response:
                    text = await response.text()
                    if response.status == 200:
                        if parse_json:
                            try:
                                logger.warning("Parsing Json")
                                return json.loads(text)
                            except Exception as json_error:
                                logger.error(f"❌ Failed to parse JSON: {json_error}")
                                logger.error(f"Response content: {text[:300]}...")
                                return None
                        else:
                            print(text[:10000]) 
                            return text
                    else:
                        logger.warning(f"⚠️ Non-200 response: {response.status} - {await response.text()}")
                        # logger.warning(f"⚠️ Status {response.status} from {url}")
        except Exception as e:
            logger.error(f"response: {await response.text()}")
            logger.error(f"⚠️ Attempt {attempt} failed: {e}")

        await asyncio.sleep(RETRY_DELAY)

    logger.error(f"❌ All {MAX_RETRIES} attempts failed for {url} {payload}")
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