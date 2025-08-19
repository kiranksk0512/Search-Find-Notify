import requests
import re
import json
from core.logger import get_company_logger

def extract_meta_tokens():
    logger = get_company_logger()
    URL = "https://www.metacareers.com/jobs"
    response = requests.get(URL)
    html = response.text

    # Extract LSD token
    lsd_match = re.search(r'\["LSD",\[\],\{"token":"(.*?)"\}', html)
    lsd = lsd_match.group(1) if lsd_match else None

    if not lsd:
        logger.warning("⚠️ LSD token could not be extracted.")


    # Extract SiteData JSON blob
    site_data_match = re.search(r'\["SiteData",\[\],(\{.*?\})\s*,\s*\d+\]', html, re.DOTALL)
    site_data = json.loads(site_data_match.group(1)) if site_data_match else {}

    # Extract fields
    spin_r = site_data.get("__spin_r")
    spin_b = site_data.get("__spin_b")
    spin_t = site_data.get("__spin_t")
    hs = site_data.get("haste_session")
    hsi = site_data.get("hsi")
    rev = site_data.get("client_revision")

    # Generate jazoest using LSD token
    jazoest = generate_jazoest(lsd, 2, False) if lsd else None

    return {
        "lsd": lsd,
        "jazoest": jazoest,
        "__spin_r": spin_r,
        "__spin_b": spin_b,
        "__spin_t": spin_t,
        "__hs": hs,
        "__hsi": hsi,
        "__rev": rev,
    }

def generate_jazoest(lsd_token: str, version: int = 2, should_randomize: bool = False) -> str:
    total = sum(ord(c) for c in lsd_token)
    if should_randomize:
        return str(total)
    else:
        return str(version) + str(total)
