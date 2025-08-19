import aiohttp
import asyncio
from core.logger import get_company_logger
import json



MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

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
            logger.warning(f"⚠️ Attempt {attempt} failed: {e}")

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
            logger.warning(f"response: {await response.text()}")
            logger.warning(f"⚠️ Attempt {attempt} failed: {e}")

        await asyncio.sleep(RETRY_DELAY)

    logger.error(f"❌ All {MAX_RETRIES} attempts failed for {url} {payload}")
    return None

# Used for Netflix
async def get_json(url, headers=None, params=None, cookies=None):
    logger = get_company_logger()
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with aiohttp.ClientSession(cookies=cookies) as session:
                async with session.get(url, headers=headers, params=params, timeout=10) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.warning(f"⚠️ Status {response.status} from {url}")
        except Exception as e:
            logger.warning(f"⚠️ Attempt {attempt} failed: {e}")

        await asyncio.sleep(RETRY_DELAY)

    logger.error(f"❌ All {MAX_RETRIES} attempts failed for {url}")
    return None



